import pytest

from promptproof.errors import TemplateError
from promptproof.template import find_variables, render_template


def test_render_substitutes_variables():
    assert render_template("Hello {{name}}!", {"name": "Ada"}) == "Hello Ada!"


def test_render_allows_whitespace_and_repeats():
    assert render_template("{{ x }} + {{x}}", {"x": "1"}) == "1 + 1"


def test_render_stringifies_values():
    assert render_template("n={{n}}", {"n": 42}) == "n=42"


def test_render_unknown_variable_raises():
    with pytest.raises(TemplateError, match="unknown variable 'missing'"):
        render_template("{{missing}}", {})


def test_find_variables():
    assert find_variables("{{a}} and {{ b }}") == ["a", "b"]


def test_render_leaves_plain_text_alone():
    assert render_template("no placeholders {here}", {}) == "no placeholders {here}"
