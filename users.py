import csv
import sys
import json
from datetime import datetime
import requests


def filter_users(func, users):
    return len(list(filter(func, users)))


# Function to convert string to datetime
def convert(datetime_str):
    try:
        date_time_obj = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%fZ')
    except Exception:
        datetime_str = datetime_str[:-1] + ".0000Z"
        date_time_obj = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%fZ')
    return date_time_obj


def users_active_since_date(begin_d, end_d, users):
    users = list(filter(lambda user: user["last_activity"], users))

    def process(user):
        la = convert(user["last_activity"])
        return la > begin_d and la < end_d

    return len(list(filter(lambda user: process(user), users)))


def get_users(url, token):
    all_data = []
    api_url = f'http://{url}.cloudbank.2i2c.cloud/hub/api'
    if url == "mills":
        api_url = f'http://datahub.{url}.edu/hub/api'
    for offset in range(0, 600, 200):
        r = requests.get(api_url + f'/users?limit=200&offset={offset}',
                        headers = {
                            'Authorization': f'token {token}'
                        }
                    )
        if r.status_code == 403:
            print("403 error")
            return []
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("Error getting users")
        r.raise_for_status()
        all_data.extend(r.json())
    return all_data


def process_pilot(pilot, dates, stats):
    p = {}
    users = get_users(pilot["url"], pilot["token"]) if pilot["token"] else None
    if users:
        users = list(filter(lambda user: "admin" not in user["roles"] and user['admin'] is False and "service-hub" not in user['name'] and "deployment-service" not in user['name'], users))
        p["name"] = pilot["name"]
        p["number_all_users"] = len(users)
        stats["all-users"][0] += p["number_all_users"]
        p["number_all_users_ever_active"] = filter_users(lambda user: user["last_activity"], users)
        stats["all-users-ever-active"][0] += p["number_all_users_ever_active"]
        for term, begin, end in dates:
            p[term] = users_active_since_date(begin, end, users)
            stats[term][0] += p[term]
            if p[term] > 5:
                stats[term][1] += 1
    return p


def generate_dates(start_year, end_year):
    dates = []
    for year in range(start_year, end_year + 1):
        # Fall semester
        fall_begin = datetime(year, 7, 15, 0, 0, 0, 0)
        fall_end = datetime(year, 12, 31, 0, 0, 0, 0)
        dates.append((f"fall_{year}", fall_begin, fall_end))

        # Spring semester (spills into next year)
        spring_begin = datetime(year + 1, 1, 1, 0, 0, 0, 0)
        spring_end = datetime(year + 1, 7, 14, 0, 0, 0, 0)
        dates.append((f"spring_{year + 1}", spring_begin, spring_end))
    return dates


def config_stats(dates):
    s = {}
    s["all-users"] = [0, 0]
    s["all-users-ever-active"] = [0, 0]
    for term, begin, end in dates:
        s[term] = [0, 0]
    return s


def config_csvwriter(dates, data_file):
    # create the csv writer object
    csv_writer = csv.writer(data_file)

    header = list(["college", "all-users", "all-users-ever-active"])
    header.extend(list(map(lambda row: row[0], dates)))
    csv_writer.writerow(header)
    return csv_writer


def write_csvwriter_stats(csv_writer, stats):
    row = ["Total"] + list(map(lambda c: c[0], stats.values()))
    csv_writer.writerow(row)
    row = ["Total Schools > 5 Users"] + list(map(lambda c: c[1], stats.values()))
    csv_writer.writerow(row)


def main(process_all, one):
    data_file = open('users.csv', 'w')
    # 2024 would be Fall 2024 and Spring 2025
    dates = generate_dates(2022, 2024)
    stats = config_stats(dates)
    csv_writer = config_csvwriter(dates, data_file)
    f = open('pilots.json')
    data = json.load(f)
    for pilot in data["pilots"]:
        if process_all or pilot["url"] == one:
            p = process_pilot(pilot, dates, stats)
            csv_writer.writerow(p.values())
    write_csvwriter_stats(csv_writer, stats)
    data_file.close()


# process_all = True
# one = None
# if len(sys.argv) > 1:
#     process_all = False
#     one = sys.argv[1]
# main(process_all, one)
