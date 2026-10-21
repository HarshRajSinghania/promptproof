# PromptProof

**Snapshot & regression testing for LLM prompts.**

Write your prompts and test cases as YAML, run one command against any
OpenAI-compatible endpoint, and get a CI-friendly pass/fail report. When a
case fails, your build goes red — before your users notice the model started
behaving differently.

```console
$ promptproof run examples/basic.yaml --mock

PromptProof — suite: sentiment-classifier
provider: mock   model: mock
------------------------------------------------------------------------
CASE            RESULT      TIME  TOKENS
----------------------------------------
glowing review  PASS         0ms      66
angry review    PASS         0ms      63
factual review  PASS         0ms      59
----------------------------------------
3 passed, 0 failed, 3 total — 188 tokens (estimated)
```

## Why PromptProof?

Prompts are code, but they fail like weather. You swap a model version, tweak
one sentence of a system prompt, or your provider silently updates a model —
and the output format your parser depends on quietly changes. Nobody notices
until production does.

PromptProof treats a prompt the way unit tests treat a function:

- **Suites are files.** Prompts, variables and expectations live in YAML/JSON
  next to your code, reviewed in pull requests like everything else.
- **Assertions, not vibes.** `contains`, `regex`, `json_schema`, `max_chars`
  — deterministic checks that mean the same thing on every run.
- **Built for CI.** Plain-text table for humans, JSON report for machines,
  exit code `1` when any case fails so GitHub Actions turns red.
- **No key needed to try it.** A built-in mock provider runs any suite
  offline, so a fresh clone works in 30 seconds and CI never needs secrets
  just to test the harness.

## Quick start (offline demo)

```bash
pip install promptproof        # or: pip install -e . from a clone
promptproof run examples/basic.yaml --mock
promptproof run examples/basic.yaml --mock --json report.json
```

That runs the bundled sentiment-classifier suite end-to-end — rendering,
"model" calls, assertions, report — with zero API keys and zero network.

## Running against a real endpoint

```bash
export OPENAI_API_KEY=sk-...
promptproof run examples/basic.yaml
```

PromptProof speaks the OpenAI chat-completions API, so `base_url` can point
at OpenAI, Azure OpenAI, OpenRouter, Together, Groq, or a local server
(Ollama, LM Studio, …) — anything compatible. The API key is read from the
environment variable named by `api_key_env` in the suite; keys are never
written into suite files or reports.

Exit codes: `0` all cases passed · `1` a case failed · `2` the suite or
configuration is invalid.

## Suite files

```yaml
name: sentiment-classifier

model:
  base_url: https://api.openai.com/v1   # any OpenAI-compatible endpoint
  name: gpt-4o-mini
  api_key_env: OPENAI_API_KEY           # env var holding the key
  temperature: 0

prompt: |
  Classify the sentiment of this review. Respond with JSON only.
  Review: {{review}}

# Only used by --mock runs: deterministic offline responses.
mock:
  default: '{"sentiment": "neutral"}'
  rules:
    - match: "absolutely loved"        # substring, or /regex/
      response: '{"sentiment": "positive"}'

cases:
  - name: glowing review
    vars: {review: "I absolutely loved this keyboard."}
    assertions:
      - contains: '"positive"'
      - max_chars: 100
      - json_schema:
          type: object
          required: [sentiment]
          properties:
            sentiment: {type: string, enum: [positive, negative, neutral]}
```

Templates support `{{variable}}` placeholders only — a suite is data, not
code. A case may set `mock_response` to override the mock rules for that
case. Suites can also be plain JSON (same structure).

## Assertions

| Assertion      | Example                                   | Passes when…                                             |
| -------------- | ----------------------------------------- | -------------------------------------------------------- |
| `contains`     | `contains: '"positive"'`                 | the response contains the substring                      |
| `not_contains` | `not_contains: "I don't know"`            | the response does *not* contain the substring            |
| `regex`        | `regex: '"id":\s*\d+'`                    | the pattern matches somewhere in the response            |
| `json_schema`  | `json_schema: {type: object, required: [sentiment]}` | the response parses as JSON and validates against the schema |
| `max_chars`    | `max_chars: 500`                          | the response is at most N characters                     |

`json_schema` uses a small built-in validator covering the subset prompt
tests actually use — `type`, `required`, `properties`, `items`, `enum`,
`minimum`/`maximum`, `minLength`/`maxLength`, `pattern` — so PromptProof
needs no heavy dependencies. Assertions may also be written in the explicit
form `{type: contains, value: "x"}`.

## GitHub Actions

```yaml
- name: Prompt regression tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    pip install promptproof
    promptproof run tests/prompts/checkout.yaml --json prompt-report.json
```

A failing case exits `1` and fails the step. For pull requests that only
touch prompt files, run with `--mock` to validate the suite itself without
spending tokens or requiring secrets from forks.

## Roadmap

- `llm_judge` assertion — a second model grading free-form responses
  (interface reserved; deliberately not faked in v0.1)
- Golden-file snapshots: record real responses once, diff against them later
- Multi-turn conversation suites
- Cost budgets per suite (`max_tokens` / `max_usd` gates)
- HTML report output

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
Please keep the dependency footprint tiny and the offline demo working.

## License

MIT © 2026 Dylan XM — see [LICENSE](LICENSE).
