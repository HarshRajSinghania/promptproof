"""Tests for golden-file snapshots (--record / diff)."""

import json

from promptproof.runner import run_suite
from promptproof.suite import load_suite

_SUITE = """\
name: snapshot-demo
prompt: "Say: {{word}}"
mock:
  default: "hello"
cases:
  - name: one
    vars: {word: "hi"}
    snapshot: true
    assertions:
      - contains: "hello"
  - name: two
    vars: {word: "yo"}
    assertions: []
"""


def _write(tmp_path, name="snap.yaml", snapshot_file=None) -> str:
    extra = f"snapshot_file: {snapshot_file}\n" if snapshot_file else ""
    path = tmp_path / name
    path.write_text(extra + _SUITE, encoding="utf-8")
    return str(path)


def test_record_creates_golden_file(tmp_path):
    path = _write(tmp_path)
    report = run_suite(load_suite(path), mock=True, record=True)
    assert report.ok
    golden = tmp_path / "snap.golden.json"
    assert golden.exists()
    data = json.loads(golden.read_text(encoding="utf-8"))
    assert data == {"one": "hello", "two": "hello"}


def test_run_against_matching_golden_passes(tmp_path):
    path = _write(tmp_path)
    run_suite(load_suite(path), mock=True, record=True)
    report = run_suite(load_suite(path), mock=True)
    assert report.ok
    snap_results = [
        r for c in report.cases for r in c.assertions if r.kind == "snapshot"
    ]
    assert len(snap_results) == 1
    assert all(r.passed for r in snap_results)


def test_changed_response_fails_snapshot(tmp_path):
    path = _write(tmp_path)
    run_suite(load_suite(path), mock=True, record=True)
    golden = tmp_path / "snap.golden.json"
    data = json.loads(golden.read_text(encoding="utf-8"))
    data["one"] = "something completely different"
    golden.write_text(json.dumps(data), encoding="utf-8")
    report = run_suite(load_suite(path), mock=True)
    assert not report.ok
    case_one = next(c for c in report.cases if c.name == "one")
    assert not case_one.passed
    assert any(
        r.kind == "snapshot" and not r.passed for r in case_one.assertions
    )


def test_missing_golden_fails_with_record_hint(tmp_path):
    report = run_suite(load_suite(_write(tmp_path)), mock=True)
    case_one = next(c for c in report.cases if c.name == "one")
    assert not case_one.passed
    assert "--record" in case_one.error


def test_custom_snapshot_file(tmp_path):
    custom = tmp_path / "goldens" / "custom.json"
    path = _write(tmp_path, snapshot_file=str(custom))
    run_suite(load_suite(path), mock=True, record=True)
    assert custom.exists()
    report = run_suite(load_suite(path), mock=True)
    assert report.ok


def test_case_without_snapshot_flag_ignores_golden(tmp_path):
    path = _write(tmp_path)
    run_suite(load_suite(path), mock=True, record=True)
    report = run_suite(load_suite(path), mock=True)
    case_two = next(c for c in report.cases if c.name == "two")
    assert case_two.passed
    assert not any(r.kind == "snapshot" for r in case_two.assertions)


def test_default_snapshot_path_resolution():
    from promptproof.snapshots import default_snapshot_path

    assert str(default_snapshot_path("suites/demo.yaml")).endswith(
        "suites/demo.golden.json"
    )
