"""Gmail API client using OAuth2."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".config" / "conversation-analyser" / "gmail"
_CREDENTIALS_FILE = _CONFIG_DIR / "credentials.json"
_TOKEN_FILE = _CONFIG_DIR / "token.json"

_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_service() -> Any:
    """Build and return an authenticated Gmail API service object."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "Gmail dependencies not installed. Run: "
            "pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client"
        ) from exc

    creds = None
    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {_CREDENTIALS_FILE}. "
                    "Call check_credential_status for setup instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CREDENTIALS_FILE), _SCOPES
            )
            creds = flow.run_local_server(port=0)

        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict[str, Any]) -> str:
    """Recursively extract plain-text or HTML body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data + "==").decode(
            "utf-8", errors="replace"
        )

    # Fallback to HTML if plain text missing, but convert to something readable-ish
    if mime_type == "text/html" and body_data:
        import re as _re

        html = base64.urlsafe_b64decode(body_data + "==").decode(
            "utf-8", errors="replace"
        )
        # Very crude HTML to text conversion
        text = _re.sub(r"<[^>]+>", " ", html)
        text = _re.sub(r"\s+", " ", text).strip()
        return text

    for part in payload.get("parts", []):
        text = _decode_body(part)
        if text:
            return text
    return ""


def _parse_headers(headers: list[dict]) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in headers}


def fetch_thread(thread_id: str, include_body: bool = True) -> dict[str, Any]:
    """Fetch a Gmail thread by ID and return structured data."""
    service = _get_service()
    thread = (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )

    messages_out = []
    participants: set[str] = set()
    dates: list[str] = []

    for msg in thread.get("messages", []):
        headers = _parse_headers(msg.get("payload", {}).get("headers", []))
        sender = headers.get("from", "unknown")
        recipients = [r.strip() for r in headers.get("to", "").split(",") if r.strip()]
        date = headers.get("date", "")
        subject = headers.get("subject", "(no subject)")
        snippet = msg.get("snippet", "")

        participants.add(sender)
        participants.update(recipients)
        if date:
            dates.append(date)

        body_text = _decode_body(msg.get("payload", {})) if include_body else ""

        messages_out.append(
            {
                "message_id": msg["id"],
                "thread_id": thread_id,
                "subject": subject,
                "sender": sender,
                "recipients": recipients,
                "date": date,
                "body_text": body_text,
                "snippet": snippet,
            }
        )

    subject = messages_out[0]["subject"] if messages_out else "(no subject)"
    date_range = (min(dates, default=""), max(dates, default=""))

    return {
        "thread_id": thread_id,
        "subject": subject,
        "participants": sorted(participants),
        "messages": messages_out,
        "date_range": date_range,
        "message_count": len(messages_out),
    }


def search_threads(
    query: str, max_results: int = 10, include_body: bool = True
) -> list[dict[str, Any]]:
    """Search Gmail threads and return structured data."""
    service = _get_service()
    response = (
        service.users()
        .threads()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    threads = response.get("threads", [])
    results = []
    for t in threads:
        try:
            results.append(fetch_thread(t["id"], include_body=include_body))
        except Exception as exc:
            logger.warning("Failed to fetch thread %s: %s", t["id"], exc)
    return results
