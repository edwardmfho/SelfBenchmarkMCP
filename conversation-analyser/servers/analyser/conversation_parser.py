"""Conversation file parser — supports JSON, Markdown, and plain text."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import ConversationTurn, ParsedConversation


def _estimate_tokens(text: str) -> int:
    """Conservative token estimate: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


def _parse_json(raw: str) -> list[ConversationTurn]:
    """Parse OpenAI-style or Anthropic-style JSON conversation arrays."""
    data: Any = json.loads(raw)

    # Handle top-level list
    if isinstance(data, list):
        messages = data
    # Handle {"messages": [...]} wrapper
    elif isinstance(data, dict) and "messages" in data:
        messages = data["messages"]
    # Handle {"conversation": [...]} wrapper
    elif isinstance(data, dict) and "conversation" in data:
        messages = data["conversation"]
    else:
        raise ValueError(
            "Unrecognised JSON structure — expected a list or {messages: [...]}"
        )

    turns: list[ConversationTurn] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "unknown"))
        # Content can be a string or a list of content blocks (Anthropic format)
        content = item.get("content", "")
        if isinstance(content, list):
            # Flatten text blocks
            content = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        turns.append(ConversationTurn(role=role, content=str(content)))
    return turns


def _parse_markdown(raw: str) -> list[ConversationTurn]:
    """Parse Markdown with role headers like '## User' or '**Assistant:**'."""
    # Match headers: ## Role, ### Role, **Role:**, or Role: at line start
    pattern = re.compile(
        r"^(?:#{1,3}\s+|(?:\*\*)?)(user|assistant|system|human|ai|bot)(?:\*\*)?:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    parts = pattern.split(raw)
    turns: list[ConversationTurn] = []

    # parts[0] is any preamble before first header; then alternating role/content
    i = 1
    while i + 1 < len(parts):
        role = parts[i].strip().lower()
        content = parts[i + 1].strip()
        if content:
            turns.append(ConversationTurn(role=role, content=content))
        i += 2

    if not turns:
        # Fallback: treat whole document as a single user turn
        turns = [ConversationTurn(role="user", content=raw.strip())]
    return turns


def _parse_plaintext(raw: str) -> list[ConversationTurn]:
    """Treat the entire file as a single user turn."""
    return [ConversationTurn(role="user", content=raw.strip())]


def parse_conversation_file(file_path: str) -> ParsedConversation:
    """
    Read and parse a conversation file.

    Supported formats:
    - JSON  (.json)  — OpenAI / Anthropic message arrays
    - Markdown (.md) — role headers (## User / ## Assistant)
    - Plain text     — treated as a single user turn

    Raises:
        FileNotFoundError: if the file does not exist
        ValueError: if the file cannot be parsed
    """
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Conversation file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        try:
            turns = _parse_json(raw)
            fmt = "json"
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Failed to parse JSON conversation: {exc}") from exc
    elif suffix in {".md", ".markdown"}:
        turns = _parse_markdown(raw)
        fmt = "markdown"
    else:
        # Try JSON first (file might lack extension)
        try:
            turns = _parse_json(raw)
            fmt = "json"
        except (json.JSONDecodeError, ValueError):
            # Try markdown
            turns = _parse_markdown(raw)
            fmt = "markdown" if len(turns) > 1 else "plaintext"
            if fmt == "plaintext":
                turns = _parse_plaintext(raw)

    return ParsedConversation(
        messages=turns,
        raw_text=raw,
        token_estimate=_estimate_tokens(raw),
        source_format=fmt,  # type: ignore[arg-type]
    )


def conversation_to_text(conversation: ParsedConversation) -> str:
    """Format a ParsedConversation as a readable text block for the LLM."""
    lines: list[str] = []
    for turn in conversation.messages:
        role_label = turn.role.upper()
        lines.append(f"[{role_label}]\n{turn.content}")
    return "\n\n".join(lines)
