"""Console, JSON, and self-contained HTML reports for a suite run."""

from __future__ import annotations

import html as html_lib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .runner import RunReport


def render_console(report: RunReport) -> str:
    """Render *report* as a plain-text table suitable for CI logs."""
    lines: list[str] = []
    lines.append(f"PromptProof — suite: {report.suite_name}")
    lines.append(f"provider: {report.provider}   model: {report.model}")
    lines.append("-" * 72)
    name_width = max([len(c.name) for c in report.cases] + [4])
    header = f"{'CASE':<{name_width}}  {'RESULT':<6}  {'TIME':>8}  {'TOKENS':>6}"
    lines.append(header)
    lines.append("-" * len(header))
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        lines.append(
            f"{case.name:<{name_width}}  {status:<6}  "
            f"{case.duration_ms:>6.0f}ms  {case.total_tokens:>6}"
        )
        if case.error:
            lines.append(f"    error: {case.error}")
        for result in case.assertions:
            if result.skipped:
                lines.append(f"    ⊘ {result.kind}: {result.detail}")
            elif not result.passed:
                lines.append(f"    ✗ {result.kind}: {result.detail}")
    lines.append("-" * len(header))
    usage_note = " (estimated)" if report.usage_estimated else ""
    lines.append(
        f"{report.passed_count} passed, {report.failed_count} failed, "
        f"{len(report.cases)} total — {report.total_tokens} tokens{usage_note}"
    )
    return "\n".join(lines)


def report_to_dict(report: RunReport) -> dict[str, Any]:
    """Serialize *report* to the stable JSON report shape."""
    return {
        "tool": "promptproof",
        "version": __version__,
        "suite": report.suite_name,
        "provider": report.provider,
        "model": report.model,
        "summary": {
            "passed": report.passed_count,
            "failed": report.failed_count,
            "total": len(report.cases),
            "total_tokens": report.total_tokens,
            "usage_estimated": report.usage_estimated,
        },
        "cases": [
            {
                "name": case.name,
                "passed": case.passed,
                "duration_ms": round(case.duration_ms, 2),
                "prompt": case.prompt,
                "response": case.response,
                "error": case.error or None,
                "usage": {
                    "prompt_tokens": case.prompt_tokens,
                    "completion_tokens": case.completion_tokens,
                    "total_tokens": case.total_tokens,
                    "estimated": case.usage_estimated,
                },
                "assertions": [
                    {"kind": r.kind, "passed": r.passed, "detail": r.detail, "skipped": r.skipped}
                    for r in case.assertions
                ],
            }
            for case in report.cases
        ],
    }


def write_json_report(report: RunReport, path: str | Path) -> None:
    """Write the JSON report for *report* to *path*."""
    Path(path).write_text(
        json.dumps(report_to_dict(report), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


_HTML_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
       color: #111; background: #fff; margin: 0; padding: 32px 16px; }
.wrap { max-width: 960px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: #555; font-size: 14px; margin-bottom: 16px; }
.summary { display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0 24px; }
.pill { border: 1px solid #ddd; border-radius: 999px; padding: 6px 14px; font-size: 14px; }
.pill.pass { background: #e6f4ea; border-color: #b7e0c1; }
.pill.fail { background: #fdecea; border-color: #f5c6c0; }
.case { border: 1px solid #e5e5e5; border-radius: 12px; padding: 16px 18px; margin-bottom: 12px; }
.case-head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.case-name { font-size: 16px; font-weight: 600; }
.badge { font-size: 12px; font-weight: 700; border-radius: 6px; padding: 2px 8px; }
.badge.pass { background: #1a7f37; color: #fff; }
.badge.fail { background: #cf222e; color: #fff; }
.case-stats { color: #555; font-size: 13px; margin-left: auto; }
.error { color: #cf222e; font-size: 14px; margin: 8px 0 0; }
.assertions { margin: 10px 0 0; padding: 0; list-style: none; font-size: 14px; }
.assertions li { padding: 3px 0; }
.a-pass { color: #1a7f37; }
.a-fail { color: #cf222e; }
.a-skip { color: #9a6700; }
.detail { color: #555; }
details { margin-top: 10px; font-size: 13px; }
summary { cursor: pointer; color: #555; }
pre { background: #f6f6f6; border: 1px solid #eee; border-radius: 8px; padding: 12px;
      overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
footer { color: #888; font-size: 12px; margin-top: 28px; }
"""


def render_html(report: RunReport) -> str:
    """Render *report* as a self-contained HTML page (inline CSS, no assets)."""
    esc = html_lib.escape
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    usage_note = " (estimated)" if report.usage_estimated else ""

    case_blocks: list[str] = []
    for case in report.cases:
        status = "pass" if case.passed else "fail"
        badge = f'<span class="badge {status}">{status.upper()}</span>'
        stats = f"{case.duration_ms:.0f}ms · {case.total_tokens} tokens"
        block = [
            '<section class="case">',
            f'<div class="case-head">{badge}<span class="case-name">{esc(case.name)}</span>'
            f'<span class="case-stats">{stats}</span></div>',
        ]
        if case.error:
            block.append(f'<p class="error">error: {esc(case.error)}</p>')
        if case.assertions:
            items = []
            for result in case.assertions:
                if result.skipped:
                    cls, mark = "a-skip", "⊘"
                elif result.passed:
                    cls, mark = "a-pass", "✓"
                else:
                    cls, mark = "a-fail", "✗"
                line = f'<span class="{cls}">{mark} {esc(result.kind)}</span>'
                if result.detail:
                    line += f' <span class="detail">{esc(result.detail)}</span>'
                items.append(f"<li>{line}</li>")
            block.append('<ul class="assertions">' + "".join(items) + "</ul>")
        if case.prompt or case.response:
            block.append(
                "<details><summary>prompt &amp; response</summary>"
                f"<h4>prompt</h4><pre>{esc(case.prompt)}</pre>"
                f"<h4>response</h4><pre>{esc(case.response)}</pre></details>"
            )
        block.append("</section>")
        case_blocks.append("\n".join(block))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PromptProof report — {esc(report.suite_name)}</title>
<style>{_HTML_CSS}</style>
</head>
<body>
<div class="wrap">
<h1>PromptProof report</h1>
<div class="meta">suite: {esc(report.suite_name)} · provider: {esc(report.provider)} ·
model: {esc(report.model)} · generated {generated}</div>
<div class="summary">
<span class="pill pass">{report.passed_count} passed</span>
<span class="pill fail">{report.failed_count} failed</span>
<span class="pill">{len(report.cases)} total</span>
<span class="pill">{report.total_tokens} tokens{esc(usage_note)}</span>
</div>
{chr(10).join(case_blocks)}
<footer>Generated by PromptProof {esc(__version__)} — snapshot &amp; regression testing for LLM prompts.</footer>
</div>
</body>
</html>
"""


def write_html_report(report: RunReport, path: str | Path) -> None:
    """Write the HTML report for *report* to *path*."""
    Path(path).write_text(render_html(report) + "\n", encoding="utf-8")
