# Contributing to PromptProof

Thanks for helping! PromptProof aims to stay small, dependable and boring in
the best way: standard library first, tiny dependency footprint, honest
offline behaviour.

## Getting started

```bash
git clone https://github.com/dylanXM/promptproof.git
cd promptproof
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
promptproof run examples/basic.yaml --mock
```

## Ground rules

- **Python 3.11+**, type annotations and docstrings on public functions.
- **New assertions** go in `promptproof/assertions.py`: register the check in
  the `_CHECKS` table, document it in the README table, and add pass *and*
  fail tests.
- **Every change ships with tests.** Bug fixes need a regression test that
  fails without the fix.
- **The mock demo is sacred.** `examples/basic.yaml --mock` must always run
  offline with no API key and pass. CI enforces this.
- **No silent magic.** Unknown variables, unknown assertions and malformed
  suites are hard errors with actionable messages.
- Keep token-usage reporting honest: estimated numbers are always labelled
  as estimated.

## Pull requests

1. Fork and branch from `main`.
2. Make the change, add tests, update the README if behaviour changes.
3. Run `pytest` and the mock demo locally; both must be green.
4. Open the PR with a short description of the behaviour change and why.

## Reporting bugs

Open an issue with your suite file (secrets removed), the command you ran,
and the full output. For assertion bugs, the smallest response string that
reproduces the problem is gold.
