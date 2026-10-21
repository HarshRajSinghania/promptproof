"""The ``llm_judge`` assertion backend: a second model grading a response.

Deterministic assertions (``contains``, ``regex``, …) cannot judge things
like tone, helpfulness or whether an answer actually addresses the question.
``llm_judge`` covers that gap: the suite states a criterion in plain language
and a *judge* model is asked whether the response satisfies it.

The judge endpoint is configured through environment variables only — never
through suite files, so keys stay out of version control:

===========================  ================================================
Variable                     Meaning
===========================  ================================================
``PROMPTPROOF_JUDGE_BASE_URL``  Base URL of an OpenAI-compatible endpoint
``PROMPTPROOF_JUDGE_MODEL``     Model name to grade with
``PROMPTPROOF_JUDGE_API_KEY``   API key for that endpoint
===========================  ================================================

If base URL or model is unset, the assertion *skips*: it reports itself as
skipped (not passed, not failed) so suites still run offline, in CI without
secrets, and under ``--mock``. A configured judge that errors or answers
unparseably *fails* the assertion with the reason in the detail — it never
raises into the run.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from typing import Callable, Mapping

from .providers import OpenAICompatibleProvider

#: A transport takes the judge prompt and returns the judge's raw reply.
#: Tests inject a fake one; production builds one from an
#: :class:`~promptproof.providers.OpenAICompatibleProvider`.
JudgeTransport = Callable[[str], str]

ENV_BASE_URL = "PROMPTPROOF_JUDGE_BASE_URL"
ENV_MODEL = "PROMPTPROOF_JUDGE_MODEL"
ENV_API_KEY = "PROMPTPROOF_JUDGE_API_KEY"

_JUDGE_PROMPT = """\
You are grading an LLM response against a single criterion.

Criterion: {criterion}

Response to grade:
\"\"\"
{response}
\"\"\"

Reply with JSON only, in exactly this shape:
{{"verdict": "yes", "reason": "<one short sentence>"}}
Use "yes" if the response satisfies the criterion, otherwise "no".
Keep the reason under 20 words."""


@dataclass
class JudgeConfig:
    """Where the judge lives. Empty fields mean "not configured"."""

    base_url: str = ""
    model: str = ""
    api_key_env: str = ENV_API_KEY
    timeout: float = 60.0

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "JudgeConfig":
        source = os.environ if env is None else env
        return cls(
            base_url=source.get(ENV_BASE_URL, "").strip(),
            model=source.get(ENV_MODEL, "").strip(),
        )


@dataclass
class JudgeVerdict:
    """One grading outcome. ``skipped`` means the judge never ran."""

    passed: bool
    reason: str = ""
    skipped: bool = False


def _parse_verdict(reply: str) -> JudgeVerdict:
    """Parse the judge's reply into a verdict.

    Primary shape is ``{"verdict": "yes", "reason": "..."}`` (code fences
    and surrounding prose are tolerated); a bare leading yes/no is accepted
    as a fallback. Anything else fails the assertion rather than guessing.
    """
    text = reply.strip()
    data: object = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None

    if isinstance(data, dict):
        raw_verdict = data.get("verdict", data.get("pass"))
        reason = str(data.get("reason", "")).strip()[:200]
        if isinstance(raw_verdict, bool):
            return JudgeVerdict(raw_verdict, reason)
        verdict = str(raw_verdict).strip().lower()
        if verdict in ("yes", "pass", "passed", "true"):
            return JudgeVerdict(True, reason)
        if verdict in ("no", "fail", "failed", "false"):
            return JudgeVerdict(False, reason)
    else:
        first_word = re.split(r"[\s.:]", text.lower(), maxsplit=1)[0] if text else ""
        if first_word in ("yes", "no"):
            return JudgeVerdict(first_word == "yes", text[:200])

    return JudgeVerdict(False, f"judge returned an unparseable verdict: {text[:120]!r}")


class LLMJudge:
    """Grades responses against natural-language criteria."""

    def __init__(
        self,
        config: JudgeConfig | None = None,
        *,
        transport: JudgeTransport | None = None,
    ) -> None:
        self.config = config or JudgeConfig()
        self._injected_transport = transport
        self._built_transport: JudgeTransport | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMJudge":
        return cls(JudgeConfig.from_env(env))

    def with_overrides(self, *, base_url: str = "", model: str = "") -> "LLMJudge":
        """Copy of this judge with a different endpoint and/or model.

        An explicitly injected transport is kept (tests rely on it); a
        provider built from the old config is *not* reused.
        """
        config = replace(
            self.config,
            base_url=base_url or self.config.base_url,
            model=model or self.config.model,
        )
        return LLMJudge(config, transport=self._injected_transport)

    def _transport(self) -> JudgeTransport:
        if self._injected_transport is not None:
            return self._injected_transport
        if self._built_transport is None:
            provider = OpenAICompatibleProvider(
                base_url=self.config.base_url,
                model=self.config.model,
                api_key_env=self.config.api_key_env,
                temperature=0.0,
                timeout=self.config.timeout,
            )
            self._built_transport = lambda prompt: provider.complete(prompt).text
        return self._built_transport

    def evaluate(self, criterion: str, response: str) -> JudgeVerdict:
        """Grade *response* against *criterion*. Never raises."""
        if not self.config.configured:
            return JudgeVerdict(
                passed=True,
                reason=(
                    "judge endpoint not configured "
                    f"(set {ENV_BASE_URL} and {ENV_MODEL} to enable llm_judge)"
                ),
                skipped=True,
            )
        prompt = _JUDGE_PROMPT.format(criterion=criterion, response=response)
        try:
            reply = self._transport()(prompt)
        except Exception as exc:  # endpoint down / bad key: fail, don't crash
            return JudgeVerdict(False, f"judge request failed: {exc}")
        return _parse_verdict(reply)
