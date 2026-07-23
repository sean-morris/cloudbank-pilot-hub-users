"""check_deployment_sync.py

Cross-checks the three things that need to agree for CloudBank reporting to
work:
  1. infrastructure  - 2i2c-org/infrastructure config/clusters/cloudbank/cluster.yaml
                        (source of truth: what's actually deployed)
  2. pilots.json      - what we have API tokens for (see main.py)
  3. the roster sheet - what has an ACCESS ID / contact info

This is a data-quality report, not a blocking pipeline: it always runs to
completion and prints what's out of sync. The workflow that calls this
decides whether/how to surface it (e.g. post to Slack) — it does not fail
the job by itself.

Requires:
    - pilots.json: decrypted pilot hub tokens (see main.py)
    - `gh` CLI available and able to read the public 2i2c-org/infrastructure repo
    - config/institution_mapping.json: used as known-good hub<->sheet_institution
      pairs so already-reviewed matches aren't re-guessed on every run

Usage:
    python scripts/check_deployment_sync.py
"""

import difflib
import json
import os
import subprocess
from pathlib import Path

import pandas as pd
import yaml

BASE_DIR = Path(__file__).parent.parent
SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1pYQTs-zFvbvBl9FdMIjCUKRv9_O5vGvfdRgNgyBy9-0/export?format=csv&gid=352213565"
)
PILOTS_PATH = BASE_DIR / "pilots.json"
MAPPING_PATH = BASE_DIR / "config" / "institution_mapping.json"

INFRA_REPO = "2i2c-org/infrastructure"
INFRA_CLUSTER_YAML_PATH = "config/clusters/cloudbank/cluster.yaml"

# Real deployments in the cloudbank cluster that are not a single CloudBank
# member institution, so they're out of scope for ACCESS-ID / roster matching.
NON_INSTITUTION_SLUGS = {"cra", "authoring", "demo", "gpu-demo", "staging", "high"}


def fetch_infra_hubs():
    """Returns {slug: display_name} for real institution hubs in the cloudbank cluster."""
    raw = subprocess.run(
        ["gh", "api", f"repos/{INFRA_REPO}/contents/{INFRA_CLUSTER_YAML_PATH}", "--jq", ".content"],
        capture_output=True, text=True, check=True,
    ).stdout
    import base64
    cluster = yaml.safe_load(base64.b64decode(raw))
    return {
        hub["name"]: hub["display_name"]
        for hub in cluster["hubs"]
        if hub["name"] not in NON_INSTITUTION_SLUGS
    }


def load_pilots():
    pilots = json.loads(PILOTS_PATH.read_text())["pilots"]
    return {
        p["url"]: p["name"]
        for p in pilots
        if p["where"] == "cloudbank" and p["url"] not in NON_INSTITUTION_SLUGS
    }


def fetch_sheet():
    """Returns {institution: access_id_or_None}, excluding rows explicitly marked icor
    (those are a separate project per Sean, not CloudBank/cloudbank-cluster scope)."""
    df = pd.read_csv(SHEET_CSV_URL)
    df["Notes"] = df["Notes"].astype(str).str.strip()
    df = df[df["Institution"].notna()]
    df = df[df["Notes"].str.lower() != "icor"]
    access_id_pattern = df["Notes"].str.match(r"^[A-Z]{2,6}\d{6}$", na=False)
    return {
        row["Institution"]: (row["Notes"] if match else None)
        for match, (_, row) in zip(access_id_pattern, df.iterrows())
    }


def load_reviewed_hub_to_institution():
    """{hub_url: sheet_institution} for pairs a human has already confirmed."""
    if not MAPPING_PATH.exists():
        return {}
    entries = json.loads(MAPPING_PATH.read_text())
    return {e["hub_url"]: e["sheet_institution"] for e in entries if e.get("reviewed") and e.get("hub_url")}


