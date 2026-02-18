"""FastMCP server — Conversation Analyser with MCP Sampling."""

import json
import logging
from pathlib import Path


from mcp.server.fastmcp import Context, FastMCP

from .analyser import analyse
from .models import (
    AnalysisError,
    ConversationTurn,
    ParsedConversation,
    WorkType,
    WorkTypeSetupRequired,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in work types
# ---------------------------------------------------------------------------

_BUILTIN_WORK_TYPES: list[WorkType] = [
    WorkType(
        id="meeting",
        label="Meeting Transcript",
        description="Analyse meeting transcripts for decisions, action items, and sentiment.",
        is_builtin=True,
    ),
    WorkType(
        id="deliverables",
        label="Deliverables Discussion",
        description="Conversations about project deliverables, timelines, and scope.",
        is_builtin=True,
    ),
    WorkType(
        id="strategy",
        label="Strategic Discussion",
        description="High-level strategy, vision, and planning conversations.",
        is_builtin=True,
    ),
    WorkType(
        id="board_update",
        label="Board / Executive Update",
        description="Board meetings, investor updates, and executive briefings.",
        is_builtin=True,
    ),
    WorkType(
        id="hiring",
        label="Hiring & Performance",
        description="Interviews, performance reviews, and team feedback conversations.",
        is_builtin=True,
    ),
    WorkType(
        id="brainstorm",
        label="Brainstorm / Ideation",
        description="Creative brainstorming, ideation, and innovation sessions.",
        is_builtin=True,
    ),
    WorkType(
        id="customer_call",
        label="Customer / Sales Call",
        description="Customer discovery, sales calls, and support conversations.",
        is_builtin=True,
    ),
    WorkType(
        id="personal_benchmark",
        label="Personal Benchmark",
        description="Analyse recent activity to categorise work and estimate manual time saved.",
        is_builtin=True,
    ),
]

# Path for persisting user-created work types
_USER_WORK_TYPES_FILE = Path(__file__).parents[2] / "data" / "user_work_types.json"


def _load_user_work_types() -> list[WorkType]:
    if not _USER_WORK_TYPES_FILE.exists():
        return []
    try:
        data = json.loads(_USER_WORK_TYPES_FILE.read_text(encoding="utf-8"))
        return [WorkType(**item) for item in data]
    except Exception:  # noqa: BLE001
        logger.warning("Failed to load user work types", exc_info=True)
        return []


def _save_user_work_type(wt: WorkType) -> None:
    _USER_WORK_TYPES_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_user_work_types()
    existing = [e for e in existing if e.id != wt.id]
    existing.append(wt)
    _USER_WORK_TYPES_FILE.write_text(
        json.dumps([e.model_dump() for e in existing], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="conversation-analyser",
    instructions=(
        "Analyse conversation files using MCP Sampling. "
        "Start with `list_work_types` to see available work types, "
        "then call `analyse_conversation` with a file path."
    ),
)


@mcp.tool()
def list_work_types() -> list:
    """List all available work types (built-in + user-created)."""
    return [wt.model_dump() for wt in _BUILTIN_WORK_TYPES + _load_user_work_types()]


@mcp.tool()
def save_work_type(
    work_type_id: str,
    label: str,
    description: str,
) -> dict:
    """
    Create or update a custom work type.

    Use this on first run to define the context for your conversations
    (e.g. 'board_meeting', 'sprint_retro', 'investor_call').

    Args:
        work_type_id: Unique slug (lowercase, hyphens ok), e.g. 'sprint_retro'
        label: Human-readable label, e.g. 'Sprint Retrospective'
        description: When to use this work type
    """
    wt = WorkType(
        id=work_type_id.lower().replace(" ", "_"),
        label=label,
        description=description,
        is_builtin=False,
    )
    _save_user_work_type(wt)
    return wt.model_dump()


@mcp.tool()
def list_analysis_types() -> list:
    """List all available analysis types with descriptions."""
    return [
        {
            "id": "summary",
            "label": "Executive Summary",
            "description": "Concise summary of the conversation",
        },
        {
            "id": "sentiment",
            "label": "Sentiment Analysis",
            "description": "Overall sentiment and emotional arc",
        },
        {
            "id": "key_topics",
            "label": "Key Topics",
            "description": "Main topics and themes discussed",
        },
        {
            "id": "action_items",
            "label": "Action Items",
            "description": "Extracted action items, owners, and deadlines",
        },
        {
            "id": "custom",
            "label": "Custom",
            "description": "Provide your own analysis prompt via custom_prompt",
        },
        {
            "id": "benchmark",
            "label": "Benchmark",
            "description": "Categorise activity and estimate manual effort saved (Best for multi-conversation analysis)",
        },
    ]


@mcp.tool()
async def analyse_conversation(
    ctx: Context,
    file_path: str,
    work_type: str = "meeting",
    analysis_type: str = "summary",
    custom_prompt: str = "",
    max_tokens_per_chunk: int = 2000,
    model_hint: str = "",
) -> dict:
    """
    Analyse a conversation file using MCP Sampling.

    The server reads the file, chunks it if needed, sends each chunk to the
    client's LLM via sampling/createMessage, synthesises the results, and
    returns an interactive HTML scorecard.

    Requires the MCP client to support sampling (e.g. Claude Desktop).

    Args:
        file_path: Absolute path to the conversation file (.json, .md, or .txt)
        work_type: Work type id — determines which prompt template is used (use list_work_types to see options)
        analysis_type: Type of analysis to perform
        custom_prompt: Custom analysis prompt (only used when analysis_type='custom')
        max_tokens_per_chunk: Approximate token budget per chunk (500-8000, default 2000)
        model_hint: Optional model name hint, e.g. 'claude-3-5-sonnet'
    """
    # First-time user check: if work_type not in known types, suggest setup
    all_types = _BUILTIN_WORK_TYPES + _load_user_work_types()
    known_ids = {wt.id for wt in all_types}
    if work_type not in known_ids:
        result = WorkTypeSetupRequired(suggested_types=_BUILTIN_WORK_TYPES)
        return result.model_dump()

    analysis_result = await analyse(
        ctx=ctx,
        file_path=file_path,
        analysis_type=analysis_type,
        work_type=work_type,
        custom_prompt=custom_prompt or None,
        max_tokens_per_chunk=max(500, min(8000, max_tokens_per_chunk)),
        model_hint=model_hint or None,
    )

    return analysis_result.model_dump()


@mcp.tool()
async def analyse_benchmark_conversations(
    ctx: Context,
    threads: list,
    model_hint: str = "",
) -> dict:
    """
    Analyse a collection of email threads to generate a Personal Benchmark.

    This tool takes multiple threads (e.g. from gmail-fetcher:get_benchmark_data),
    concatenates them into a single virtual conversation, and analyses them
    using the 'personal_benchmark' work type and 'benchmark' analysis type.

    Args:
        threads: List of GmailThread-like dictionaries
        model_hint: Optional model name hint
    """
    all_turns: list[ConversationTurn] = []

    for t in threads:
        # Best-effort conversion from dict to GmailThread-like structure
        subject = t.get("subject", "(no subject)")
        messages = t.get("messages", [])
        for msg in messages:
            sender = msg.get("sender", "unknown")
            recipients = msg.get("recipients", [])
            date = msg.get("date", "")
            body = msg.get("body_text", "")

            content = (
                f"Subject: {subject}\n"
                f"From: {sender}\n"
                f"To: {', '.join(recipients) if isinstance(recipients, list) else recipients}\n"
                f"Date: {date}\n\n"
                f"{body}"
            )
            all_turns.append(ConversationTurn(role="user", content=content))

    if not all_turns:
        return AnalysisError(
            error="no_data",
            detail="No conversation turns found in the provided threads.",
        ).model_dump()

    # Create a ParsedConversation object
    raw_text = "\n\n---\n\n".join([t.content for t in all_turns])
    conversation = ParsedConversation(
        messages=all_turns,
        raw_text=raw_text,
        token_estimate=len(raw_text) // 4,
        source_format="plaintext",
    )

    analysis_result = await analyse(
        ctx=ctx,
        conversation=conversation,
        work_type="personal_benchmark",
        analysis_type="benchmark",
        model_hint=model_hint or None,
    )

    return analysis_result.model_dump()


@mcp.prompt()
def conversation_analysis(
    work_type: str = "meeting", analysis_type: str = "summary"
) -> str:
    """
    Return the system prompt template for a given work type and analysis type.
    Useful for clients that want to run analysis themselves.
    """
    from .analyser import _get_system_prompt, _load_prompts  # noqa: PLC0415

    prompts = _load_prompts()
    return _get_system_prompt(work_type, analysis_type, None, prompts)


def main() -> None:
    """Entry point — run in stdio mode."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
