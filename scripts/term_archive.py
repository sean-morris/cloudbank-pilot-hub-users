"""Keep completed terms' user counts from shrinking -> data/term_archive.csv.

users.py counts each user in the term of their LAST activity, using whatever
accounts a hub still has. When a hub loses accounts, its past terms drop to
zero; that happened to the CloudBank hubs in the Aug 17-25 2026 outage, and
every nightly users.csv since then has shown CloudBank with no users before
Fall 2026.

This keeps the highest count ever recorded per (college, where, term) and
writes it back into users.csv for every term before the current one. The
current term is always the live count.

    python scripts/term_archive.py               # nightly, after main.py
    python scripts/term_archive.py --seed-from-git   # once: rebuild from history
"""

import argparse
import io
import subprocess
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
USERS = BASE / "users.csv"
ARCHIVE = BASE / "data" / "term_archive.csv"
KEY = ["college", "where", "term"]


def is_total(df):
    return df["college"].astype(str).str.startswith("Total")


def long_form(users):
    """users.csv rows -> (college, where, term, users), summary rows dropped."""
    users = users[~is_total(users)]
    if "where" not in users:
        return pd.DataFrame(columns=KEY + ["users"])
    terms = [c for c in users.columns if "_20" in c]
    out = users.melt(id_vars=["college", "where"], value_vars=terms, var_name="term", value_name="users")
    return out[out["users"] > 0]


def merge(archive, new):
    both = pd.concat([archive, new], ignore_index=True)
    return both.groupby(KEY, as_index=False)["users"].max()


def seed_from_git():
    log = subprocess.run(
        ["git", "log", "--format=%h", "--", "users.csv"],
        capture_output=True, text=True, cwd=BASE, check=True,
    ).stdout.split()
    archive = pd.DataFrame(columns=KEY + ["users"])
    for sha in log:
        raw = subprocess.run(
            ["git", "show", f"{sha}:users.csv"], capture_output=True, text=True, cwd=BASE,
        ).stdout
        try:
            archive = merge(archive, long_form(pd.read_csv(io.StringIO(raw))))
        except (pd.errors.EmptyDataError, KeyError):
            continue
    print(f"  seeded from {len(log)} commits")
    return archive


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-from-git", action="store_true")
    args = ap.parse_args()

    users = pd.read_csv(USERS)
    archive = pd.read_csv(ARCHIVE) if ARCHIVE.is_file() else pd.DataFrame(columns=KEY + ["users"])
    if args.seed_from_git:
        archive = merge(archive, seed_from_git())
    archive = merge(archive, long_form(users))
    ARCHIVE.parent.mkdir(exist_ok=True)
    archive.sort_values(KEY).to_csv(ARCHIVE, index=False)

    # Completed terms = every term column before the latest one with users.
    terms = [c for c in users.columns if "_20" in c]
    rows = users[~is_total(users)]
    current = next((t for t in reversed(terms) if rows[t].sum() > 0), None)
    closed = terms[: terms.index(current)] if current else []

    best = archive.set_index(KEY)["users"]
    raised = 0
    for i, row in users[~is_total(users)].iterrows():
        for term in closed:
            kept = best.get((row["college"], row["where"], term), 0)
            if kept > row[term]:
                users.at[i, term] = kept
                raised += 1
    users.to_csv(USERS, index=False)
    print(f"  term_archive.csv: {len(archive)} rows; restored {raised} completed-term cells in users.csv")


if __name__ == "__main__":
    main()
