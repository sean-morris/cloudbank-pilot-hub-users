import firebase_admin
from firebase_admin import credentials, firestore
import os
import datetime

# Use the application default credentials
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': os.environ.get("GCP_PROJECT_ID"),
    'storageBucket': 'data8x-scratch.appspot.com/otter-srv-stdalone'
})

db = firestore.client()
docs = db.collection("otter-stdalone-prod-count").stream()
sum = 0
weeks_dict = {}
for doc in docs:
    rec = doc.to_dict()
    ts = rec.get("timestamp")
    year, month, date = list(map(lambda item: int(item), ts.split(" ")[0].split("-")))
    week = datetime.date(year, month, date).isocalendar()[1]
    two_digit_month = "{:02d}".format(month)
    key = f"{year}-{two_digit_month} {week}"
    num_notebooks = int(rec.get('message'))
    if key not in weeks_dict:
        weeks_dict[key] = [1, num_notebooks]
    else:
        weeks_dict[key][0] += 1
        weeks_dict[key][1] += num_notebooks
    sum += num_notebooks
s_dict = dict(reversed(sorted(weeks_dict.items())))
with open("parse_data.csv", "w") as f:
    f.write(f"Total: {sum}\n")
    f.write("Year-Month, Week Of Year, Number of Users, Number of Notebooks\n")
    for row in s_dict.items():
        d = row[0].split(" ")
        f.write(f"{d[0]}, {d[1]}, {row[1][0]}, {row[1][1]}\n")
