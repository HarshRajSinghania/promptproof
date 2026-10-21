"""Human-readable console report and machine-readable JSON report."""

from __future__ import annotations

import json
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
            if not result.passed:
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
                    {"kind": r.kind, "passed": r.passed, "detail": r.detail}
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
