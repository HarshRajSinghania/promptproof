"""Run a suite: render prompts, call the provider, check assertions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from .assertions import AssertionResult, check_assertions
from .judge import LLMJudge
from .providers import MockProvider, OpenAICompatibleProvider
from .snapshots import default_snapshot_path, load_goldens, save_goldens
from .suite import Suite
from .template import render_template

Provider = Union[MockProvider, OpenAICompatibleProvider]


@dataclass
class CaseResult:
    name: str
    passed: bool
    duration_ms: float
    prompt: str
    response: str
    assertions: list[AssertionResult] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usage_estimated: bool = False
    error: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class RunReport:
    suite_name: str
    provider: str
    model: str
    cases: list[CaseResult] = field(default_factory=list)
    estimated_cost_usd: float = 0.0
    cost_estimated: bool = False
    budget_error: str = ""

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def failed_count(self) -> int:
        return len(self.cases) - self.passed_count

    @property
    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.cases)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.cases)

    @property
    def total_completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.cases)

    @property
    def usage_estimated(self) -> bool:
        return any(c.usage_estimated for c in self.cases)

    @property
    def ok(self) -> bool:
        return self.failed_count == 0 and not self.budget_error


def make_provider(suite: Suite, *, mock: bool) -> Provider:
    """Build the provider for a run (mock for offline, HTTP otherwise)."""
    if mock:
        return MockProvider(suite.mock)
    return OpenAICompatibleProvider(
        base_url=suite.model.base_url,
        model=suite.model.name,
        api_key_env=suite.model.api_key_env,
        temperature=suite.model.temperature,
    )


def snapshot_path(suite: Suite) -> Path | str:
    """Resolve the golden-file path for *suite* (explicit or default)."""
    if suite.snapshot_file:
        return Path(suite.snapshot_file)
    return default_snapshot_path(suite.source or f"{suite.name}.yaml")


def _check_snapshot(response: str, golden: str) -> AssertionResult:
    """Diff a response against its golden value."""
    if response == golden:
        return AssertionResult("snapshot", True, "matches golden snapshot")
    return AssertionResult(
        "snapshot",
        False,
        f"response differs from golden snapshot ({len(response)} chars "
        f"vs golden {len(golden)} chars); re-run with --record to update",
    )


def run_suite(
    suite: Suite, *, mock: bool = False, record: bool = False
) -> RunReport:
    """Execute every case in *suite* and return a :class:`RunReport`.

    With ``record=True`` each snapshot-enabled case's response is written to
    the golden file instead of being diffed, and the run exits green (cases
    that error still fail).
    """
    provider = make_provider(suite, mock=mock)
    # Built once per run; only used by llm_judge assertions, and an
    # unconfigured judge skips instead of failing (see judge.py).
    judge = LLMJudge.from_env()
    report = RunReport(
        suite_name=suite.name,
        provider=provider.name,
        model="mock" if mock else suite.model.name,
    )
    goldens: dict[str, str] = {} if record else load_goldens(snapshot_path(suite))
    recorded: dict[str, str] = {}
    for case in suite.cases:
        started = time.perf_counter()
        prompt = render_template(suite.prompt, case.vars)
        try:
            completion = provider.complete(prompt, case_mock_response=case.mock_response)
        except Exception as exc:  # provider errors fail the case, not the run
            report.cases.append(
                CaseResult(
                    name=case.name,
                    passed=False,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    prompt=prompt,
                    response="",
                    error=str(exc),
                )
            )
            continue
        if record:
            recorded[case.name] = completion.text
            report.cases.append(
                CaseResult(
                    name=case.name,
                    passed=True,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    prompt=prompt,
                    response=completion.text,
                    prompt_tokens=completion.prompt_tokens,
                    completion_tokens=completion.completion_tokens,
                    usage_estimated=completion.usage_estimated,
                )
            )
            continue
        results = check_assertions(completion.text, case.assertions, judge=judge)
        if case.snapshot:
            golden = goldens.get(case.name)
            if golden is None:
                report.cases.append(
                    CaseResult(
                        name=case.name,
                        passed=False,
                        duration_ms=(time.perf_counter() - started) * 1000,
                        prompt=prompt,
                        response=completion.text,
                        assertions=results,
                        prompt_tokens=completion.prompt_tokens,
                        completion_tokens=completion.completion_tokens,
                        usage_estimated=completion.usage_estimated,
                        error=(
                            f"no golden snapshot for case {case.name!r}; "
                            "run with --record to create it"
                        ),
                    )
                )
                continue
            results.append(_check_snapshot(completion.text, golden))
        report.cases.append(
            CaseResult(
                name=case.name,
                passed=all(r.passed for r in results),
                duration_ms=(time.perf_counter() - started) * 1000,
                prompt=prompt,
                response=completion.text,
                assertions=results,
                prompt_tokens=completion.prompt_tokens,
                completion_tokens=completion.completion_tokens,
                usage_estimated=completion.usage_estimated,
            )
        )
    if record:
        save_goldens(snapshot_path(suite), recorded)
    _apply_budgets(report, suite)
    return report


def estimate_cost_usd(report: RunReport, suite: Suite) -> float:
    """Estimate the run's cost in USD from the suite's per-1k-token pricing."""
    return (
        report.total_prompt_tokens * suite.pricing.input_per_1k / 1000
        + report.total_completion_tokens * suite.pricing.output_per_1k / 1000
    )


def _apply_budgets(report: RunReport, suite: Suite) -> None:
    """Fill cost fields and fail the run when a suite budget is exceeded."""
    report.estimated_cost_usd = estimate_cost_usd(report, suite)
    report.cost_estimated = report.usage_estimated
    limits = suite.limits
    if limits.max_tokens is not None and report.total_tokens > limits.max_tokens:
        report.budget_error = (
            f"token budget exceeded: {report.total_tokens} tokens > "
            f"max_tokens {limits.max_tokens}"
        )
    elif limits.max_usd is not None and report.estimated_cost_usd > limits.max_usd:
        report.budget_error = (
            f"cost budget exceeded: ${report.estimated_cost_usd:.4f} > "
            f"max_usd ${limits.max_usd:.4f}"
        )
