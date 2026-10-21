"""Run a suite: render prompts, call the provider, check assertions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Union

from .assertions import AssertionResult, check_assertions
from .judge import LLMJudge
from .providers import MockProvider, OpenAICompatibleProvider
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
    def usage_estimated(self) -> bool:
        return any(c.usage_estimated for c in self.cases)

    @property
    def ok(self) -> bool:
        return self.failed_count == 0


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


def run_suite(suite: Suite, *, mock: bool = False) -> RunReport:
    """Execute every case in *suite* and return a :class:`RunReport`."""
    provider = make_provider(suite, mock=mock)
    # Built once per run; only used by llm_judge assertions, and an
    # unconfigured judge skips instead of failing (see judge.py).
    judge = LLMJudge.from_env()
    report = RunReport(
        suite_name=suite.name,
        provider=provider.name,
        model="mock" if mock else suite.model.name,
    )
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
        results = check_assertions(completion.text, case.assertions, judge=judge)
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
    return report
