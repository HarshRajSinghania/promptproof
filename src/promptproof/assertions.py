"""Assertions evaluated against a model's raw text response.

A suite lists assertions as single-key mappings, e.g.::

    assertions:
      - contains: "positive"
      - not_contains: "negative"
      - regex: '"sentiment":\\s*"positive"'
      - max_chars: 500
      - json_schema: {type: object, required: [sentiment]}

``json_schema`` ships with a small built-in validator covering the subset of
JSON Schema that prompt tests actually use (``type``, ``required``,
``properties``, ``items``, ``enum``, ``minimum``/``maximum``,
``minLength``/``maxLength``, ``pattern``). That keeps PromptProof free of a
hard dependency on the ``jsonschema`` package; see the README for the exact
supported subset.

Roadmap: an ``llm_judge`` assertion (a second model grading the response)
is planned — the assertion registry below is where it will plug in — but it
is intentionally *not* implemented in v0.1.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .errors import AssertionConfigError


@dataclass
class AssertionResult:
    """Outcome of a single assertion check."""

    kind: str
    passed: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# Minimal JSON Schema subset validator
# ---------------------------------------------------------------------------

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate_json_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate *instance* against the supported JSON Schema subset.

    Returns a list of human-readable error strings; empty means valid.
    """
    errors: list[str] = []

    expected_type = schema.get("type")
    if expected_type is not None:
        check = _TYPE_CHECKS.get(expected_type)
        if check is None:
            errors.append(f"{path}: unsupported schema type {expected_type!r}")
            return errors
        if not check(instance):
            errors.append(f"{path}: expected type {expected_type}, got {type(instance).__name__}")
            return errors  # deeper checks would only add noise

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']!r}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        for key, subschema in schema.get("properties", {}).items():
            if key in instance and isinstance(subschema, dict):
                errors.extend(validate_json_schema(instance[key], subschema, f"{path}.{key}"))

    if isinstance(instance, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(instance):
            errors.extend(validate_json_schema(item, schema["items"], f"{path}[{index}]"))

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match pattern {schema['pattern']!r}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} > maximum {schema['maximum']}")

    return errors


# ---------------------------------------------------------------------------
# Assertion checks
# ---------------------------------------------------------------------------


def _check_contains(response: str, expected: Any) -> AssertionResult:
    needle = str(expected)
    ok = needle in response
    return AssertionResult("contains", ok, "" if ok else f"response does not contain {needle!r}")


def _check_not_contains(response: str, expected: Any) -> AssertionResult:
    needle = str(expected)
    ok = needle not in response
    return AssertionResult("not_contains", ok, "" if ok else f"response contains forbidden {needle!r}")


def _check_regex(response: str, expected: Any) -> AssertionResult:
    pattern = str(expected)
    try:
        ok = re.search(pattern, response) is not None
    except re.error as exc:
        raise AssertionConfigError(f"invalid regex {pattern!r}: {exc}") from exc
    return AssertionResult("regex", ok, "" if ok else f"response does not match /{pattern}/")


def _check_max_chars(response: str, expected: Any) -> AssertionResult:
    try:
        limit = int(expected)
    except (TypeError, ValueError) as exc:
        raise AssertionConfigError(f"max_chars expects an integer, got {expected!r}") from exc
    ok = len(response) <= limit
    return AssertionResult(
        "max_chars", ok, "" if ok else f"response is {len(response)} chars, limit is {limit}"
    )


def _check_json_schema(response: str, expected: Any) -> AssertionResult:
    if not isinstance(expected, dict):
        raise AssertionConfigError("json_schema expects a mapping (schema object)")
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as exc:
        return AssertionResult("json_schema", False, f"response is not valid JSON: {exc.msg}")
    errors = validate_json_schema(parsed, expected)
    return AssertionResult("json_schema", not errors, "; ".join(errors))


_CHECKS = {
    "contains": _check_contains,
    "not_contains": _check_not_contains,
    "regex": _check_regex,
    "max_chars": _check_max_chars,
    "json_schema": _check_json_schema,
}

#: Assertion kinds implemented in this version (``llm_judge`` is roadmap).
SUPPORTED_ASSERTIONS = tuple(_CHECKS)


def normalize_assertion(raw: Any) -> tuple[str, Any]:
    """Normalize one raw assertion entry to a ``(kind, expected)`` pair.

    Accepts either ``{contains: "x"}`` or ``{type: contains, value: "x"}``.
    """
    if not isinstance(raw, dict) or not raw:
        raise AssertionConfigError(f"assertion must be a non-empty mapping, got {raw!r}")
    if "type" in raw:
        kind = raw["type"]
        if "value" not in raw:
            raise AssertionConfigError(f"assertion {kind!r} is missing its 'value'")
        return str(kind), raw["value"]
    if len(raw) != 1:
        raise AssertionConfigError(
            f"assertion must have exactly one key, got {sorted(raw)}: {raw!r}"
        )
    kind, expected = next(iter(raw.items()))
    return str(kind), expected


def check_assertions(response: str, assertions: list[Any]) -> list[AssertionResult]:
    """Run every assertion in *assertions* against *response*."""
    results: list[AssertionResult] = []
    for raw in assertions:
        kind, expected = normalize_assertion(raw)
        check = _CHECKS.get(kind)
        if check is None:
            raise AssertionConfigError(
                f"unknown assertion {kind!r}; supported: {', '.join(SUPPORTED_ASSERTIONS)}"
            )
        results.append(check(response, expected))
    return results


@dataclass
class CaseAssertions:
    """Convenience bundle: all assertion results for one case."""

    results: list[AssertionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)
