"""FastMCP server — Gmail Fetcher with credential management."""

import logging

from mcp.server.fastmcp import FastMCP

from . import credential_manager, gmail_client
from .models import (
    CredentialStatus,
    FetchThreadInput,
    GmailMessage,
    GmailThread,
    ScheduleDestructionInput,
    SearchThreadsInput,
)

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="gmail-fetcher",
    instructions=(
        "Fetch Gmail conversations for analysis. "
        "Start with `check_credential_status` — if credentials are missing, "
        "it will return a step-by-step setup guide."
    ),
)

# Check for any due scheduled destruction on startup
credential_manager.check_and_run_scheduled_destruction()


@mcp.tool()
def check_credential_status() -> CredentialStatus:
    """
    Check Gmail OAuth2 credential status.

    If credentials are not configured, returns a detailed setup guide
    explaining how to obtain them from Google Cloud Console.
    Also shows whether credential auto-destruction is scheduled.
    """
    return CredentialStatus(**credential_manager.get_credential_status())


@mcp.tool()
def schedule_credential_destruction(input: ScheduleDestructionInput) -> dict:
    """
    Schedule automatic deletion of Gmail credentials at a specific datetime.

    Recommended after completing your analysis session to protect your account.
    The destruction runs when the server starts after the scheduled time.

    Example: schedule for 24 hours from now to auto-clean up overnight.
    """
    if not input.confirm:
        return {
            "error": "confirmation_required",
            "message": "Set confirm=True to schedule credential destruction.",
        }
    return credential_manager.schedule_destruction(input.destroy_at)


@mcp.tool()
def destroy_credentials_now() -> dict:
    """
    Immediately delete all Gmail credential files (credentials.json and token.json).

    Use this when you are done with your Gmail analysis session and want to
    immediately revoke local access. You will need to re-authorise next time.
    """
    return credential_manager.destroy_credentials_now()


@mcp.tool()
def fetch_thread(input: FetchThreadInput) -> GmailThread:
    """
    Fetch a Gmail thread by its thread ID.

    Returns the full thread with all messages, participants, and body text.
    Pass the result's thread_id to the conversation-analyser server to analyse it.
    """
    data = gmail_client.fetch_thread(input.thread_id, include_body=input.include_body)
    messages = [GmailMessage(**m) for m in data["messages"]]
    return GmailThread(
        thread_id=data["thread_id"],
        subject=data["subject"],
        participants=data["participants"],
        messages=messages,
        date_range=tuple(data["date_range"]),  # type: ignore[arg-type]
        message_count=data["message_count"],
    )


@mcp.tool()
def search_threads(input: SearchThreadsInput) -> list:
    """
    Search Gmail threads using a Gmail search query.

    Examples:
    - 'from:alice@example.com subject:Q1 review'
    - 'label:important after:2026/01/01'
    - 'to:me is:unread'

    Returns a list of threads. Pass any thread to the conversation-analyser
    server for analysis.
    """
    threads_data = gmail_client.search_threads(
        input.query,
        max_results=input.max_results,
        include_body=input.include_body,
    )
    results: list[GmailThread] = []
    for data in threads_data:
        messages = [GmailMessage(**m) for m in data["messages"]]
        results.append(
            GmailThread(
                thread_id=data["thread_id"],
                subject=data["subject"],
                participants=data["participants"],
                messages=messages,
                date_range=tuple(data["date_range"]),  # type: ignore[arg-type]
                message_count=data["message_count"],
            )
        )
    return results


@mcp.tool()
def get_benchmark_data(days: int = 7) -> list:
    """
    Fetch all email threads from the last X days for personal benchmarking.

    This tool is a convenience wrapper around search_threads. It automatically
    generates the 'after:YYYY/MM/DD' query for the specified number of days.

    Args:
        days: Number of recent days to include (default 7)
    """
    from datetime import datetime, timedelta

    after_date = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"after:{after_date}"

    threads_data = gmail_client.search_threads(
        query,
        max_results=50,  # Reasonable limit for benchmark
        include_body=True,
    )

    results: list[GmailThread] = []
    for data in threads_data:
        messages = [GmailMessage(**m) for m in data["messages"]]
        results.append(
            GmailThread(
                thread_id=data["thread_id"],
                subject=data["subject"],
                participants=data["participants"],
                messages=messages,
                date_range=tuple(data["date_range"]),  # type: ignore[arg-type]
                message_count=data["message_count"],
            )
        )
    return results


def main() -> None:
    """Entry point — run in stdio mode."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
