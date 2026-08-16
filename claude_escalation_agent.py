"""
Reads flagged staffing gaps (the output of staffing_gap_flagger.py) and asks
Claude whether they're serious enough to escalate, plus a plain-English
summary a non-technical manager could read in a few seconds.

Requires ANTHROPIC_API_KEY to be set as an environment variable (e.g. via a
.env file — see .env.example). The key is never hardcoded or logged.
"""

import argparse
import csv
import json
import os
import re
import sys

import anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_INPUT_FILE = "flagged_gaps.csv"
MODEL = "claude-opus-5"

ESCALATION_SCHEMA = {
    "type": "object",
    "properties": {
        "escalate": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "reasoning": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["escalate", "severity", "reasoning", "summary"],
    "additionalProperties": False,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ask Claude whether flagged staffing gaps warrant escalation."
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default=DEFAULT_INPUT_FILE,
        help=f"Path to the flagged-gaps CSV (default: {DEFAULT_INPUT_FILE})",
    )
    return parser.parse_args()


def read_flagged_rows(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        sys.exit(f"Error: couldn't find '{path}'. Run staffing_gap_flagger.py first.")
    if not rows:
        sys.exit(f"Error: '{path}' has no flagged rows to review.")
    return rows


def build_prompt(rows):
    lines = [", ".join(f"{key}={value}" for key, value in row.items()) for row in rows]
    return (
        f"Here are {len(rows)} staffing rows flagged for exceeding the gap threshold:\n\n"
        + "\n".join(lines)
        + "\n\nAssess whether this set of gaps is serious enough to escalate to a "
        "workforce manager right now, and write a short plain-English summary "
        "a non-technical manager could read in a few seconds. Use plain ASCII "
        "punctuation only: regular hyphens instead of em/en dashes, straight "
        "quotes instead of curly quotes."
    )


def fix_stray_unicode_escapes(text):
    """
    Occasionally the model over-escapes a unicode character inside the JSON
    string (writes \\u2014 instead of the real character), which json.loads
    then decodes into the literal 6-character text "\\u2014". Clean that up.
    """
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)


def assess(rows):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "Error: ANTHROPIC_API_KEY is not set.\n"
            "Copy .env.example to .env and add your real key, "
            "or set the environment variable directly."
        )

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            output_config={"format": {"type": "json_schema", "schema": ESCALATION_SCHEMA}},
            messages=[{"role": "user", "content": build_prompt(rows)}],
        )
    except anthropic.AuthenticationError:
        sys.exit("Error: Claude rejected the API key. Check the value in your .env file.")
    except anthropic.APIStatusError as e:
        sys.exit(f"Error: Claude API request failed ({e.status_code}): {e.message}")

    if response.stop_reason == "refusal":
        sys.exit("Claude declined to process this request.")
    if response.stop_reason == "max_tokens":
        sys.exit("Error: response was cut off (hit max_tokens). Try raising max_tokens.")

    text = next(block.text for block in response.content if block.type == "text")
    result = json.loads(text)
    result["summary"] = fix_stray_unicode_escapes(result["summary"])
    result["reasoning"] = fix_stray_unicode_escapes(result["reasoning"])
    return result


if __name__ == "__main__":
    args = parse_args()
    rows = read_flagged_rows(args.input_file)

    print(f"Reviewing {len(rows)} flagged row(s) from {args.input_file}...\n")
    result = assess(rows)

    print("=" * 50)
    print(f"ESCALATE: {'YES' if result['escalate'] else 'NO'}   (severity: {result['severity']})")
    print("=" * 50)
    print(f"\n{result['summary']}\n")
    print(f"Reasoning: {result['reasoning']}")
