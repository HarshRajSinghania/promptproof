# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- New deterministic assertions: `equals` (exact match, whitespace-trimmed),
  `min_chars` (mirror of `max_chars`), `starts_with` and `ends_with`
  (literal prefix/suffix checks).
- HTML report output: `promptproof run suite.yaml --html report.html` writes
  a self-contained HTML report (inline CSS, no assets), with per-case
  assertion detail, skipped markers, and collapsible prompt/response blocks.

## [0.2.0] - 2026-10-21

### Added

- `llm_judge` assertion: grade a response against a plain-language criterion
  with a second model, configured purely via environment variables
  (`PROMPTPROOF_JUDGE_BASE_URL`, `PROMPTPROOF_JUDGE_MODEL`,
  `PROMPTPROOF_JUDGE_API_KEY`); per-assertion `model` / `base_url` overrides
  supported. When no judge endpoint is configured the assertion reports as
  *skipped* instead of failing, so suites stay green offline and in CI.

## [0.1.0] - 2026-10-21

### Added

- YAML/JSON suite files: model config, prompt template, mock rules, cases
  with per-case variables and assertion lists.
- Deterministic assertions: `contains`, `not_contains`, `regex`,
  `max_chars`, plus a dependency-free `json_schema` validator covering the
  subset prompt tests actually use.
- Providers: any OpenAI-compatible chat-completions endpoint, plus a built-in
  offline `MockProvider` (`--mock`) so suites run with no keys and no network.
- CLI: `promptproof run suite.yaml` with `--mock`, `--json`, `--base-url`,
  `--model` overrides; exit codes 0 (pass) / 1 (fail) / 2 (invalid suite).
- Reports: plain-text table for CI logs and a machine-readable JSON report.
- GitHub Actions CI: tests on Python 3.11/3.12, offline demo suite runs.

[Unreleased]: https://github.com/dylanXM/promptproof/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/dylanXM/promptproof/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dylanXM/promptproof/releases/tag/v0.1.0
