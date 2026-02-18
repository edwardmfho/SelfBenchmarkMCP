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
        if sec.get("manual_time") and sec.get("agentic_time"):
            score_badge = f'<span class="score">-{sec.get("savings")}h</span>'
        else:
            score = sec.get("score")
            score_badge = (
                f'<span class="score">{score}</span>' if score is not None else ""
            )

        sections_html += f"""
        <div class="card">
          <div class="card-title">{title} {score_badge}</div>
          <div class="card-body">{content}</div>
        </div>"""

    findings_html = "".join(f"<li>{html.escape(str(f))}</li>" for f in key_findings)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Scorecard — {work_type}</title>
<style>
  body {{ background: #0f172a; color: #f8fafc; font-family: sans-serif; padding: 20px; }}
  .container {{ max-width: 800px; margin: 0 auto; background: rgba(30, 41, 59, 0.7); border-radius: 20px; padding: 30px; border: 1px solid rgba(255,255,255,0.1); }}
  h1 {{ color: #38bdf8; margin-bottom: 10px; }}
  .summary {{ background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px; margin-bottom: 20px; }}
  .card {{ background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; margin-bottom: 10px; padding: 15px; }}
  .card-title {{ font-weight: bold; color: #818cf8; margin-bottom: 5px; }}
  .score {{ background: #38bdf8; color: white; padding: 2px 8px; border-radius: 100px; font-size: 0.8rem; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin-bottom: 8px; padding-left: 20px; position: relative; }}
  li::before {{ content: "⚡"; position: absolute; left: 0; }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 {work_type.title()} Scorecard</h1>
  <p>Analysis Type: {analysis_type} | Model: {model}</p>
  <div class="summary">{summary}</div>
  <h2>Sections</h2>
  {sections_html}
  <h2>Key Findings</h2>
  <ul>{findings_html}</ul>
</div>
<script id="scorecard-data" type="application/json">{data_json}</script>
</body>
</html>"""
