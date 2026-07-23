"""Build/update config/institution_mapping.json.

This is a one-off / occasional helper, not part of the nightly pipeline. It
proposes a mapping from CloudBank roster institutions (that have an ACCESS
allocation number) to:
  - hub_url: the matching entry in pilots.json (so we know whose users to hash)
  - ipeds_unitid: the institution's NCES IPEDS UnitID, used as institutional_id
    in the NSF/XDMoD report

Matches are proposed via fuzzy string matching and are NOT authoritative.
Anything without "reviewed": true in the output must be checked by a human
before scripts/build_nsf_report.py is trusted to run unattended. Re-running
this script preserves any entry already marked "reviewed": true.

data/ipeds_unitid_master.json is a public-domain extract (institution name +
state -> UnitID) from NCES IPEDS, sourced via the `unitids` PyPI package's
bundled reference table.

Usage:
    python scripts/generate_institution_mapping.py
"""

import difflib
import json
import re
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1pYQTs-zFvbvBl9FdMIjCUKRv9_O5vGvfdRgNgyBy9-0/export?format=csv&gid=352213565"
)
ACCESS_ID_PATTERN = re.compile(r"^[A-Z]{2,6}\d{6}$")
MAPPING_PATH = BASE_DIR / "config" / "institution_mapping.json"
IPEDS_MASTER_PATH = BASE_DIR / "data" / "ipeds_unitid_master.json"
PILOTS_PATH = BASE_DIR / "pilots.json"

# Hand-verified corrections where automated name matching gets it wrong or
# the sheet/pilots.json names diverge too much to match automatically.
HUB_URL_OVERRIDES = {
    "Berkeley City College": "bcc",
    "Orange Coast": None,  # no pilots.json hub for this institution
    "Reedley College": "reedley",
    "Rio Hondo College": "riohondo",
    "Saddlebank CC": "saddleback",  # sheet has a typo ("Saddlebank")
    "Albany High": "ahs",
    "Borough of Manhattan Community College CUNY": "bmcc",
    "Clark Atlanta University": "cau",  # pilots.json misspells it "Clarke"
    "East Tennessee State University": "etsu",
    "Georgetown University": "georgetown",  # pilots.json "name" field is wrong ("George University")
    "Illinois Tech": "iit",
    "UNC Chapel Hill": "unc-chapel-hill",
    "University of North Carolina, Wilmington": "uncw",
    "University of Texas, Permian Basin": "utpb",
    "University of Wyoming": None,  # no pilots.json hub for this institution
    "York University": None,  # no pilots.json hub for this institution
}

# Institutions that are not in NCES IPEDS at all (e.g. K-12 schools), so an
# IPEDS UnitID lookup will never succeed for them.
NOT_IPEDS_ELIGIBLE = {"Albany High"}


def fetch_qualifying_institutions():
    df = pd.read_csv(SHEET_CSV_URL)
    df["Notes"] = df["Notes"].astype(str).str.strip()
    qualifying = df[df["Notes"].str.match(ACCESS_ID_PATTERN, na=False)]
    return qualifying[["Institution", "Notes"]].rename(
        columns={"Institution": "sheet_institution", "Notes": "access_id"}
    )


def load_pilots():
    return json.loads(PILOTS_PATH.read_text())["pilots"]


def match_hub_url(sheet_institution, pilots):
    if sheet_institution in HUB_URL_OVERRIDES:
        return HUB_URL_OVERRIDES[sheet_institution], 100
    names = [p["name"] for p in pilots]
    best = difflib.get_close_matches(sheet_institution, names, n=1, cutoff=0.6)
    if not best:
        return None, 0
    matched_name = best[0]
    score = round(difflib.SequenceMatcher(None, sheet_institution, matched_name).ratio() * 100)
    hub = next(p["url"] for p in pilots if p["name"] == matched_name)
    return hub, score


def match_ipeds_unitid(sheet_institution, ipeds_master):
    """Matches against IPEDS (higher-ed only). K-12 schools need a manually-sourced
    NCES CCD School ID instead — this function can't produce one, so entries in
    NOT_IPEDS_ELIGIBLE are left for a human to fill in institutional_id/id_type."""
    if sheet_institution in NOT_IPEDS_ELIGIBLE:
        return None, 0, "not an IPEDS-eligible institution (K-12) — needs a manually-sourced NCES CCD School ID"
    # Keys are "Name ST" (with a two-letter state suffix); strip it for name-only matching.
    name_only_keys = {k[:-3]: k for k in ipeds_master if len(k) > 3 and k[-3] == " "}
    best = difflib.get_close_matches(sheet_institution, list(name_only_keys.keys()), n=1, cutoff=0.6)
    if not best:
        return None, 0, "no confident IPEDS match"
    matched_short = best[0]
    full_key = name_only_keys[matched_short]
    score = round(difflib.SequenceMatcher(None, sheet_institution, matched_short).ratio() * 100)
    return str(ipeds_master[full_key]), score, f"matched against '{full_key}'"


def main():
    qualifying = fetch_qualifying_institutions()
    pilots = load_pilots()
    ipeds_master = json.loads(IPEDS_MASTER_PATH.read_text())

    existing = {}
    if MAPPING_PATH.exists():
        for entry in json.loads(MAPPING_PATH.read_text()):
            existing[entry["sheet_institution"]] = entry

    output = []
    for _, row in qualifying.iterrows():
        name = row["sheet_institution"]
        access_id = row["access_id"]

        prior = existing.get(name)
        if prior and prior.get("reviewed"):
            prior["access_id"] = access_id
            output.append(prior)
            continue

        hub_url, hub_score = match_hub_url(name, pilots)
        institutional_id, ipeds_score, ipeds_note = match_ipeds_unitid(name, ipeds_master)
        id_type = "ipeds_unitid" if institutional_id is not None else None

        notes = []
        if hub_url is None:
            notes.append("no matching pilots.json hub found")
        if institutional_id is None:
            notes.append(ipeds_note)
        elif ipeds_score < 90:
            notes.append(f"low-confidence IPEDS match ({ipeds_note})")

        output.append(
            {
                "sheet_institution": name,
                "canonical_name": name,  # sheet name can be wrong (e.g. "York University" for York College, CUNY) — correct by hand if so
                "access_id": access_id,
                "hub_url": hub_url,
                "institutional_id": institutional_id,
                "id_type": id_type,
                "match_score": min(hub_score, ipeds_score) if institutional_id is not None else hub_score,
                "reviewed": False,
                "note": "; ".join(notes),
            }
        )

    output.sort(key=lambda e: e["sheet_institution"].lower())
    MAPPING_PATH.parent.mkdir(exist_ok=True)
    MAPPING_PATH.write_text(json.dumps(output, indent=2) + "\n")
    unresolved = [e for e in output if not e["reviewed"]]
    print(f"Wrote {MAPPING_PATH} ({len(output)} institutions, {len(unresolved)} need review)")


if __name__ == "__main__":
    main()
