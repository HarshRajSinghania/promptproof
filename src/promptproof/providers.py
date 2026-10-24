"""Model providers: a real OpenAI-compatible endpoint, and an offline mock.

The mock provider exists so a suite can be exercised end-to-end with no API
key — in CI, in a fresh clone, in a code review. It resolves a response for
a rendered prompt in this order:

1. the case's (or turn's) own ``mock_response`` field, if present;
2. the first matching entry in the suite's ``mock.rules`` list
   (``match`` is a substring, or a regex when wrapped in ``/.../``);
3. the suite's ``mock.default`` response;
4. a small JSON echo of the prompt (so unconfigured mocks still return
   something inspectable).

For multi-turn conversations the mock resolves each turn against that
turn's user message only — history is ignored, so mocks stay deterministic.

Token usage from the mock is *estimated* (chars / 4) and flagged as such in
reports — never presented as real billing data.

Both providers expose two entry points:

- ``complete(prompt, ...)`` — one user message, one reply (the
  classic single-turn case);
- ``complete_conversation(messages, ...)`` — a full ``[{role, content}]``
  history, used by multi-turn cases; ``complete`` delegates to it.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .errors import PromptProofError


@dataclass
class Completion:
    """One model completion plus its token usage."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usage_estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def estimate_tokens(text: str) -> int:
    """Rough token estimate (≈ 4 chars/token), used only for mock runs."""
    return max(1, math.ceil(len(text) / 4)) if text else 0


@dataclass
class MockConfig:
    """Suite-level mock behaviour (``mock:`` block in a suite file)."""

    default: str = ""
    rules: list[dict[str, str]] = field(default_factory=list)


class MockProvider:
    """Deterministic, offline provider used with ``--mock``."""

    name = "mock"

    def __init__(self, config: MockConfig | None = None) -> None:
        self._config = config or MockConfig()

    def _resolve(self, prompt: str, case_mock_response: str | None) -> str:
        if case_mock_response is not None:
            return case_mock_response
        for rule in self._config.rules:
            match = str(rule.get("match", ""))
            response = str(rule.get("response", ""))
            if match.startswith("/") and match.endswith("/") and len(match) > 2:
                if re.search(match[1:-1], prompt):
                    return response
            elif match and match in prompt:
                return response
        if self._config.default:
            return self._config.default
        return json.dumps({"mock": True, "echo": prompt[:200]})

    def complete(self, prompt: str, *, case_mock_response: str | None = None) -> Completion:
        return self.complete_conversation(
            [{"role": "user", "content": prompt}],
            case_mock_response=case_mock_response,
        )

    def complete_conversation(
        self,
        messages: list[dict[str, str]],
        *,
        case_mock_response: str | None = None,
    ) -> Completion:
        """Reply to a multi-turn *messages* history (mock: deterministic).

        The mock resolves each turn against that turn's user message only —
        history is ignored, so mocks stay deterministic.
        """
        last_user = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_user = str(message.get("content", ""))
                break
        text = self._resolve(last_user, case_mock_response)
        return Completion(
            text=text,
            prompt_tokens=estimate_tokens(last_user),
            completion_tokens=estimate_tokens(text),
            usage_estimated=True,
        )


class OpenAICompatibleProvider:
    """POSTs to ``{base_url}/chat/completions`` (OpenAI-style payload).

    Works with OpenAI itself and with any compatible endpoint (Azure OpenAI
    gateways, OpenRouter, Together, Groq, local servers such as Ollama or
    LM Studio) — anything that speaks the chat-completions shape.
    """

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.timeout = timeout

    def complete(self, prompt: str, *, case_mock_response: str | None = None) -> Completion:
        return self.complete_conversation(
            [{"role": "user", "content": prompt}],
            case_mock_response=case_mock_response,
        )

    def complete_conversation(
        self,
        messages: list[dict[str, str]],
        *,
        case_mock_response: str | None = None,
    ) -> Completion:
        """Send a full ``[{role, content}]`` history and return the reply."""
        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise PromptProofError(
                f"environment variable {self.api_key_env} is not set; "
                "export your API key or run with --mock for an offline demo"
            )
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": messages,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # network / HTTP errors become suite errors
            raise PromptProofError(f"request to {self.base_url} failed: {exc}") from exc

        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PromptProofError(f"unexpected response shape from endpoint: {body!r}") from exc

        usage = body.get("usage") or {}
        return Completion(
            text=str(text),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            usage_estimated=False,
        )
