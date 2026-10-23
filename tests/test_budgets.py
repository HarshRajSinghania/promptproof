"""Tests for suite-level cost budgets (limits / pricing)."""

import textwrap

import pytest

from promptproof.runner import run_suite
from promptproof.suite import load_suite

_SUITE_TEMPLATE = """\
name: budget-demo
prompt: "Say: {{word}}"
pricing:
  input_per_1k: 0.15
  output_per_1k: 0.60
limits:
  max_tokens: {max_tokens}
  max_usd: {max_usd}
mock:
  default: "hello"
cases:
  - name: one
    vars: {word: "hi"}
    assertions:
      - contains: "hello"
"""


def _write_suite(tmp_path, max_tokens=None, max_usd=None) -> str:
    limit_lines = []
    if max_tokens is not None:
        limit_lines.append(f"  max_tokens: {max_tokens}")
    if max_usd is not None:
        limit_lines.append(f"  max_usd: {max_usd}")
    if limit_lines:
        body = textwrap.dedent(_SUITE_TEMPLATE).replace(
            "limits:\n  max_tokens: {max_tokens}\n  max_usd: {max_usd}",
            "limits:\n" + "\n".join(limit_lines),
        )
    else:
        body = textwrap.dedent(_SUITE_TEMPLATE).replace(
            "limits:\n  max_tokens: {max_tokens}\n  max_usd: {max_usd}\n", ""
        )
    path = tmp_path / "budget.yaml"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_limits_and_pricing_parsed(tmp_path):
    suite = load_suite(_write_suite(tmp_path, max_tokens=500, max_usd=0.01))
    assert suite.limits.max_tokens == 500
    assert suite.limits.max_usd == pytest.approx(0.01)
    assert suite.pricing.input_per_1k == pytest.approx(0.15)
    assert suite.pricing.output_per_1k == pytest.approx(0.60)


def test_no_limits_by_default(tmp_path):
    suite = load_suite(_write_suite(tmp_path))
    assert suite.limits.max_tokens is None
    assert suite.limits.max_usd is None


def test_cost_estimated_and_run_ok_within_budget(tmp_path):
    report = run_suite(
        load_suite(_write_suite(tmp_path, max_tokens=100_000, max_usd=1.0)),
        mock=True,
    )
    assert report.ok
    assert report.budget_error == ""
    # prompt "Say: hi" + completion "hello" at chars/4 estimates
    assert report.total_prompt_tokens > 0
    assert report.estimated_cost_usd > 0
    assert report.cost_estimated is True  # mock usage is estimated


def test_token_budget_exceeded_fails_run(tmp_path):
    report = run_suite(
        load_suite(_write_suite(tmp_path, max_tokens=1)),  # impossibly small
        mock=True,
    )
    assert not report.ok
    assert "token budget exceeded" in report.budget_error


def test_cost_budget_exceeded_fails_run(tmp_path):
    report = run_suite(
        load_suite(_write_suite(tmp_path, max_usd=0.0000001)),
        mock=True,
    )
    assert not report.ok
    assert "cost budget exceeded" in report.budget_error


def test_cost_estimate_math():
    from promptproof.runner import estimate_cost_usd, RunReport, CaseResult

    report = RunReport(suite_name="x", provider="mock", model="mock")
    report.cases.append(
        CaseResult(
            name="c", passed=True, duration_ms=1.0, prompt="p", response="r",
            prompt_tokens=1000, completion_tokens=500,
        )
    )
    from promptproof.suite import Suite, Pricing

    suite = Suite(
        name="x", prompt="p",
        pricing=Pricing(input_per_1k=1.0, output_per_1k=2.0),
    )
    assert estimate_cost_usd(report, suite) == pytest.approx(2.0)


def test_zero_pricing_means_zero_cost(tmp_path):
    path = tmp_path / "noprice.yaml"
    path.write_text(
        "name: noprice\nprompt: \"Hi {{x}}\"\n"
        "limits:\n  max_usd: 0.0\n"
        "mock:\n  default: ok\n"
        "cases:\n  - name: one\n    vars: {x: 1}\n    assertions: []\n",
        encoding="utf-8",
    )
    report = run_suite(load_suite(path), mock=True)
    assert report.estimated_cost_usd == 0.0
    assert report.ok  # 0 > 0 is False, so the zero budget is not breached
