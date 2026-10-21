import pytest

from promptproof.assertions import check_assertions, validate_json_schema
from promptproof.errors import AssertionConfigError


def only(response, assertion):
    results = check_assertions(response, [assertion])
    assert len(results) == 1
    return results[0]


def test_contains():
    assert only("hello world", {"contains": "world"}).passed
    assert not only("hello world", {"contains": "mars"}).passed


def test_not_contains():
    assert only("hello world", {"not_contains": "mars"}).passed
    assert not only("hello world", {"not_contains": "world"}).passed


def test_regex():
    assert only('{"sentiment": "positive"}', {"regex": r'"sentiment":\s*"positive"'}).passed
    assert not only("plain text", {"regex": r"\d+"}).passed


def test_max_chars():
    assert only("short", {"max_chars": 10}).passed
    result = only("a much longer response", {"max_chars": 10})
    assert not result.passed
    assert "limit is 10" in result.detail


def test_type_value_form():
    assert only("abc", {"type": "contains", "value": "b"}).passed


def test_unknown_assertion_raises():
    with pytest.raises(AssertionConfigError, match="unknown assertion"):
        check_assertions("x", [{"telepathy": "yes"}])


def test_malformed_assertion_raises():
    with pytest.raises(AssertionConfigError):
        check_assertions("x", [{"contains": "a", "regex": "b"}])


# --- json_schema assertion + the built-in subset validator -----------------

SCHEMA = {
    "type": "object",
    "required": ["sentiment"],
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def test_json_schema_valid_response():
    assert only('{"sentiment": "positive", "confidence": 0.9}', {"json_schema": SCHEMA}).passed


def test_json_schema_enum_violation():
    result = only('{"sentiment": "ecstatic"}', {"json_schema": SCHEMA})
    assert not result.passed
    assert "not one of" in result.detail


def test_json_schema_missing_required():
    result = only('{"confidence": 0.5}', {"json_schema": SCHEMA})
    assert not result.passed
    assert "missing required property" in result.detail


def test_json_schema_rejects_non_json():
    result = only("not json at all", {"json_schema": SCHEMA})
    assert not result.passed
    assert "not valid JSON" in result.detail


def test_validate_nested_and_arrays():
    schema = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"type": "string", "minLength": 2}},
        },
    }
    assert validate_json_schema({"tags": ["ai", "ml"]}, schema) == []
    errors = validate_json_schema({"tags": ["a"]}, schema)
    assert errors and "minLength" in errors[0]
