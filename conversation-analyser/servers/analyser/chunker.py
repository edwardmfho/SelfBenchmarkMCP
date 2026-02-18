"""Sliding-window chunker for large conversations."""

from __future__ import annotations

from .conversation_parser import ConversationTurn, conversation_to_text
from .models import ParsedConversation


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_conversation(
    conversation: ParsedConversation,
    max_tokens_per_chunk: int = 2000,
    overlap_ratio: float = 0.10,
) -> list[str]:
    """
    Split a ParsedConversation into overlapping text chunks.

    Strategy:
    - Keeps whole turns together (never splits mid-message)
    - Adds ~10% overlap between chunks so context isn't lost at boundaries
    - Returns a list of formatted text strings ready to send to the LLM

    Args:
        conversation: Parsed conversation to chunk
        max_tokens_per_chunk: Approximate token budget per chunk
        overlap_ratio: Fraction of the chunk to repeat as overlap (0.0–0.5)

    Returns:
        List of text chunks. If the conversation fits in one chunk, returns a
        single-element list.
    """
    turns = conversation.messages

    # Fast path: fits in one chunk
    full_text = conversation_to_text(conversation)
    if _estimate_tokens(full_text) <= max_tokens_per_chunk:
        return [full_text]

    overlap_tokens = int(max_tokens_per_chunk * overlap_ratio)
    budget = max_tokens_per_chunk - overlap_tokens  # net new tokens per chunk

    chunks: list[str] = []
    current_turns: list[ConversationTurn] = []
    current_tokens = 0
    overlap_buffer: list[ConversationTurn] = []

    for turn in turns:
        turn_text = f"[{turn.role.upper()}]\n{turn.content}"
        turn_tokens = _estimate_tokens(turn_text)

        # If a single turn exceeds the budget, split it by paragraphs
        if turn_tokens > budget:
            # Flush current buffer first
            if current_turns:
                chunk_text = _turns_to_text(current_turns)
                chunks.append(chunk_text)
                overlap_buffer = _last_n_tokens(current_turns, overlap_tokens)
                current_turns = list(overlap_buffer)
                current_tokens = sum(
                    _estimate_tokens(f"[{t.role.upper()}]\n{t.content}")
                    for t in current_turns
                )

            # Split the oversized turn into paragraph sub-chunks
            paragraphs = turn.content.split("\n\n")
            para_buffer: list[str] = []
            para_tokens = 0
            for para in paragraphs:
                pt = _estimate_tokens(para)
                if para_tokens + pt > budget and para_buffer:
                    sub_content = "\n\n".join(para_buffer)
                    sub_turn = ConversationTurn(role=turn.role, content=sub_content)
                    chunk_text = _turns_to_text(list(overlap_buffer) + [sub_turn])
                    chunks.append(chunk_text)
                    # Keep last paragraph as overlap
                    overlap_buffer = [sub_turn]
                    para_buffer = [para]
                    para_tokens = pt
                else:
                    para_buffer.append(para)
                    para_tokens += pt
            if para_buffer:
                sub_content = "\n\n".join(para_buffer)
                sub_turn = ConversationTurn(role=turn.role, content=sub_content)
                current_turns = list(overlap_buffer) + [sub_turn]
                current_tokens = sum(
                    _estimate_tokens(f"[{t.role.upper()}]\n{t.content}")
                    for t in current_turns
                )
            continue

        if current_tokens + turn_tokens > budget and current_turns:
            # Flush current chunk
            chunk_text = _turns_to_text(current_turns)
            chunks.append(chunk_text)
            # Seed next chunk with overlap
            overlap_buffer = _last_n_tokens(current_turns, overlap_tokens)
            current_turns = list(overlap_buffer)
            current_tokens = sum(
                _estimate_tokens(f"[{t.role.upper()}]\n{t.content}")
                for t in current_turns
            )

        current_turns.append(turn)
        current_tokens += turn_tokens

    # Flush remaining turns
    if current_turns:
        chunks.append(_turns_to_text(current_turns))

    return chunks if chunks else [full_text]


def _turns_to_text(turns: list[ConversationTurn]) -> str:
    return "\n\n".join(f"[{t.role.upper()}]\n{t.content}" for t in turns)


def _last_n_tokens(
    turns: list[ConversationTurn], n_tokens: int
) -> list[ConversationTurn]:
    """Return the last turns whose combined token count is ≤ n_tokens."""
    result: list[ConversationTurn] = []
    total = 0
    for turn in reversed(turns):
        t = _estimate_tokens(f"[{turn.role.upper()}]\n{turn.content}")
        if total + t > n_tokens:
            break
        result.insert(0, turn)
        total += t
    return result
