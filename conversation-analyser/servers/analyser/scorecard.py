"""HTML scorecard builder — injects analysis data into the scorecard template."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

_TEMPLATE_FILE = Path(__file__).parents[2] / "templates" / "scorecard.html"

# The template has a <script type="application/json"> element whose content is
# replaced with the real JSON payload at render time.
_INJECT_PLACEHOLDER = (
    '<script id="scorecard-data" type="application/json">null</script>'
)
_INJECT_REPLACEMENT = (
    '<script id="scorecard-data" type="application/json">{data_json}</script>'
)


def build_scorecard(
    analysis_type: str,
    work_type: str,
    synthesis_data: dict[str, Any],
    chunk_count: int,
    model_used: str,
    source_format: str,
    turn_count: int,
) -> str:
    """
    Build a self-contained HTML scorecard by injecting JSON data into the template.

    If the template file is missing, falls back to a minimal inline HTML page.
    """
    payload = {
        "analysis_type": analysis_type,
        "work_type": work_type,
        "chunk_count": chunk_count,
        "model_used": model_used,
        "source_format": source_format,
        "turn_count": turn_count,
        **synthesis_data,
    }
    data_json = json.dumps(payload, ensure_ascii=False, indent=2)

    if _TEMPLATE_FILE.exists():
        template = _TEMPLATE_FILE.read_text(encoding="utf-8")
        replacement = _INJECT_REPLACEMENT.format(data_json=data_json)
        return template.replace(_INJECT_PLACEHOLDER, replacement)

    # Fallback minimal scorecard
    return _minimal_scorecard(payload, data_json)


def _minimal_scorecard(payload: dict[str, Any], data_json: str) -> str:
    """Minimal inline HTML scorecard used when the template file is missing."""
    summary = html.escape(str(payload.get("summary", "")))
    sections = payload.get("sections", [])
    key_findings = payload.get("key_findings", [])
    work_type = html.escape(str(payload.get("work_type", "")))
    analysis_type = html.escape(str(payload.get("analysis_type", "")))
    model = html.escape(str(payload.get("model_used", "")))

    sections_html = ""
    for sec in sections:
        title = html.escape(str(sec.get("title", "")))
        content = html.escape(str(sec.get("content", "")))
        score = sec.get("score")
        score_badge = f'<span class="score">{score}</span>' if score is not None else ""
        sections_html += f"""
        <div class="card" tabindex="0">
          <div class="card-header">
            <span class="card-title">{title}</span>{score_badge}
            <span class="toggle">▼</span>
          </div>
          <div class="card-body">{content}</div>
        </div>"""

    findings_html = "".join(f"<li>{html.escape(str(f))}</li>" for f in key_findings)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Conversation Scorecard — {work_type} / {analysis_type}</title>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --border: #2d3148;
    --accent: #6c63ff; --accent2: #00d4aa; --text: #e2e8f0;
    --muted: #8892a4; --radius: 12px; --shadow: 0 4px 24px rgba(0,0,0,.4);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif;
         min-height: 100vh; padding: 2rem; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: .25rem; }}
  .meta {{ color: var(--muted); font-size: .85rem; margin-bottom: 2rem; }}
  .summary-box {{ background: var(--surface); border: 1px solid var(--border);
                  border-radius: var(--radius); padding: 1.25rem 1.5rem;
                  margin-bottom: 2rem; line-height: 1.7; box-shadow: var(--shadow); }}
  .section-title {{ font-size: 1.1rem; font-weight: 600; margin: 1.5rem 0 .75rem;
                    color: var(--accent2); letter-spacing: .03em; }}
  .card {{ background: var(--surface); border: 1px solid var(--border);
           border-radius: var(--radius); margin-bottom: .75rem;
           box-shadow: var(--shadow); overflow: hidden; cursor: pointer;
           transition: border-color .2s; }}
  .card:hover, .card:focus {{ border-color: var(--accent); outline: none; }}
  .card-header {{ display: flex; align-items: center; gap: .75rem;
                  padding: 1rem 1.25rem; user-select: none; }}
  .card-title {{ flex: 1; font-weight: 600; }}
  .score {{ background: var(--accent); color: #fff; border-radius: 20px;
            padding: .15rem .65rem; font-size: .8rem; font-weight: 700; }}
  .toggle {{ color: var(--muted); transition: transform .2s; }}
  .card.open .toggle {{ transform: rotate(180deg); }}
  .card-body {{ padding: 0 1.25rem 1rem; color: var(--muted); line-height: 1.7;
                display: none; white-space: pre-wrap; }}
  .card.open .card-body {{ display: block; }}
  ul.findings {{ list-style: none; padding: 0; }}
  ul.findings li {{ padding: .5rem 0; border-bottom: 1px solid var(--border);
                    color: var(--muted); }}
  ul.findings li::before {{ content: "→ "; color: var(--accent2); font-weight: 700; }}
  footer {{ margin-top: 3rem; color: var(--muted); font-size: .8rem; text-align: center; }}
</style>
</head>
<body>
<h1>📊 Conversation Scorecard</h1>
<p class="meta">Work type: <strong>{work_type}</strong> &nbsp;·&nbsp;
   Analysis: <strong>{analysis_type}</strong> &nbsp;·&nbsp;
   Model: <strong>{model}</strong></p>

<div class="summary-box">{summary}</div>

{'<p class="section-title">Sections</p>' + sections_html if sections_html else ""}

{'<p class="section-title">Key Findings</p><ul class="findings">' + findings_html + "</ul>" if findings_html else ""}

<footer>Generated by Conversation Analyser MCP Server</footer>

<script>
// Embed raw data for programmatic access
window.__scorecardData = {data_json};

// Accordion toggle
document.querySelectorAll('.card').forEach(card => {{
  card.addEventListener('click', () => card.classList.toggle('open'));
  card.addEventListener('keydown', e => {{
    if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); card.classList.toggle('open'); }}
  }});
}});
</script>
</body>
</html>"""
