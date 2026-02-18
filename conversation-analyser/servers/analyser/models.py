"""Pydantic BaseModel definitions for the Conversation Analyser MCP server."""

# from __future__ import annotations — Disabled for FastMCP compatibility

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Conversation parsing
# ---------------------------------------------------------------------------


class ConversationTurn(BaseModel):
    """A single turn in a conversation."""

    role: str = Field(description="Speaker role, e.g. 'user', 'assistant', 'system'")
    content: str = Field(description="Text content of the turn")


class ParsedConversation(BaseModel):
    """Normalised representation of an ingested conversation file."""

    messages: list[ConversationTurn]
    raw_text: str = Field(description="Original raw text of the file")
    token_estimate: int = Field(description="Rough token count (len // 4)")
    source_format: str = Field(description="Detected input format")


# ---------------------------------------------------------------------------
# Work types
# ---------------------------------------------------------------------------


class WorkType(BaseModel):
    """A named context that selects the right prompt template."""

    id: str = Field(description="Unique slug, e.g. 'meeting'")
    label: str = Field(description="Human-readable label, e.g. 'Meeting Transcript'")
    description: str = Field(description="Short description of when to use this type")
    is_builtin: bool = Field(default=True, description="False for user-created types")


class WorkTypeSetupRequired(BaseModel):
    """Returned when no work type is configured yet (first-time user)."""

    message: str = Field(
        default=(
            "No work type selected. Please choose one from `suggested_types` "
            "or create your own with the `save_work_type` tool."
        )
    )
    suggested_types: list[WorkType]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class AnalysisChunkResult(BaseModel):
    """Partial analysis result for one chunk of a large conversation."""

    chunk_index: int = Field(description="0-based chunk index")
    total_chunks: int = Field(description="Total number of chunks")
    partial_analysis: str = Field(description="LLM output for this chunk")
    model_used: str = Field(description="Model name returned by the client")
    stop_reason: str | None = Field(default=None)


class AnalysisResult(BaseModel):
    """Final analysis result returned to the MCP client."""

    analysis_type: str
    work_type: str
    summary: str = Field(description="Plain-text executive summary")
    scorecard_html: str = Field(
        description="Full self-contained interactive HTML scorecard"
    )
    chunk_results: list[AnalysisChunkResult] = Field(
        default_factory=list,
        description="Per-chunk partial results (empty for single-chunk analyses)",
    )
    impact_stories: list[dict] = Field(
        default_factory=list,
        description="Specific narrative examples of time savings (for benchmark)",
    )
    force_multiplier: float | None = Field(
        default=None, description="Ratio of Manual Time / Agentic Time"
    )
    employee_equivalent: float | None = Field(
        default=None, description="Manual hours / 40h work week"
    )
    model_used: str = Field(description="Model name used for the final synthesis")
    stop_reason: str | None = Field(default=None)


class AnalysisError(BaseModel):
    """Structured error returned when analysis cannot proceed."""

    error: str
    detail: str
    suggestion: str | None = None


# ---------------------------------------------------------------------------
# Tool inputs
# ---------------------------------------------------------------------------


class AnalyseConversationInput(BaseModel):
    """Input schema for the analyse_conversation tool."""

    file_path: str = Field(
        description="Absolute or relative path to the conversation file"
    )
    analysis_type: str = Field(default="summary")
    work_type: str = Field(
        default="meeting",
        description="Work type id — determines which prompt template is used",
    )
    custom_prompt: str | None = Field(
        default=None,
        description="Used only when analysis_type == 'custom'",
    )
    max_tokens_per_chunk: int = Field(
        default=2000,
        ge=500,
        le=8000,
        description="Approximate token budget per chunk",
    )
    model_hint: str | None = Field(
        default=None,
        description="Optional model name hint, e.g. 'claude-3-5-sonnet'",
    )


class SaveWorkTypeInput(BaseModel):
    """Input schema for the save_work_type tool."""

    id: str = Field(description="Unique slug (lowercase, hyphens ok)")
    label: str = Field(description="Human-readable label")
    description: str = Field(description="When to use this work type")
