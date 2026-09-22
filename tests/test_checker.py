from types import SimpleNamespace as NS

import pytest
from typesafe_sdk import TypeSafeError

from bscheck.cli import main, render
from bscheck.core import (
    QUESTIONS,
    Span,
    check,
    diagnose,
    extract_spans,
    validate_answers,
)


def probabilities(**updates):
    return dict.fromkeys(QUESTIONS, 0.5) | updates


class FakeClient:
    def __init__(self):
        self.calls = []

    def system_one(self, **request):
        self.calls.append(request)
        return NS(
            model="jev-test",
            usage=NS(input_tokens=42),
            answers={key: NS(noul=0.5) for key in request["questions"]},
        )


def test_markdown_locations_and_exclusions():
    source = "# Title\n\n```md\nFake claim.\n```\n\n- First claim. Second claim.\n\n> Wrapped claim\n> continues here.\n\n    code is not prose\n"
    spans = extract_spans(source)
    assert [(s.line, s.column) for s in spans] == [(7, 3), (7, 16), (9, 3)]
    assert spans[0].text == "First claim."
    assert spans[2].end_line == 10
    assert "Fake" not in " ".join(s.text for s in spans)


def test_abbreviations_decimals_links_and_unicode():
    spans = extract_spans(
        "Dr. Jones measured 3.5 ms. Élise agrees. See [the study](https://example.org)."
    )
    assert spans[0].text.startswith("Dr. Jones measured 3.5 ms.")
    assert len(spans) == 2  # conservative ASCII-capital boundary


@pytest.mark.parametrize(
    "signals,expected",
    [
        ({"causal": 0.95, "mechanism": 0.05}, {"BS001"}),
        ({"causal": 0.95, "mechanism": 0.6}, set()),
        ({"claim": 0.1, "falsifiable": 0.01}, set()),
        ({"claim": 0.95, "falsifiable": 0.01}, {"BS003"}),
        ({"needs_evidence": 0.95, "evidence": 0.05}, {"BS004"}),
        ({"needs_evidence": 0.95, "evidence": 0.95}, set()),
        ({"jargon": 0.99, "removable": 0.99}, {"BS002", "BS005"}),
    ],
)
def test_rule_gating(signals, expected):
    diagnostics = diagnose(Span("Text.", 1, 1, 1, 6), probabilities(**signals), 0.8)
    assert {d["code"] for d in diagnostics} == expected


def test_batches_retain_full_context_and_model():
    client = FakeClient()
    source = "\n\n".join(f"Claim number {i}." for i in range(10))
    report = check(source, client)
    assert len(client.calls) == 2
    assert all(c["state"]["document"] == source for c in client.calls)
    assert len(client.calls[0]["questions"]) == 64
    assert len(client.calls[1]["questions"]) == 16
    assert report["units_checked"] == 10
    assert report["models"] == ["jev-test"]
    assert report["input_tokens"] == 84


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), 1.1, -1, True])
def test_bad_answers_fail_closed(value):
    with pytest.raises(ValueError, match="invalid probability"):
        validate_answers({f"s0_{key}": NS(noul=value) for key in QUESTIONS}, 1)


def test_empty_document_and_input_limit():
    assert check("# Heading\n\n```\ncode\n```", None)["units_checked"] == 0
    with pytest.raises(ValueError, match="24,000"):
        check("é" * 12001, None)


def test_cli_json_without_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    path = tmp_path / "empty.md"
    path.write_text("# Heading")
    assert main([str(path), "--format", "json"]) == 0
    import json

    assert json.loads(capsys.readouterr().out)["diagnostics"] == []
    path.write_text("A claim.")
    assert main([str(path)]) == 2
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err


def test_service_failure_does_not_print_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "private-test-value")
    path = tmp_path / "input.md"
    path.write_text("A claim.")

    def fail(**kwargs):
        raise TypeSafeError("private-test-value")

    monkeypatch.setattr("bscheck.cli.TypeSafeClient", fail)
    assert main([str(path)]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "private-test-value" not in captured.err


def test_render_locations_and_escape_controls():
    source = "A claim."
    diagnostic = diagnose(Span(source, 1, 1, 1, 9), probabilities(jargon=0.99), 0.8)
    text = render({"diagnostics": diagnostic, "units_checked": 1}, source, "a\x1b.md")
    assert "a?.md:1:1: warning BS002" in text
    assert "^^^^^^^^" in text


def test_threshold_changes_only_composition():
    row = probabilities(claim=0.95, falsifiable=0.24)
    span = Span("Claim.", 1, 1, 1, 7)
    assert not diagnose(span, row, 0.8)
    assert [d["code"] for d in diagnose(span, row, 0.75)] == ["BS003"]


def test_missing_answer_is_not_a_clean_bill_of_health():
    with pytest.raises(ValueError, match="incomplete"):
        validate_answers({}, 1)


def test_cli_warning_exit_and_environment_precedence(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "environment-key")
    (tmp_path / ".env").write_text("TYPESAFE_API_KEY=dotenv-key\n")
    path = tmp_path / "input.md"
    path.write_text("An assertion.")

    class Client(FakeClient):
        def __init__(self, **kwargs):
            super().__init__()
            assert kwargs["api_key"] == "environment-key"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def system_one(self, **request):
            response = super().system_one(**request)
            response.answers["s0_jargon"].noul = 0.99
            return response

    monkeypatch.setattr("bscheck.cli.TypeSafeClient", Client)
    assert main([str(path)]) == 1
    assert "warning BS002" in capsys.readouterr().out
