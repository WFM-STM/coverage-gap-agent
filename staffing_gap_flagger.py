"""
Reads a CSV of forecasted vs. scheduled staffing and flags rows where the
gap between the two exceeds a threshold percentage.

Expected CSV columns: department, date, forecasted_staff, scheduled_staff
"""

import argparse
import csv
import sys

DEFAULT_INPUT_FILE = "sample_staffing.csv"
DEFAULT_OUTPUT_FILE = "flagged_gaps.csv"
DEFAULT_THRESHOLD_PERCENT = 10.0  # flag any row where |gap%| exceeds this
REQUIRED_COLUMNS = ["department", "date", "forecasted_staff", "scheduled_staff"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Flag staffing rows where the forecast-vs-scheduled gap exceeds a threshold."
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default=DEFAULT_INPUT_FILE,
        help=f"Path to the input CSV (default: {DEFAULT_INPUT_FILE})",
    )
    parser.add_argument(
        "-t", "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD_PERCENT,
        help=f"Flag rows where |gap%%| exceeds this percent (default: {DEFAULT_THRESHOLD_PERCENT})",
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT_FILE,
        help=f"Path to write flagged rows to (default: {DEFAULT_OUTPUT_FILE})",
    )
    return parser.parse_args()


def read_rows(path):
    """Read the CSV into a list of dictionaries, one per row.
    Exits with a clear message if the file is missing or malformed.
    """
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames
    except FileNotFoundError:
        sys.exit(f"Error: couldn't find input file '{path}'.")

    if fieldnames is None:
        sys.exit(f"Error: '{path}' appears to be empty.")

    missing = [col for col in REQUIRED_COLUMNS if col not in fieldnames]
    if missing:
        sys.exit(
            f"Error: '{path}' is missing required column(s): {', '.join(missing)}.\n"
            f"Found columns: {fieldnames}"
        )

    return rows


def to_number(value):
    """Convert a CSV cell to a non-negative float, or None if it can't be parsed."""
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if number < 0:
        return None
    return number


def gap_percent(forecasted, scheduled):
    """
    Positive = understaffed (scheduled below forecast).
    Negative = overstaffed (scheduled above forecast).
    """
    if forecasted == 0:
        return 0.0
    return (forecasted - scheduled) / forecasted * 100


def process_rows(rows):
    """
    Split raw CSV rows into:
      - valid: rows with usable numbers, gap_percent/direction attached
      - skipped: rows that couldn't be parsed, with a reason
    """
    valid = []
    skipped = []

    for line_number, row in enumerate(rows, start=2):  # +2: header is line 1
        forecasted = to_number(row.get("forecasted_staff"))
        scheduled = to_number(row.get("scheduled_staff"))

        problems = []
        if forecasted is None:
            problems.append(f"forecasted_staff={row.get('forecasted_staff')!r} is not a valid non-negative number")
        if scheduled is None:
            problems.append(f"scheduled_staff={row.get('scheduled_staff')!r} is not a valid non-negative number")

        if problems:
            skipped.append({"line": line_number, "row": row, "reason": "; ".join(problems)})
            continue

        row = dict(row)
        row["forecasted_staff"] = forecasted
        row["scheduled_staff"] = scheduled
        gap = round(gap_percent(forecasted, scheduled), 1)
        row["gap_percent"] = gap
        if gap > 0:
            row["direction"] = "understaffed"
        elif gap < 0:
            row["direction"] = "overstaffed"
        else:
            row["direction"] = "on target"
        valid.append(row)

    return valid, skipped


def find_flagged_rows(valid_rows, threshold):
    return [row for row in valid_rows if abs(row["gap_percent"]) > threshold]


def write_flagged_rows(path, flagged_rows):
    if not flagged_rows:
        return
    fieldnames = list(flagged_rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flagged_rows)


def print_summary(rows, valid_rows, skipped_rows, flagged_rows, threshold):
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Rows read             : {len(rows)}")
    print(f"Valid rows processed  : {len(valid_rows)}")
    print(f"Rows skipped (bad data): {len(skipped_rows)}")

    if valid_rows:
        total_forecasted = sum(row["forecasted_staff"] for row in valid_rows)
        total_scheduled = sum(row["scheduled_staff"] for row in valid_rows)
        overall_gap = gap_percent(total_forecasted, total_scheduled)
        print(f"Total forecasted staff: {total_forecasted:g}")
        print(f"Total scheduled staff : {total_scheduled:g}")
        print(f"Overall gap           : {overall_gap:.1f}%")

        worst = max(valid_rows, key=lambda row: abs(row["gap_percent"]))
        print(
            f"Worst single gap      : {worst['department']} on {worst['date']} "
            f"({worst['gap_percent']:.1f}%, {worst['direction']})"
        )

    print(f"Rows flagged (>{threshold:g}% gap): {len(flagged_rows)}")
    print("=" * 50)


if __name__ == "__main__":
    args = parse_args()

    rows = read_rows(args.input_file)
    valid_rows, skipped_rows = process_rows(rows)
    flagged_rows = find_flagged_rows(valid_rows, args.threshold)

    print_summary(rows, valid_rows, skipped_rows, flagged_rows, args.threshold)

    if skipped_rows:
        print(f"\nSkipped row details:")
        for s in skipped_rows:
            print(f"  Line {s['line']}: {s['reason']}")

    if flagged_rows:
        print(f"\nFlagged rows (>{args.threshold:g}% gap):\n")
        for row in flagged_rows:
            extra = ", ".join(
                f"{key}={row[key]}"
                for key in row
                if key not in ("department", "date", "forecasted_staff", "scheduled_staff", "gap_percent", "direction")
            )
            extra_str = f"  [{extra}]" if extra else ""
            print(
                f"  {row['department']:15} {row['date']}  "
                f"{row['gap_percent']:6.1f}%  ({row['direction']}){extra_str}"
            )

    write_flagged_rows(args.output, flagged_rows)
    if flagged_rows:
        print(f"\nWrote flagged rows to {args.output}")