def match_sheet_institution(candidate_names, sheet_institutions, known_match):
    """Only ever returns a match we're willing to draw conclusions from: a
    human-reviewed pair, or an exact (case-insensitive) name match against
    any candidate name (infra display_name, pilots.json name — they're
    curated separately, so one often matches the sheet even when the other
    doesn't). Fuzzy scoring alone is not trustworthy enough here — e.g.
    "West Los Angeles College" fuzzy-matches "East Los Angeles College" at
    92/100, which is simply wrong. Anything less than exact gets surfaced as
    a suggestion for a human to confirm, never used to claim an institution
    does or doesn't have an ACCESS ID."""
    if known_match is not None:
        return known_match

    lowered = {name.lower(): name for name in sheet_institutions}
    for candidate in candidate_names:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def suggest_sheet_institution(display_name, sheet_institutions):
    best = difflib.get_close_matches(display_name, sheet_institutions, n=1, cutoff=0.6)
    if not best:
        return None, 0
    score = round(difflib.SequenceMatcher(None, display_name, best[0]).ratio() * 100)
    return best[0], score


def check():
    infra_hubs = fetch_infra_hubs()
    pilot_hubs = load_pilots()
    sheet = fetch_sheet()
    reviewed = load_reviewed_hub_to_institution()

    infra_slugs = set(infra_hubs)
    pilot_slugs = set(pilot_hubs)
    sheet_names = list(sheet.keys())

    issues = {
        "deployed_but_no_token": [],   # in infra, not in pilots.json — can't collect any data
        "token_but_not_deployed": [],  # in pilots.json, not in infra — stale/decommissioned
        "deployed_no_access_id": [],       # confidently matched to a sheet row, but no ACCESS ID yet
        "needs_review": [],                # can't confidently tell if this institution has an ACCESS ID or not
    }

    for slug in sorted(infra_slugs - pilot_slugs):
        issues["deployed_but_no_token"].append(f"{infra_hubs[slug]} ({slug}) — deployed in infra, no entry in pilots.json")

    for slug in sorted(pilot_slugs - infra_slugs):
        issues["token_but_not_deployed"].append(f"{pilot_hubs[slug]} ({slug}) — in pilots.json, no infra deployment found")

    for slug in sorted(infra_slugs & pilot_slugs):
        display_name = infra_hubs[slug]
        candidate_names = [display_name, pilot_hubs[slug]]
        matched_institution = match_sheet_institution(candidate_names, sheet_names, reviewed.get(slug))

        if matched_institution is not None:
            if sheet[matched_institution] is None:
                issues["deployed_no_access_id"].append(f"{display_name} ({slug}) — deployed, in roster, but no ACCESS ID yet")
            continue

        suggestion, score = suggest_sheet_institution(display_name, sheet_names)
        if suggestion:
            issues["needs_review"].append(
                f"{display_name} ({slug}) — not confidently matched to a roster row; closest guess is "
                f"'{suggestion}' (score={score}, not trusted) — confirm and add hub_url to config/institution_mapping.json"
            )
        else:
            issues["needs_review"].append(f"{display_name} ({slug}) — no roster row found at all, not even a rough guess")

    return issues


def format_report(issues):
    labels = {
        "deployed_but_no_token": "Deployed in infra but missing from pilots.json (no data can be collected)",
        "token_but_not_deployed": "In pilots.json but not found in infra (possibly decommissioned)",
        "deployed_no_access_id": "Deployed and in the roster, but no ACCESS ID yet",
        "needs_review": "Can't confidently match to a roster row (needs a human to confirm the pairing)",
    }
    lines = []
    total = 0
    for key, label in labels.items():
        items = issues[key]
        if not items:
            continue
        total += len(items)
        lines.append(f"\n{label} ({len(items)}):")
        lines.extend(f"  - {item}" for item in items)
    header = f"Deployment sync check: {total} item(s) found" if total else "Deployment sync check: everything in sync"
    return header + "\n" + "\n".join(lines)


def main():
    issues = check()
    report = format_report(issues)
    total = sum(len(v) for v in issues.values())
    print(report)

    (BASE_DIR / "sync_check_report.txt").write_text(report + "\n")

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as f:
            f.write("## Deployment sync check\n\n```\n" + report + "\n```\n")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"issue_count={total}\n")


if __name__ == "__main__":
    main()
