from types import SimpleNamespace as NS

import pytest
from typesafe_sdk import TypeSafeError

from bscheck.cli import main, render, render_brief
from bscheck.core import (
    QUESTIONS,
    RULES,
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
    assert len(client.calls) == 4
    assert all(c["state"]["document"] == source for c in client.calls)
    assert len(client.calls[0]["questions"]) == 3 * len(QUESTIONS)
    assert len(client.calls[-1]["questions"]) == len(QUESTIONS)
    assert all(len(call["questions"]) <= 64 for call in client.calls)
    assert report["units_checked"] == 10
    assert report["models"] == ["jev-test"]
    assert report["input_tokens"] == 168


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


@pytest.mark.parametrize("brief", [False, True])
def test_cli_warning_exit_and_environment_precedence(
    tmp_path, monkeypatch, capsys, brief
):
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
    assert main([str(path)] + (["--brief"] if brief else [])) == 1
    output = capsys.readouterr().out
    assert ("BS002: word salad" if brief else "warning BS002") in output


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.code)
def test_each_subtype_preserves_metadata_and_requires_every_signal(rule):
    span = Span("Text.", 1, 1, 1, 6)
    row = probabilities(
        **{name: 0.95 if positive else 0.05 for name, positive in rule.signals}
    )
    diagnostic = next(d for d in diagnose(span, row, 0.8) if d["code"] == rule.code)
    assert (diagnostic["category"], diagnostic["subtype"]) == (
        rule.category,
        rule.subtype,
    )
    for name, _ in rule.signals:
        uncertain = row | {name: 0.5}
        assert rule.code not in {d["code"] for d in diagnose(span, uncertain, 0.8)}


def test_all_seven_families_in_offline_catalogue(capsys):
    assert main(["--rules"]) == 0
    output = capsys.readouterr().out
    categories = {
        "philosophical",
        "linguistic",
        "analytical",
        "technological",
        "organizational",
        "social",
        "professional",
    }
    assert {rule.category for rule in RULES} == categories
    for category in categories:
        assert output.count(f"{category.capitalize()} bullshit") == 1
    for rule in RULES:
        assert f"{rule.code} [{rule.subtype}]" in output


def test_overlapping_families_are_not_forced_into_one_label():
    span = Span("Text.", 1, 1, 1, 6)
    diagnostics = diagnose(
        span, probabilities(jargon=0.95, technical_costume=0.95), 0.8
    )
    assert {d["category"] for d in diagnostics} == {"linguistic", "technological"}
    output = render(
        {"diagnostics": diagnostics, "units_checked": 1}, "Text.", "test.md"
    )
    assert "type: technological / technical-costume" in output


@pytest.mark.parametrize(
    "signals,code,expected",
    [
        ({"jargon": 0.937}, "BS002", 0.937),
        ({"causal": 0.97, "mechanism": 0.08}, "BS001", 0.92),
        ({"causal": 0.85, "mechanism": 0.02}, "BS001", 0.85),
    ],
)
def test_certainty_uses_weakest_required_support(signals, code, expected):
    source = "A claim."
    diagnostics = diagnose(Span(source, 1, 1, 1, 9), probabilities(**signals), 0.8)
    diagnostic = next(d for d in diagnostics if d["code"] == code)
    assert diagnostic["certainty"] == pytest.approx(expected)
    text = render({"diagnostics": [diagnostic], "units_checked": 1}, source, "test.md")
    assert f"certainty: {expected:.1%} (minimum rule support)" in text
    # The reported value is also the boundary used by diagnostic gating.
    assert code not in {
        d["code"]
        for d in diagnose(
            Span(source, 1, 1, 1, 9), probabilities(**signals), expected + 0.001
        )
    }


def test_brief_groups_counts_certainty_and_bounded_locations():
    diagnostics = []
    for line in range(1, 11):
        diagnostics.extend(
            diagnose(
                Span("Text.", line, 1, line, 6),
                probabilities(jargon=0.9 if line == 1 else 0.95),
                0.8,
            )
        )
    diagnostics.extend(
        diagnose(
            Span("Text.", 1, 7, 1, 12),
            probabilities(jargon=0.99, causal=0.95, mechanism=0.05),
            0.8,
        )
    )
    output = render_brief({"diagnostics": diagnostics, "units_checked": 11}, "a\x1b.md")
    assert "a?.md: 12 warning(s) across 11 prose unit(s)." in output
    assert "Linguistic: 11 warning(s)" in output
    assert output.count("BS002:") == 1
    assert "11 occurrence(s); certainty 90.0%–99.0%" in output
    assert "lines 1, 2, 3, 4, 5, 6, 7, 8, … (+2 more)" in output
    assert "Analytical: 1 warning(s)" in output
    assert "certainty 95.0%; lines 1" in output
    assert "Text." not in output


def test_brief_cli_empty_and_json_conflict(tmp_path, capsys):
    path = tmp_path / "empty.md"
    path.write_text("# Heading")
    assert main([str(path), "--brief"]) == 0
    assert "No bullshit detected. This is not a warranty." in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        main([str(path), "--brief", "--format", "json"])
    assert error.value.code == 2
    assert "--brief requires text output" in capsys.readouterr().err
