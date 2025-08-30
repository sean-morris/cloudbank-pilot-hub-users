"""
otter_standalone_use.py

Collects weekly usage statistics for Otter Standalone notebooks from Firestore.
Aggregates the number of users and notebooks per week and writes results to a CSV file.

Usage:
    python otter_standalone_use.py

Outputs:
    - otter_standalone_use.csv: Weekly usage statistics

Requires:
    - Google Cloud credentials (set via environment variable GCP_PROJECT_ID)
"""

import firebase_admin
from firebase_admin import credentials, firestore
import os
import datetime


def main():
    """
    Connects to Firestore, retrieves Otter Standalone usage records,
    aggregates statistics by week, and writes results to a CSV file.
    """
    # Use the application default credentials
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        'projectId': os.environ.get("GCP_PROJECT_ID"),
        'storageBucket': 'data8x-scratch.appspot.com/otter-srv-stdalone'
    })

    db = firestore.client()
    docs = db.collection("otter-stdalone-prod-count").stream()
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


if __name__ == "__main__":
    main()
