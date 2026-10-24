"""Multi-turn conversation suites: loading, validation, and execution."""

import json
import urllib.request

import pytest

from promptproof.errors import PromptProofError
from promptproof.providers import OpenAICompatibleProvider
from promptproof.runner import run_suite
from promptproof.suite import load_suite

MULTITURN_SUITE = """\
name: chatty

model:
  base_url: https://api.openai.com/v1
  name: gpt-4o-mini
  api_key_env: OPENAI_API_KEY
  temperature: 0

prompt: |
  You are a helpful assistant.

mock:
  default: "default reply"
  rules:
    - match: "first question"
      response: "first answer"
    - match: "second question"
      response: "second answer"

cases:
  - name: two turns
    turns:
      - prompt: "first question"
        assertions:
          - contains: "first answer"
      - prompt: "second question"
        assertions:
          - contains: "second answer"
"""


def _write_suite(tmp_path, text=MULTITURN_SUITE, name="suite.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_load_turns_parses(tmp_path):
    suite = load_suite(_write_suite(tmp_path))
    case = suite.cases[0]
    assert len(case.turns) == 2
    assert case.turns[0]["prompt"] == "first question"
    assert case.turns[0]["assertions"] == [{"contains": "first answer"}]
    assert case.turns[0]["mock_response"] is None


@pytest.mark.parametrize(
    "bad_case",
    [
        "    turns: []",
        "    turns: not-a-list",
        "    turns:\n      - not-a-mapping",
        "    turns:\n      - assertions:\n          - contains: x",
        "    turns:\n      - prompt: '   '",
        "    turns:\n      - prompt: hi\n    assertions:\n      - contains: x",
    ],
)
def test_load_turns_validation(tmp_path, bad_case):
    text = (
        "name: bad\n"
        "prompt: 'system'\n"
        "cases:\n"
        "  - name: broken\n"
        f"{bad_case}\n"
    )
    with pytest.raises(PromptProofError):
        load_suite(_write_suite(tmp_path, text))


def test_multiturn_mock_run_passes(tmp_path):
    report = run_suite(load_suite(_write_suite(tmp_path)), mock=True)
    assert report.ok
    case = report.cases[0]
    assert len(case.turns) == 2
    assert all(turn.passed for turn in case.turns)
    assert case.response == "second answer"  # final reply
    assert "system:\nYou are a helpful assistant." in case.prompt


def test_turn_mock_response_override(tmp_path):
    text = (
        "name: override\n"
        "prompt: 'system'\n"
        "cases:\n"
        "  - name: per-turn mock\n"
        "    turns:\n"
        "      - prompt: 'first question'\n"
        "        mock_response: 'custom reply'\n"
        "        assertions:\n"
        "          - contains: 'custom reply'\n"
    )
    report = run_suite(load_suite(_write_suite(tmp_path, text)), mock=True)
    assert report.ok
    assert report.cases[0].response == "custom reply"


def test_turn_failure_attribution(tmp_path):
    text = (
        "name: faily\n"
        "prompt: 'system'\n"
        "mock:\n"
        "  default: 'default reply'\n"
        "cases:\n"
        "  - name: second turn fails\n"
        "    turns:\n"
        "      - prompt: 'first question'\n"
        "        mock_response: 'first answer'\n"
        "        assertions:\n"
        "          - contains: 'first answer'\n"
        "      - prompt: 'second question'\n"
        "        mock_response: 'second answer'\n"
        "        assertions:\n"
        "          - contains: 'something missing'\n"
    )
    report = run_suite(load_suite(_write_suite(tmp_path, text)), mock=True)
    assert not report.ok
    case = report.cases[0]
    assert not case.passed
    assert case.turns[0].passed
    assert not case.turns[1].passed
    # single-turn failure counting is unchanged: the case fails as one unit
    assert report.failed_count == 1


class _FakeHTTPResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_conversation_history_sent_to_provider(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
            {
                "choices": [{"message": {"content": "fake reply"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    report = run_suite(load_suite(_write_suite(tmp_path)), mock=False)
    # The fake endpoint replies "fake reply" to every turn, so the
    # mock-rule-driven assertions fail — that is fine here; what this test
    # proves is the message history that reached the provider.
    assert len(report.cases[0].turns) == 2
    messages = captured["payload"]["messages"]
    # system message, then user/assistant pairs per turn
    assert messages[0] == {"role": "system", "content": "You are a helpful assistant.\n"}
    assert messages[1] == {"role": "user", "content": "first question"}
    assert messages[2] == {"role": "assistant", "content": "fake reply"}
    assert messages[3] == {"role": "user", "content": "second question"}
    assert captured["payload"]["model"] == "gpt-4o-mini"


def test_provider_error_fails_multiturn_case(tmp_path, monkeypatch):
    def boom(request, timeout=None):
        raise ConnectionError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    report = run_suite(load_suite(_write_suite(tmp_path)), mock=False)
    assert not report.ok
    case = report.cases[0]
    assert not case.passed
    assert "network down" in case.error
