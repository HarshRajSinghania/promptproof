"""llm_judge tests — all offline, via an injected fake transport."""

import pytest

from promptproof.assertions import check_assertions
from promptproof.errors import AssertionConfigError
from promptproof.judge import JudgeConfig, LLMJudge
from promptproof.runner import run_suite
from promptproof.suite import load_suite

JUDGE_ENV = ("PROMPTPROOF_JUDGE_BASE_URL", "PROMPTPROOF_JUDGE_MODEL", "PROMPTPROOF_JUDGE_API_KEY")


class FakeTransport:
    """Records prompts, returns a canned judge reply (or raises)."""

    def __init__(self, reply="", exc=None):
        self.reply = reply
        self.exc = exc
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if self.exc is not None:
            raise self.exc
        return self.reply


def configured_judge(transport):
    config = JudgeConfig(base_url="http://judge.invalid/v1", model="judge-model")
    return LLMJudge(config, transport=transport)


def unconfigured_judge(transport):
    return LLMJudge(JudgeConfig(), transport=transport)


# --- verdict parsing through the assertion ---------------------------------


def test_judge_yes_passes_with_reason():
    transport = FakeTransport('{"verdict": "yes", "reason": "polite and on-topic"}')
    results = check_assertions(
        "Thanks! Here is the summary you asked for.",
        [{"llm_judge": "the response is polite and answers the question"}],
        judge=configured_judge(transport),
    )
    assert len(results) == 1
    result = results[0]
    assert result.kind == "llm_judge"
    assert result.passed and not result.skipped
    assert "polite and on-topic" in result.detail
    # The judge saw both the criterion and the response being graded.
    assert "the response is polite" in transport.prompts[0]
    assert "Thanks! Here is the summary" in transport.prompts[0]


def test_judge_no_fails_with_reason():
    transport = FakeTransport('{"verdict": "no", "reason": "rude and off-topic"}')
    results = check_assertions(
        "Whatever. Figure it out yourself.",
        [{"llm_judge": "the response is polite"}],
        judge=configured_judge(transport),
    )
    assert not results[0].passed
    assert not results[0].skipped
    assert "rude and off-topic" in results[0].detail


def test_judge_accepts_fenced_json_and_bare_yes():
    fenced = FakeTransport('```json\n{"verdict": "yes", "reason": "fine"}\n```')
    judge = configured_judge(fenced)
    assert judge.evaluate("any criterion", "any response").passed

    bare = FakeTransport("Yes — it directly answers the question.")
    judge = configured_judge(bare)
    verdict = judge.evaluate("any criterion", "any response")
    assert verdict.passed
    assert "directly answers" in verdict.reason


def test_judge_unparseable_reply_fails_not_crashes():
    judge = configured_judge(FakeTransport("the response seems okay to me"))
    verdict = judge.evaluate("any criterion", "any response")
    assert not verdict.passed
    assert "unparseable" in verdict.reason


def test_judge_transport_error_fails_not_crashes():
    judge = configured_judge(FakeTransport(exc=RuntimeError("connection refused")))
    verdict = judge.evaluate("any criterion", "any response")
    assert not verdict.passed
    assert "judge request failed" in verdict.reason


# --- not configured: skip gracefully ----------------------------------------


def test_judge_not_configured_skips_without_calling_transport():
    transport = FakeTransport('{"verdict": "no", "reason": "must never be seen"}')
    results = check_assertions(
        "anything",
        [{"llm_judge": "the response is polite"}],
        judge=unconfigured_judge(transport),
    )
    result = results[0]
    assert result.skipped
    assert result.passed  # skipped must not fail the case
    assert "skipped" in result.detail
    assert "PROMPTPROOF_JUDGE_BASE_URL" in result.detail
    assert transport.prompts == []  # judge endpoint was never called


def test_judge_config_from_env(monkeypatch):
    for var in JUDGE_ENV:
        monkeypatch.delenv(var, raising=False)
    assert not LLMJudge.from_env().config.configured

    monkeypatch.setenv("PROMPTPROOF_JUDGE_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("PROMPTPROOF_JUDGE_MODEL", "gpt-4o-mini")
    config = LLMJudge.from_env().config
    assert config.configured
    assert config.model == "gpt-4o-mini"


def test_suite_with_llm_judge_runs_green_when_judge_unconfigured(tmp_path, monkeypatch):
    for var in JUDGE_ENV:
        monkeypatch.delenv(var, raising=False)
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
name: judge-demo
prompt: "Answer politely"
mock:
  default: "Of course, happy to help."
cases:
  - name: polite
    assertions:
      - contains: happy
      - llm_judge: "the response is polite"
""",
        encoding="utf-8",
    )
    report = run_suite(load_suite(suite_file), mock=True)
    assert report.ok
    judge_result = report.cases[0].assertions[1]
    assert judge_result.skipped and judge_result.passed


# --- assertion value forms ----------------------------------------------------


def test_judge_mapping_form_with_model_override():
    transport = FakeTransport('{"verdict": "yes", "reason": "ok"}')
    judge = configured_judge(transport)
    results = check_assertions(
        "a response",
        [{"llm_judge": {"criterion": "it is fine", "model": "bigger-judge"}}],
        judge=judge,
    )
    assert results[0].passed
    assert "it is fine" in transport.prompts[0]


def test_judge_mapping_form_requires_criterion():
    with pytest.raises(AssertionConfigError, match="criterion"):
        check_assertions(
            "a response",
            [{"llm_judge": {"model": "judge-model"}}],
            judge=configured_judge(FakeTransport()),
        )


def test_judge_empty_criterion_raises():
    with pytest.raises(AssertionConfigError, match="non-empty"):
        check_assertions(
            "a response",
            [{"llm_judge": "  "}],
            judge=configured_judge(FakeTransport()),
        )
