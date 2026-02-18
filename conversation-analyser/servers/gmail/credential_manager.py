"""Gmail OAuth2 credential manager with setup guide and scheduled destruction."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default credential storage location
_CONFIG_DIR = Path.home() / ".config" / "conversation-analyser" / "gmail"
_CREDENTIALS_FILE = _CONFIG_DIR / "credentials.json"
_TOKEN_FILE = _CONFIG_DIR / "token.json"
_SCHEDULE_FILE = _CONFIG_DIR / "destruction_schedule.json"

_SETUP_GUIDE = """
## Gmail OAuth2 Setup Guide

Follow these steps to connect the Gmail Fetcher to your Gmail account.

### Step 1 — Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **New Project**, give it a name (e.g. `conversation-analyser`), click **Create**

### Step 2 — Enable the Gmail API
1. In your project, go to **APIs & Services → Library**
2. Search for **Gmail API** and click **Enable**

### Step 3 — Create OAuth2 Credentials
1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. Choose **Desktop app** as the application type
4. Give it a name and click **Create**
5. Click **Download JSON** — this is your `credentials.json`

### Step 4 — Place the Credentials File
First, create the configuration directory by running this command in your terminal:
```bash
mkdir -p "{config_dir}"
```

Then, move the downloaded `credentials.json` to that folder:
```bash
mv ~/Downloads/credentials.json "{credentials_path}"
```

### Step 5 — Authorise (first run)
Once the file is in place, calling `fetch_thread` or any other tool will open a browser window to authorise access. This creates a `token.json` automatically.

### 🔒 Security Recommendations
- **Schedule destruction**: Use `schedule_credential_destruction` to auto-delete credentials after your session.
- **Revoke access**: Visit [Google Account Permissions](https://myaccount.google.com/permissions) to revoke access.
- **Never commit** `credentials.json` or `token.json` to version control.
""".strip()


def get_setup_guide() -> str:
    # Proactively create the directory so the user doesn't get "folder not found" errors
    # when trying to save their credentials.json manually.
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return _SETUP_GUIDE.format(
        config_dir=str(_CONFIG_DIR),
        credentials_path=str(_CREDENTIALS_FILE),
        token_path=str(_TOKEN_FILE),
    )


def get_credential_status() -> dict[str, Any]:
    """Return the current credential status as a dict."""
    import json as _json

    configured = _CREDENTIALS_FILE.exists() and _TOKEN_FILE.exists()
    expires_at = None
    if _TOKEN_FILE.exists():
        try:
            token_data = _json.loads(_TOKEN_FILE.read_text())
            expires_at = token_data.get("expiry")
        except (_json.JSONDecodeError, IOError, KeyError) as exc:
            logger.warning("Failed to parse token file: %s", exc)

    destruction_scheduled = False
    destruction_at = None
    if _SCHEDULE_FILE.exists():
        try:
            sched = _json.loads(_SCHEDULE_FILE.read_text())
            destruction_at = sched.get("destroy_at")
            destruction_scheduled = destruction_at is not None
        except (_json.JSONDecodeError, IOError, KeyError) as exc:
            logger.warning("Failed to parse destruction schedule: %s", exc)

    return {
        "configured": configured,
        "credential_path": str(_CREDENTIALS_FILE)
        if _CREDENTIALS_FILE.exists()
        else None,
        "token_path": str(_TOKEN_FILE) if _TOKEN_FILE.exists() else None,
        "expires_at": expires_at,
        "destruction_scheduled": destruction_scheduled,
        "destruction_at": destruction_at,
        "setup_guide": None if configured else get_setup_guide(),
    }


def schedule_destruction(destroy_at: str) -> dict[str, Any]:
    """Persist a destruction schedule to disk."""
    import json as _json

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _SCHEDULE_FILE.write_text(
        _json.dumps({"destroy_at": destroy_at}, indent=2),
        encoding="utf-8",
    )
    logger.info("Credential destruction scheduled for %s", destroy_at)
    return {"scheduled": True, "destroy_at": destroy_at}


def destroy_credentials_now() -> dict[str, str]:
    """Immediately delete credential and token files."""
    deleted: list[str] = []
    for path in [_CREDENTIALS_FILE, _TOKEN_FILE, _SCHEDULE_FILE]:
        if path.exists():
            path.unlink()
            deleted.append(str(path))
            logger.info("Deleted credential file: %s", path)
    return {"deleted": deleted, "status": "destroyed"}


def check_and_run_scheduled_destruction() -> bool:
    """
    Check if a scheduled destruction is due and run it.
    Returns True if destruction was performed.
    """
    import json as _json

    if not _SCHEDULE_FILE.exists():
        return False
    try:
        sched = _json.loads(_SCHEDULE_FILE.read_text())
        destroy_at_str = sched.get("destroy_at")
        if not destroy_at_str:
            return False
        destroy_at = datetime.fromisoformat(destroy_at_str)
        if datetime.now(timezone.utc) >= destroy_at.astimezone(timezone.utc):
            destroy_credentials_now()
            logger.info("Scheduled credential destruction executed")
            return True
    except Exception:
        logger.warning("Failed to check destruction schedule", exc_info=True)
    return False
