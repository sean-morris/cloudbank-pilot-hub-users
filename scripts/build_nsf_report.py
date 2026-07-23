"""build_nsf_report.py

Builds and submits the nightly ACCESS allocation usage report to XDMoD's
resource-manager-logs endpoint. Only institutions that (a) have an ACCESS
allocation number in the CloudBank roster spreadsheet and (b) have a
human-reviewed entry in config/institution_mapping.json are included.

Like the dashboard pipeline (users.py / main.py), this script tolerates
individual hub failures: if one institution's hub can't be reached, or an
institution in the sheet has no reviewed mapping entry yet, that institution
is skipped and everyone else's data still gets submitted. The job still
exits non-zero whenever anything was skipped, so the gap stays visible (CI
goes red, Slack fires) instead of silently persisting. institutional_id and
hub_url are never guessed at runtime — only what's already reviewed in
config/institution_mapping.json is used.

Requires:
    - pilots.json: decrypted pilot hub tokens (see main.py)
    - config/institution_mapping.json: reviewed institution -> hub/IPEDS mapping
    - env XDMOD_TOKEN: bearer token for the resource-manager-logs endpoint
    - env NSF_HASH_KEY: HMAC key used to pseudonymize hub usernames

Usage:
    python scripts/build_nsf_report.py             # build and submit
    python scripts/build_nsf_report.py --dry-run    # build and print only
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from users import get_users  # noqa: E402
SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1pYQTs-zFvbvBl9FdMIjCUKRv9_O5vGvfdRgNgyBy9-0/export?format=csv&gid=352213565"
)
ACCESS_ID_PATTERN = re.compile(r"^[A-Z]{2,6}\d{6}$")
MAPPING_PATH = BASE_DIR / "config" / "institution_mapping.json"
PILOTS_PATH = BASE_DIR / "pilots.json"
XDMOD_ENDPOINT = "https://data.ccr.xdmod.org/resource-manager-logs"


def fetch_qualifying_access_ids():
    """Returns {institution name: access id} for rows with a current ACCESS allocation."""
    df = pd.read_csv(SHEET_CSV_URL)
    df["Notes"] = df["Notes"].astype(str).str.strip()
    qualifying = df[df["Notes"].str.match(ACCESS_ID_PATTERN, na=False)]
    return dict(zip(qualifying["Institution"], qualifying["Notes"]))


def load_reviewed_mapping():
    mapping = json.loads(MAPPING_PATH.read_text())
    return {entry["sheet_institution"]: entry for entry in mapping if entry.get("reviewed")}


def load_pilot(hub_url):
    """Some slugs (e.g. "dvc") are reused across clusters — Diablo Valley College has
    both an icor-flavored pilots.json entry and a separate cloudbank one. hub_url in
    config/institution_mapping.json always refers to the cloudbank deployment, so
    matching on url alone could silently grab the wrong cluster's entry/token."""
    pilots = json.loads(PILOTS_PATH.read_text())["pilots"]
    return next(p for p in pilots if p["url"] == hub_url and p["where"] == "cloudbank")


def hub_users(pilot):
    """Real hub users, excluding admins and service/deployment accounts (mirrors users.py)."""
    all_users = get_users(pilot["url"], pilot["where"], pilot["token"])
    return [
        u
        for u in all_users
        if "admin" not in u["roles"]
        and u["admin"] is False
        and "service-hub" not in u["name"]
        and "deployment-service" not in u["name"]
    ]


def hash_user_id(hmac_key, institutional_id, username):
    message = f"{institutional_id}:{username}".encode()
    return hmac.new(hmac_key.encode(), message, hashlib.sha256).hexdigest()


def build_report(hmac_key):
    """Returns (records, problems). problems is non-empty if the report is incomplete."""
    current_access_ids = fetch_qualifying_access_ids()
    reviewed = load_reviewed_mapping()

    problems = []
    records = []

    for institution, access_id in current_access_ids.items():
        entry = reviewed.get(institution)
        if entry is None:
            problems.append(
                f"'{institution}' has ACCESS allocation {access_id} in the sheet but no "
                f"reviewed entry in {MAPPING_PATH.name} — run scripts/generate_institution_mapping.py "
                f"and review it before this institution can be reported"
            )
            continue
        if entry["hub_url"] is None or entry["institutional_id"] is None:
            # Known, reviewed gap (e.g. no CloudBank hub, or no IPEDS UnitID). Not an error,
            # just nothing to report for this institution.
            continue

        pilot = load_pilot(entry["hub_url"])
        try:
            users = hub_users(pilot)
        except Exception as exc:
            problems.append(f"'{institution}' ({entry['hub_url']}): failed to fetch hub users: {exc}")
            continue

        for user in users:
            records.append(
                {
                    "access_id": access_id,
                    "institutional_id": entry["institutional_id"],
                    "institution_name": entry["canonical_name"],
                    "hashed_user_id": hash_user_id(hmac_key, entry["institutional_id"], user["name"]),
                }
            )

    return records, problems


def submit(records, token):
    payload = json.dumps(records).encode()
    response = requests.post(
        XDMOD_ENDPOINT,
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("nsf_report.json", payload, "application/json")},
    )
    response.raise_for_status()
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Build the report but do not submit it")
    args = parser.parse_args()

    hmac_key = os.environ.get("NSF_HASH_KEY")
    token = os.environ.get("XDMOD_TOKEN")
    if not hmac_key:
        print("Finished with failure: NSF_HASH_KEY is not set")
        sys.exit(1)
    if not args.dry_run and not token:
        print("Finished with failure: XDMOD_TOKEN is not set")
        sys.exit(1)

    records, problems = build_report(hmac_key)
    institution_count = len({r["institutional_id"] for r in records})

    lines = [f"Built report: {len(records)} user records across {institution_count} institutions"]
    if problems:
        lines.append(f"{len(problems)} institution(s) skipped:")
        lines.extend(f"  - {p}" for p in problems)
    report = "\n".join(lines)
    print(report)

    # Institution names + error text only — never the payload itself (hashed_user_id
    # values), so this is safe to post to Slack / show in a step summary.
    (BASE_DIR / "nsf_report_summary.txt").write_text(report + "\n")

    if args.dry_run:
        out_path = BASE_DIR / "nsf_report.dry_run.json"
        out_path.write_text(json.dumps(records, indent=2) + "\n")
        print(f"Dry run — wrote {out_path}, did not submit")
    elif records:
        response = submit(records, token)
        print(f"Submitted {len(records)} records, status={response.status_code}")
    else:
        print("Nothing to submit")

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        mode = "dry run (not submitted)" if args.dry_run else "submitted"
        with open(step_summary, "a") as f:
            f.write(f"## NSF ACCESS usage report ({mode})\n\n```\n{report}\n```\n")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"record_count={len(records)}\n")
            f.write(f"institution_count={institution_count}\n")
            f.write(f"skipped_count={len(problems)}\n")

    if problems:
        print("Finished with failure: one or more institutions were skipped (see above)")
        sys.exit(1)

    print("Finished successfully")


if __name__ == "__main__":
    main()
