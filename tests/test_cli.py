import json
from pathlib import Path

import pytest

from promptproof import __version__
from promptproof.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_run_mock_example_exits_zero(capsys):
    code = main(["run", str(ROOT / "examples" / "basic.yaml"), "--mock"])
    assert code == 0
    out = capsys.readouterr().out
    assert "3 passed, 0 failed" in out


def test_run_writes_json_report(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    code = main(
        ["run", str(ROOT / "examples" / "basic.yaml"), "--mock", "--json", str(report_path)]
    )
    assert code == 0
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["suite"] == "sentiment-classifier"
    assert data["summary"]["passed"] == 3
    assert data["summary"]["usage_estimated"] is True
    assert data["cases"][0]["assertions"], "per-assertion detail must be in the report"


def test_run_missing_file_exits_two(capsys):
    code = main(["run", "does-not-exist.yaml", "--mock"])
    assert code == 2
    assert "error" in capsys.readouterr().err
