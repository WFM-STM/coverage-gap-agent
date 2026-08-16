# Coverage Gap Agent

A two-step pipeline that flags staffing shortfalls from a forecast-vs-scheduled CSV, then uses Claude to decide whether the flagged gaps are serious enough to escalate — and drafts a plain-English summary a manager can read in a few seconds.

## What it does

1. **`staffing_gap_flagger.py`** reads a CSV of forecasted vs. scheduled headcount, computes the gap between the two for every row, and flags any row where that gap exceeds a threshold (10% by default). It's resilient to messy real-world data — blank cells, typos like `N/A` or `TBD`, negative numbers — skipping bad rows with a clear reason instead of crashing, and prints a summary (totals, overall gap, worst offender) before listing what got flagged.
2. **`claude_escalation_agent.py`** takes that list of flagged rows and sends it to Claude, which returns a structured verdict: whether to escalate, how severe it is, and a short plain-English explanation of what's going on and what to do about it.

Run them in sequence and you go from a raw scheduling export to "here's what needs a manager's attention today, and why."

## Why it exists

Forecast-vs-scheduled CSVs are usually reviewed by eye, which doesn't scale and misses patterns that only show up when you look across a whole day or department (e.g. one queue with zero coverage buried in 90 rows of minor variance). This project automates the first pass — mechanical flagging, then judgment-level triage — so a human only has to look at what's actually worth their time.

## Project structure

```
staffing_gap_flagger.py      # Step 1: flag gaps in a staffing CSV
claude_escalation_agent.py   # Step 2: ask Claude to triage the flagged gaps
sample_staffing.csv          # small clean example CSV
Archive/sample_staffing.csv  # larger, messier example CSV (multiple departments, bad data)
requirements.txt             # Python dependencies for the escalation agent
.env.example                 # template for your API key — copy to .env
```

## Setup

1. **Clone the repo and install dependencies** (only needed for the escalation agent — the flagger uses only Python's standard library):
   ```
   pip install -r requirements.txt
   ```
2. **Set your Anthropic API key.** Copy `.env.example` to `.env` and fill in your real key:
   ```
   copy .env.example .env
   ```
   Then edit `.env` so it reads:
   ```
   ANTHROPIC_API_KEY=sk-ant-...your real key...
   ```
   `.env` is listed in `.gitignore`, so it never gets committed. Never paste your key directly into the scripts.

## How to run it

### Step 1 — flag the gaps

```
python staffing_gap_flagger.py [input_file] [-t THRESHOLD] [-o OUTPUT]
```

- `input_file` — path to your CSV (default: `sample_staffing.csv`). Must have at least these columns: `department`, `date`, `forecasted_staff`, `scheduled_staff`. Extra columns (e.g. `skill`, `interval_start`) are preserved and passed through.
- `-t / --threshold` — flag rows where the absolute gap exceeds this percent (default: `10`).
- `-o / --output` — where to write the flagged rows (default: `flagged_gaps.csv`).

Example:

```
python staffing_gap_flagger.py Archive\sample_staffing.csv -t 15 -o flagged_gaps.csv
```

This prints a summary (rows read, skipped, overall gap, worst offender) and writes every flagged row to the output CSV.

### Step 2 — ask Claude whether it's escalation-worthy

```
python claude_escalation_agent.py [input_file]
```

- `input_file` — path to the flagged-gaps CSV from Step 1 (default: `flagged_gaps.csv`).

Example:

```
python claude_escalation_agent.py flagged_gaps.csv
```

Output looks like:

```
ESCALATE: YES   (severity: high)
==================================================

<plain-English summary of what's happening and what to do>

Reasoning: <why Claude reached that verdict>
```

### Run both together

```
python staffing_gap_flagger.py my_data.csv -t 10 -o flagged_gaps.csv
python claude_escalation_agent.py flagged_gaps.csv
```

## Notes

- The escalation agent uses Claude Opus 5 (`claude-opus-5`) with a JSON schema, so the response is always structured (`escalate`, `severity`, `reasoning`, `summary`) rather than free-form text you'd have to parse.
- If `ANTHROPIC_API_KEY` isn't set, the script exits with a clear message instead of a stack trace.
- Generated output files (`flagged_gaps*.csv`) are gitignored — they're run artifacts, not source of truth.
