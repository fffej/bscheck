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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Type-check your Markdown for bullshit. Powered by Jev."
    )
    parser.add_argument("file", nargs="?", help="Markdown file, or - for stdin")
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
    if args.rules:
        for rule in RULES:
            print(f"{rule.code}: {rule.title}\n  {rule.message}\n  help: {rule.help}")
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
        else render(report, source, filename)
    )
    return 1 if report["diagnostics"] else 0
