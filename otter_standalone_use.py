"""
otter_standalone_use.py

Collects weekly usage statistics for Otter Standalone notebooks from Firestore.
Aggregates the number of users and notebooks per week and writes results to a CSV file.
"""

import datetime
import os
import sys

import firebase_admin
from firebase_admin import credentials, firestore


DEFAULT_PROJECT_IDS = ["cb-1003-1696", "data8x-scratch"]
COLLECTION_NAME = "otter-stdalone-prod-count"


def get_project_ids():
    """
    Returns the Firestore project IDs to query.

    Uses OTTER_FIRESTORE_PROJECT_IDS when set, otherwise falls back to the
    default pair of projects covering the logging cutover.
    """
    project_ids = os.getenv("OTTER_FIRESTORE_PROJECT_IDS")
    if not project_ids:
        return DEFAULT_PROJECT_IDS
    return [project_id.strip() for project_id in project_ids.split(",") if project_id.strip()]


def get_firestore_clients(project_ids):
    """
    Initializes one Firebase app and Firestore client per project.

    Args:
        project_ids (list[str]): Firestore project IDs.

    Returns:
        list[tuple[str, firestore.Client]]: Project IDs paired with clients.
    """
    cred = credentials.ApplicationDefault()
    clients = []
    for project_id in project_ids:
        app = firebase_admin.initialize_app(cred, {"projectId": project_id}, name=project_id)
        clients.append((project_id, firestore.client(app=app)))
    return clients


def main():
    """
    Connects to Firestore, retrieves Otter Standalone usage records,
    aggregates statistics by week, and writes results to a CSV file.
    """
    docs = []
    project_ids = get_project_ids()
    for _, db in get_firestore_clients(project_ids):
        project_docs = list(db.collection(COLLECTION_NAME).stream())
        docs.extend(project_docs)

    total_notebooks = 0
    weeks_dict = {}
    for doc in docs:
        rec = doc.to_dict()
        ts = rec.get("timestamp")
        year, month, date = list(map(lambda item: int(item), ts.split(" ")[0].split("-")))
        week = datetime.date(year, month, date).isocalendar()[1]
        two_digit_month = "{:02d}".format(month)
        two_digit_week = "{:02d}".format(week)
        key = f"{year}-{two_digit_month} {two_digit_week}"
        num_notebooks = int(rec.get('message'))
        if key not in weeks_dict:
            weeks_dict[key] = [1, num_notebooks]
        else:
            weeks_dict[key][0] += 1
            weeks_dict[key][1] += num_notebooks
        total_notebooks += num_notebooks

    s_dict = dict(reversed(sorted(weeks_dict.items())))
    with open("otter_standalone_use.csv", "w") as f:
        f.write(f"Total: {total_notebooks}\n")
        f.write("Year-Month, Week Of Year, Number of Users, Number of Notebooks\n")
        for row in s_dict.items():
            d = row[0].split(" ")
            f.write(f"{d[0]}, {d[1]}, {row[1][0]}, {row[1][1]}\n")

    return {
        "project_count": len(project_ids),
        "records": len(docs),
        "weeks": len(weeks_dict),
        "total_notebooks": total_notebooks,
    }


if __name__ == "__main__":
    try:
        summary = main()
        print(
            "Finished successfully: "
            f"otter_standalone records={summary['records']} "
            f"notebooks={summary['total_notebooks']} projects={summary['project_count']}"
        )
    except Exception as exc:
        print(f"Finished with failure: {exc}")
        sys.exit(1)
