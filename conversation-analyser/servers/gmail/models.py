"""Pydantic BaseModel definitions for the Gmail Fetcher MCP server."""

from __future__ import annotations


from pydantic import BaseModel, Field

from servers.analyser.models import ConversationTurn


# ---------------------------------------------------------------------------
# Credential management
# ---------------------------------------------------------------------------


class CredentialStatus(BaseModel):
    """Status of Gmail OAuth2 credentials."""

    configured: bool = Field(description="True if credentials are present and valid")
    credential_path: str | None = Field(
        default=None, description="Absolute path to credentials.json"
    )
    token_path: str | None = Field(
        default=None, description="Absolute path to token.json (OAuth2 token)"
    )
    expires_at: str | None = Field(
        default=None, description="ISO-8601 datetime when the token expires"
    )
    destruction_scheduled: bool = Field(
        default=False,
        description="True if a scheduled credential destruction job is active",
    )
    destruction_at: str | None = Field(
        default=None,
        description="ISO-8601 datetime when credentials will be auto-destroyed",
    )
    setup_guide: str | None = Field(
        default=None,
        description="Step-by-step Markdown guide shown when credentials are missing",
    )


class ScheduleDestructionInput(BaseModel):
    """Input for scheduling credential destruction."""

    destroy_at: str = Field(
        description="ISO-8601 datetime when credentials should be destroyed, e.g. '2026-02-20T18:00:00+11:00'"
    )
    confirm: bool = Field(
        default=False,
        description="Must be True to confirm the destructive action",
    )


# ---------------------------------------------------------------------------
# Gmail data
# ---------------------------------------------------------------------------


class GmailMessage(BaseModel):
    """A single email message."""

    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipients: list[str]
    date: str = Field(description="ISO-8601 date string")
    body_text: str = Field(description="Plain-text body of the email")
    snippet: str = Field(description="Short preview snippet")


class GmailThread(BaseModel):
    """An email thread (conversation) fetched from Gmail."""

    thread_id: str
    subject: str
    participants: list[str]
    messages: list[GmailMessage]
    date_range: tuple[str, str] = Field(
        description="(earliest_date, latest_date) ISO-8601 strings"
    )
    message_count: int

    def to_conversation_turns(self) -> list[ConversationTurn]:
        """Convert Gmail thread to ConversationTurn list for the analyser."""
        turns: list[ConversationTurn] = []
        for msg in self.messages:
            role = "user"  # Treat all emails as user turns for analysis
            content = (
                f"From: {msg.sender}\n"
                f"To: {', '.join(msg.recipients)}\n"
                f"Date: {msg.date}\n"
                f"Subject: {msg.subject}\n\n"
                f"{msg.body_text}"
            )
            turns.append(ConversationTurn(role=role, content=content))
        return turns


class SearchThreadsInput(BaseModel):
    """Input for searching Gmail threads."""

    query: str = Field(
        description="Gmail search query, e.g. 'from:alice@example.com subject:Q1 review'"
    )
    max_results: int = Field(
        default=10, ge=1, le=50, description="Maximum number of threads to return"
    )
    include_body: bool = Field(
        default=True, description="Whether to include full email body text"
    )


class FetchThreadInput(BaseModel):
    """Input for fetching a specific Gmail thread."""

    thread_id: str = Field(description="Gmail thread ID")
    include_body: bool = Field(default=True)
