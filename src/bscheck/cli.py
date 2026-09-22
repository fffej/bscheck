"""Command-line entry point. Credentials and service errors never enter reports."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import TypeSafeClient, TypeSafeError

from .core import RULES, CheckError, check, extract_spans


def terminal_safe(text: str) -> str:
    return "".join(c if c.isprintable() or c == "\t" else "?" for c in text)


def render(report: dict, source: str, filename: str) -> str:
    lines = source.splitlines()
    output = []
    for diagnostic in report["diagnostics"]:
        span = diagnostic["span"]
        line, column = span["line"], span["column"]
        output.append(
            f"{terminal_safe(filename)}:{line}:{column}: warning {diagnostic['code']}: {diagnostic['title']}"
        )
        output.append(
            f"      certainty: {diagnostic['certainty']:.1%} (minimum rule support)"
        )
        output.append(f"      type: {diagnostic['category']} / {diagnostic['subtype']}")
        original = lines[line - 1]
        displayed = terminal_safe(original).expandtabs(4)
        prefix = terminal_safe(original[: column - 1]).expandtabs(4)
        width = (
            span["end_column"] - column
            if span["end_line"] == line
            else len(original) - column + 1
        )
        output.append(f" {line:>4} | {displayed}")
        output.append(f"      | {' ' * len(prefix)}{'^' * max(1, min(width, 100))}")
        output.append(f"      = {diagnostic['message']}")
        output.append(f"      help: {diagnostic['help']}")
        output.append("")
    count = len(report["diagnostics"])
    output.append(
        f"{count} warning(s) across {report['units_checked']} prose unit(s). "
        + (
            "Build succeeded. Credibility has questions."
            if count
            else "No bullshit detected. This is not a warranty."
        )
    )
    return "\n".join(output)


def render_brief(report: dict, filename: str) -> str:
    diagnostics = report["diagnostics"]
    output = [
        (
            f"{terminal_safe(filename)}: {len(diagnostics)} warning(s) "
            f"across {report['units_checked']} prose unit(s)."
        )
    ]
    if not diagnostics:
        return output[0] + " No bullshit detected. This is not a warranty."
    categories = {}
    for diagnostic in diagnostics:
        groups = categories.setdefault(diagnostic["category"], {})
        groups.setdefault(diagnostic["code"], []).append(diagnostic)
    for category, groups in categories.items():
        count = sum(len(items) for items in groups.values())
        output.append(f"{category.capitalize()}: {count} warning(s)")
        for code, items in sorted(groups.items()):
            low = min(item["certainty"] for item in items)
            high = max(item["certainty"] for item in items)
            certainty = f"{low:.1%}" if low == high else f"{low:.1%}–{high:.1%}"
            lines = sorted({item["span"]["line"] for item in items})
            locations = ", ".join(map(str, lines[:8]))
            if len(lines) > 8:
                locations += f", … (+{len(lines) - 8} more)"
            output.append(
                f"  {code}: {items[0]['title']} — {len(items)} occurrence(s); "
                f"certainty {certainty}; lines {locations}"
            )
    output.append(
        "Certainty is minimum rule support. Use full output for excerpts and fixes."
    )
    return "\n".join(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Type-check your Markdown for bullshit. Powered by Jev."
    )
    parser.add_argument("file", nargs="?", help="Markdown file, or - for stdin")
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Summarise text output by category and rule",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Required support for every rule signal (default: 0.8)",
    )
    parser.add_argument(
        "--model", default="jev-1.13.0", help="Jev model ID (default: jev-1.13.0)"
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="dotenv file (default: .env in current directory)",
    )
    parser.add_argument(
        "--rules", action="store_true", help="Explain diagnostic codes; no API call"
    )
    args = parser.parse_args(argv)
    if args.brief and args.format == "json":
        parser.error("--brief requires text output; omit --format json")
    if args.rules:
        for category in dict.fromkeys(rule.category for rule in RULES):
            print(f"{category.capitalize()} bullshit")
            for rule in RULES:
                if rule.category == category:
                    print(
                        f"  {rule.code} [{rule.subtype}]: {rule.title}\n"
                        f"    {rule.message}\n    help: {rule.help}"
                    )
            print()
        return 0
    if not args.file:
        parser.error("provide a Markdown file or - for stdin")
    if not 0.5 < args.threshold <= 1:
        parser.error("--threshold must be greater than 0.5 and at most 1")
    try:
        source = (
            sys.stdin.read()
            if args.file == "-"
            else Path(args.file).read_text(encoding="utf-8")
        )
        load_dotenv(args.env_file, override=False)
        # Empty/non-prose documents do not need credentials or a network connection.
        if not extract_spans(source):
            report = check(source, None, model=args.model, threshold=args.threshold)
        else:
            key = os.environ.get("TYPESAFE_API_KEY")
            if not key:
                raise CheckError("Set TYPESAFE_API_KEY in the environment or .env.")
            with TypeSafeClient(api_key=key, timeout=60.0) as client:
                report = check(
                    source, client, model=args.model, threshold=args.threshold
                )
    except (OSError, UnicodeError):
        print(
            "bscheck: error: could not read the UTF-8 input or environment file.",
            file=sys.stderr,
        )
        return 2
    except CheckError as error:
        print(f"bscheck: error: {error}", file=sys.stderr)
        return 2
    except (TypeSafeError, ValueError) as error:
        status = getattr(error, "status_code", None)
        suffix = f" (HTTP {status})" if isinstance(status, int) else ""
        print(
            f"bscheck: error: Jev request failed{suffix}; check credentials, connectivity, and service limits. No complete report produced.",
            file=sys.stderr,
        )
        return 2
    filename = "<stdin>" if args.file == "-" else args.file
    report["file"] = filename
    print(
        json.dumps(report, indent=2, ensure_ascii=False)
        if args.format == "json"
        else render_brief(report, filename)
        if args.brief
        else render(report, source, filename)
    )
    return 1 if report["diagnostics"] else 0
