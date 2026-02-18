# Conversation Analyser MCP Servers

Two MCP servers that analyse conversations using **MCP Sampling** — the LLM runs in your client (Claude Desktop), not on the server.

## Servers

| Server | Entry point | Purpose |
|---|---|---|
| `conversation-analyser` | `servers/analyser/server.py` | Analyse conversation files |
| `gmail-fetcher` | `servers/gmail/server.py` | Fetch Gmail threads |

## Quick Start

### 1. Install

**Option A: Run without installing (Recommended)**
You can run the servers directly using `uvx`. Note the trailing command name:

```bash
# Analyser
uvx --quiet --from git+https://github.com/edwardmfho/SelfBenchmarkMCP.git#subdirectory=conversation-analyser \
  conversation-analyser

# Gmail Fetcher (includes required [gmail] dependencies)
uvx --quiet --from "conversation-analyser-mcp[gmail] @ git+https://github.com/edwardmfho/SelfBenchmarkMCP.git#subdirectory=conversation-analyser" \
  gmail-fetcher
```

**Option B: Local Development Install**
```bash
git clone https://github.com/edwardmfho/SelfBenchmarkMCP.git
cd SelfBenchmarkMCP/conversation-analyser
uv pip install -e .
```

### 2. Add to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "conversation-analyser": {
      "command": "uvx",
      "args": [
        "--quiet",
        "--from",
        "git+https://github.com/edwardmfho/SelfBenchmarkMCP.git#subdirectory=conversation-analyser",
        "conversation-analyser"
      ]
    },
    "gmail-fetcher": {
      "command": "uvx",
      "args": [
        "--quiet",
        "--from",
        "conversation-analyser-mcp[gmail] @ git+https://github.com/edwardmfho/SelfBenchmarkMCP.git#subdirectory=conversation-analyser",
        "gmail-fetcher"
      ]
    }
  }
}
```

### 3. Analyse a conversation

In Claude Desktop, ask:
> *"Analyse the conversation at `/path/to/my/meeting.json` as a meeting summary"*

Claude will call `analyse_conversation` → chunk the file → sample the LLM → return an interactive HTML scorecard.

---

## Conversation Analyser Tools

| Tool | Description |
|---|---|
| `list_work_types` | See available work types |
| `save_work_type` | Create a custom work type (first-time setup) |
| `list_analysis_types` | See analysis modes |
| `analyse_conversation` | Run analysis → returns HTML scorecard |

### Supported file formats
- **JSON** — OpenAI `[{"role":"user","content":"..."}]` or Anthropic format
- **Markdown** — `## User` / `## Assistant` headers
- **Plain text** — treated as a single user turn

### Work types (built-in)
`meeting` · `deliverables` · `strategy` · `board_update` · `hiring` · `brainstorm` · `customer_call`

### Analysis types
`summary` · `sentiment` · `key_topics` · `action_items` · `custom`

---

## Gmail Fetcher Tools

| Tool | Description |
|---|---|
| `check_credential_status` | Check OAuth2 setup (returns guide if not configured) |
| `search_threads` | Search Gmail with a query string |
| `fetch_thread` | Fetch a specific thread by ID |
| `schedule_credential_destruction` | Auto-delete credentials at a datetime |
| `destroy_credentials_now` | Immediately delete credentials |

### Gmail setup
Run `check_credential_status` — if credentials are missing, it returns a full step-by-step guide for setting up Google Cloud OAuth2.

> **Security**: After your session, use `schedule_credential_destruction` to auto-delete credentials.

---

## Customising Prompts

Edit [`prompts/prompts.md`](prompts/prompts.md) to tune how the LLM analyses conversations. The server hot-reloads this file — no restart needed.

## Scorecard Template

Edit [`templates/scorecard.html`](templates/scorecard.html) to customise the visual design. The server injects JSON data via the `<!-- INJECT: data_json -->` placeholder.

## Sample Files

- [`examples/sample_meeting.json`](examples/sample_meeting.json) — a sample meeting transcript for testing

---

## Context Size Handling

For large conversations, the server automatically:
1. Splits into overlapping chunks (~2000 tokens each, 10% overlap)
2. Analyses each chunk via MCP Sampling
3. Synthesises all partial results via a final MCP Sampling call
4. Builds the HTML scorecard from the synthesis

All LLM calls use `sampling/createMessage` — the server never calls an LLM API directly.
