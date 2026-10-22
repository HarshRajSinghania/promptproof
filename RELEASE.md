# Releasing PromptProof to PyPI

## Prerequisites

Everything below the "publish" step is already automated. The only thing
missing is the **PyPI-side credential**, which requires the maintainer
(logged in as dylanXM on PyPI) — it cannot be created by automation.

### One-time setup (do once, on pypi.org)

1. Register / log in to <https://pypi.org> as the maintainer.
2. Project settings → Publishing → add a **Trusted Publisher**:
   - Owner: `dylanXM`
   - Repository name: `promptproof`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. On GitHub: repo Settings → Environments → create environment `pypi`
   (no required reviewers needed; the trusted publisher handles auth).

After this, publishing a release is: **push a `v*` tag and nothing else**.
No API tokens to store or rotate — OIDC trusted publishing mints a
short-lived token per run.

## Release checklist

1. Bump the version in **two** places so they agree:
   - `pyproject.toml` → `version`
   - `src/promptproof/__init__.py` → `__version__`
2. Add the changes to `CHANGELOG.md` under a new `[x.y.z]` heading with the
   release date; move the compare links at the bottom.
3. Run the full suite locally and validate the package:
   - `.venv/bin/python -m pytest -q`
   - `.venv/bin/python -m build`
   - `.venv/bin/python -m twine check --strict dist/*`
4. Commit, then tag and push the tag:
   - `git tag v0.2.0 && git push origin v0.2.0`
   - The `release` workflow builds the sdist + wheel, runs `twine check`,
     uploads them as a workflow artifact, then publishes to PyPI via the
     trusted publisher.
5. Create a GitHub Release for the tag; paste the CHANGELOG section as the
   release notes.

## Verify a published release

- `pip index versions promptproof-cli` (or `pip install promptproof-cli==x.y.z`
  in a fresh venv) and `promptproof --version` shows the new version.
- PyPI project page: <https://pypi.org/project/promptproof-cli/>

## Status (2026-10-22)

- Packaging validated locally: `python -m build` + `twine check --strict`
  pass for the current tree (0.2.0).
- Release workflow `release.yml` is in place and wired to the `pypi`
  environment; it will publish automatically on a `v*` tag push.
- ⏳ **Blocked on the maintainer**: the PyPI trusted-publisher setup above
  has not been done yet, so the publish job cannot succeed until then.
  Nothing else is pending.
