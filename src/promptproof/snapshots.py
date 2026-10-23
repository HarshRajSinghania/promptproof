"""Golden-file snapshots.

Record each snapshot-enabled case's real response once (``--record``) into a
JSON golden file, then diff every later run against it: a changed response
fails the case just like a failed assertion.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import PromptProofError


def default_snapshot_path(suite_path: str) -> Path:
    """Default golden-file location: ``<suite-stem>.golden.json`` next to the suite."""
    suite_file = Path(suite_path)
    return suite_file.with_name(f"{suite_file.stem}.golden.json")


def load_goldens(path: str | Path) -> dict[str, str]:
    """Load the golden file, returning ``{}`` when it does not exist yet."""
    golden_file = Path(path)
    if not golden_file.exists():
        return {}
    try:
        data = json.loads(golden_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PromptProofError(f"golden file {golden_file} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PromptProofError(f"golden file {golden_file} must contain a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def save_goldens(path: str | Path, goldens: dict[str, str]) -> None:
    """Write *goldens* to *path* (creating parent directories as needed)."""
    golden_file = Path(path)
    golden_file.parent.mkdir(parents=True, exist_ok=True)
    golden_file.write_text(
        json.dumps(goldens, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
