"""MCP Sampling orchestrator — all LLM calls go through session.create_message()."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import mcp.types as mcp_types
from mcp.server.fastmcp import Context

from .chunker import chunk_conversation
from .conversation_parser import parse_conversation_file
from .models import (
    AnalysisChunkResult,
    AnalysisError,
    AnalysisResult,
    ParsedConversation,
)
from .scorecard import build_scorecard

logger = logging.getLogger(__name__)

# Path to the editable prompts file (relative to project root)
_PROMPTS_FILE = Path(__file__).parents[2] / "prompts" / "prompts.md"


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


def _load_prompts() -> dict[str, str]:
    """
    Parse prompts/prompts.md and return a dict of {section_key: prompt_text}.

    Sections are identified by '## key' headers inside the file.
    """
    if not _PROMPTS_FILE.exists():
        logger.warning(
            "prompts.md not found at %s — using empty prompts", _PROMPTS_FILE
        )
        return {}

    raw = _PROMPTS_FILE.read_text(encoding="utf-8")
    prompts: dict[str, str] = {}
    current_key: str | None = None
    buffer: list[str] = []

    for line in raw.splitlines():
        # Top-level sections (# ...) are groupings, not keys
        if line.startswith("# "):
            if current_key and buffer:
                prompts[current_key] = "\n".join(buffer).strip()
            current_key = None
            buffer = []
        # Second-level headers are section groups (## work_types, ## analysis_types)
        elif line.startswith("## "):
            if current_key and buffer:
                prompts[current_key] = "\n".join(buffer).strip()
            current_key = None
            buffer = []
        # Third-level headers are individual prompt keys
        elif line.startswith("### "):
            if current_key and buffer:
                prompts[current_key] = "\n".join(buffer).strip()
            current_key = line[4:].strip().lower()
            buffer = []
        else:
            if current_key is not None:
                buffer.append(line)

    if current_key and buffer:
        prompts[current_key] = "\n".join(buffer).strip()

    return prompts


def _get_system_prompt(
    work_type: str,
    analysis_type: str,
    custom_prompt: str | None,
    prompts: dict[str, str],
) -> str:
    """Build the system prompt by combining work-type context + analysis instruction."""
    if analysis_type == "custom" and custom_prompt:
        return custom_prompt

    work_prompt = prompts.get(work_type, "")
    analysis_prompt = prompts.get(analysis_type, "")

    parts = []
    if work_prompt:
        parts.append(work_prompt)
    if analysis_prompt:
        parts.append(analysis_prompt)

    if not parts:
        return (
            f"You are analysing a {work_type} conversation. "
            f"Perform a {analysis_type} analysis and return structured findings."
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Core sampling helpers
# ---------------------------------------------------------------------------


async def _sample_chunk(
    ctx: Context,
    chunk_text: str,
    system_prompt: str,
    chunk_index: int,
    total_chunks: int,
    model_hint: str | None,
    max_response_tokens: int = 1500,
) -> AnalysisChunkResult:
    """Send one chunk to the LLM via MCP sampling and return a partial result."""
    header = (
        f"[Chunk {chunk_index + 1} of {total_chunks}]\n\n" if total_chunks > 1 else ""
    )
    user_text = f"{header}Conversation:\n\n{chunk_text}"

    messages = [
        mcp_types.SamplingMessage(
            role="user",
            content=mcp_types.TextContent(type="text", text=user_text),
        )
    ]

    model_prefs = None
    if model_hint:
        model_prefs = mcp_types.ModelPreferences(
            hints=[mcp_types.ModelHint(name=model_hint)],
            intelligencePriority=0.8,
            speedPriority=0.2,
        )

    await ctx.info(f"Sampling chunk {chunk_index + 1}/{total_chunks}…")

    try:
        result = await ctx.session.create_message(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=max_response_tokens,
            model_preferences=model_prefs,
            related_request_id=ctx.request_id,
        )
    except Exception as exc:
        logger.error("Sampling failed: %s", exc)
        return AnalysisChunkResult(
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            partial_analysis=f"Error during sampling: {exc}",
            model_used="unknown",
            stop_reason="error",
        )

    text = (
        result.content.text if hasattr(result.content, "text") else str(result.content)
    )
    return AnalysisChunkResult(
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        partial_analysis=text,
        model_used=result.model,
        stop_reason=result.stopReason,
    )


async def _synthesise(
    ctx: Context,
    partial_results: list[AnalysisChunkResult],
    analysis_type: str,
    work_type: str,
    model_hint: str | None,
) -> tuple[str, str, str | None]:
    """
    Merge partial chunk results into a final synthesis via MCP sampling.

    Returns (summary_text, model_used, stop_reason).
    """
    combined = "\n\n---\n\n".join(
        f"[Partial analysis {r.chunk_index + 1}/{r.total_chunks}]\n{r.partial_analysis}"
        for r in partial_results
    )

    synthesis_prompt = (
        f"You have received {len(partial_results)} partial analyses of a {work_type} "
        f"conversation, each covering a different section. "
        f"Synthesise them into a single coherent {analysis_type} analysis. "
        "Eliminate redundancy, resolve any contradictions, and produce a unified result. "
        "Return your response as JSON with keys: "
        '"summary" (string), "sections" (list of {title, content, score?}), '
        '"key_findings" (list of strings).'
    )

    messages = [
        mcp_types.SamplingMessage(
            role="user",
            content=mcp_types.TextContent(
                type="text",
                text=f"Partial analyses to synthesise:\n\n{combined}",
            ),
        )
    ]

    model_prefs = None
    if model_hint:
        model_prefs = mcp_types.ModelPreferences(
            hints=[mcp_types.ModelHint(name=model_hint)],
            intelligencePriority=1.0,
        )

    await ctx.info("Synthesising partial analyses via MCP sampling…")

    try:
        result = await ctx.session.create_message(
            messages=messages,
            system_prompt=synthesis_prompt,
            max_tokens=2000,
            model_preferences=model_prefs,
            related_request_id=ctx.request_id,
        )
    except Exception as exc:
        logger.error("Synthesis sampling failed: %s", exc)
        return f"Error during synthesis: {exc}", "unknown", "error"

    text = (
        result.content.text if hasattr(result.content, "text") else str(result.content)
    )
    return text, result.model, result.stopReason


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def analyse(
    ctx: Context,
    file_path: str | None = None,
    conversation: ParsedConversation | None = None,
    analysis_type: str = "summary",
    work_type: str = "meeting",
    custom_prompt: str | None = None,
    max_tokens_per_chunk: int = 2000,
    model_hint: str | None = None,
) -> AnalysisResult | AnalysisError:
    """
    Full analysis pipeline:
    1. Check sampling capability
    2. Parse conversation file (if file_path provided)
    3. Chunk if needed
    4. Sample each chunk via MCP sampling
    5. Synthesise (also via MCP sampling) if multi-chunk
    6. Build HTML scorecard
    7. Return AnalysisResult
    """
    # 1. Capability check
    if not ctx.session.check_client_capability(
        mcp_types.ClientCapabilities(sampling=mcp_types.SamplingCapability())  # type: ignore[call-arg]
    ):
        return AnalysisError(
            error="sampling_not_supported",
            detail="The connected MCP client does not support sampling/createMessage.",
            suggestion=(
                "Use a client that supports MCP sampling, such as Claude Desktop. "
                "See https://modelcontextprotocol.io/docs/concepts/sampling for details."
            ),
        )

    # 2. Parse or use provided conversation
    if conversation is None:
        if file_path is None:
            return AnalysisError(
                error="missing_input",
                detail="Either file_path or conversation must be provided.",
            )
        try:
            conversation = parse_conversation_file(file_path)
        except FileNotFoundError as exc:
            return AnalysisError(
                error="file_not_found",
                detail=str(exc),
                suggestion="Provide an absolute path to an existing .json, .md, or .txt file.",
            )
        except ValueError as exc:
            return AnalysisError(
                error="parse_error",
                detail=str(exc),
            )

    await ctx.info(
        f"Parsed {len(conversation.messages)} turns "
        f"(~{conversation.token_estimate} tokens, format={conversation.source_format})"
    )

    # 3. Chunk
    chunks = chunk_conversation(conversation, max_tokens_per_chunk=max_tokens_per_chunk)
    total_chunks = len(chunks)
    await ctx.info(f"Split into {total_chunks} chunk(s)")

    # 4. Load prompts
    prompts = _load_prompts()
    system_prompt = _get_system_prompt(work_type, analysis_type, custom_prompt, prompts)

    # 5. Sample each chunk
    partial_results: list[AnalysisChunkResult] = []
    for i, chunk in enumerate(chunks):
        chunk_result = await _sample_chunk(
            ctx=ctx,
            chunk_text=chunk,
            system_prompt=system_prompt,
            chunk_index=i,
            total_chunks=total_chunks,
            model_hint=model_hint,
        )
        partial_results.append(chunk_result)
        await ctx.report_progress(i + 1, total_chunks)

    # 6. Synthesise if multi-chunk
    if total_chunks == 1:
        final_text = partial_results[0].partial_analysis
        model_used = partial_results[0].model_used
        stop_reason = partial_results[0].stop_reason
    else:
        final_text, model_used, stop_reason = await _synthesise(
            ctx=ctx,
            partial_results=partial_results,
            analysis_type=analysis_type,
            work_type=work_type,
            model_hint=model_hint,
        )

    # 7. Parse synthesis JSON (best-effort) and build scorecard
    synthesis_data = {"summary": final_text, "sections": [], "key_findings": []}
    text_to_parse = final_text.strip()
    if "```json" in text_to_parse:
        text_to_parse = text_to_parse.split("```json")[1].split("```")[0].strip()
    elif "```" in text_to_parse:
        text_to_parse = text_to_parse.split("```")[1].split("```")[0].strip()

    try:
        s_data = json.loads(text_to_parse)
        if isinstance(s_data, dict):
            synthesis_data.update(s_data)
        summary = synthesis_data.get("summary", final_text[:500])
    except (json.JSONDecodeError, AttributeError):
        summary = final_text[:500]

    scorecard_html = build_scorecard(
        analysis_type=analysis_type,
        work_type=work_type,
        synthesis_data=synthesis_data,
        chunk_count=total_chunks,
        model_used=model_used,
        source_format=conversation.source_format,
        turn_count=len(conversation.messages),
    )

    return AnalysisResult(
        analysis_type=analysis_type,
        work_type=work_type,
        summary=summary,
        scorecard_html=scorecard_html,
        chunk_results=partial_results if total_chunks > 1 else [],
        impact_stories=synthesis_data.get("impact_stories", []),
        force_multiplier=synthesis_data.get("force_multiplier"),
        employee_equivalent=synthesis_data.get("employee_equivalent"),
        model_used=model_used,
        stop_reason=stop_reason,
    )
