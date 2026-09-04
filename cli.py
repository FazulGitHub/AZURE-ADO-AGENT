"""
cli.py
------
Command-line alternative to the Flask app, useful for scripting / CI or
if you just prefer a terminal workflow.

Examples:
    python cli.py --requirement "As part of checkout, add Apple Pay support"
    python cli.py --file requirement.txt --out artifacts.md --format markdown
    python cli.py --file requirement.txt --out artifacts.json --format json
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from generator import generate_artifacts, to_markdown, to_csv_rows, DEFAULT_MODEL

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate agile artifacts (user stories, tasks, acceptance "
        "criteria, test scenarios) from a feature/ADO requirement using Groq."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--requirement", "-r", help="Requirement text inline.")
    src.add_argument("--file", "-f", help="Path to a text file containing the requirement.")

    parser.add_argument("--context", "-c", default="", help="Optional extra context/constraints.")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help=f"Groq model (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "csv"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument("--out", "-o", help="Output file path. Defaults to stdout.")

    args = parser.parse_args()

    requirement = args.requirement
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            return 1
        requirement = path.read_text(encoding="utf-8")

    try:
        result = generate_artifacts(requirement=requirement, extra_context=args.context, model=args.model)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if result.error:
        print(f"Generation error: {result.error}", file=sys.stderr)
        return 1

    if args.format == "markdown":
        output = to_markdown(result)
    elif args.format == "json":
        output = json.dumps(result.raw_json, indent=2)
    else:  # csv
        import csv
        import io

        rows = to_csv_rows(result)
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        output = buf.getvalue()

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Written to {args.out}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
