from promptproof import __version__
from promptproof.assertions import AssertionResult
from promptproof.report import render_html
from promptproof.runner import CaseResult, RunReport


def make_report():
    return RunReport(
        suite_name="demo-suite",
        provider="mock",
        model="mock",
        cases=[
            CaseResult(
                name="ok case",
                passed=True,
                duration_ms=12.3,
                prompt="Classify this",
                response="positive",
                assertions=[AssertionResult("contains", True)],
            ),
            CaseResult(
                name="bad <case>",
                passed=False,
                duration_ms=5.0,
                prompt="Say hi",
                response='<script>alert("xss")</script> and goodbye',
                assertions=[
                    AssertionResult("equals", False, "response does not exactly equal 'hi'"),
                    AssertionResult("llm_judge", True, "skipped: no judge", skipped=True),
                ],
            ),
        ],
    )


def test_html_is_self_contained_document():
    text = render_html(make_report())
    assert text.startswith("<!DOCTYPE html>")
    assert "<style>" in text and "</html>" in text
    assert "demo-suite" in text
    assert __version__ in text


def test_html_shows_case_results_and_stats():
    text = render_html(make_report())
    assert "ok case" in text
    assert "1 passed" in text and "1 failed" in text and "2 total" in text
    assert "FAIL" in text and "PASS" in text


def test_html_escapes_user_content():
    text = render_html(make_report())
    assert "&lt;script&gt;" in text
    assert "<script>alert" not in text
    assert "bad &lt;case&gt;" in text


def test_html_marks_skipped_assertions():
    text = render_html(make_report())
    assert "⊘ llm_judge" in text


def test_html_shows_prompt_and_response():
    text = render_html(make_report())
    assert "Classify this" in text
    assert "positive" in text
