import csv
import sys
import json
import datetime as d
from datetime import datetime
from dateutil.relativedelta import relativedelta
import requests


def filter_users(func, users):
    return len(list(filter(func, users)))

# Function to convert string to datetime
def convert(datetime_str):     
    date_time_obj = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%fZ')
    return date_time_obj

def users_active_since_date(begin_d, end_d, users):
    users = list(filter(lambda user: user["last_activity"], users))
    def process(user):
        la = convert(user["last_activity"])
        return la > begin_d and la <  end_d
    return len(list(filter(lambda user: process(user), users)))

def get_users(url, token):
    api_url =f'http://{url}.cloudbank.2i2c.cloud/hub/api'
    if url == "mills":
        api_url =f'http://datahub.{url}.edu/hub/api'
    r = requests.get(api_url + '/users',
        headers={
            'Authorization': f'token {token}',
        }
    )
    r.raise_for_status()
    users = r.json()
    return users

def process_pilot(pilot):
    p = {}
    users = get_users(pilot["url"], pilot["token"]) if pilot["token"] else None
    if users:
        users = list(filter(lambda user: not "admin" in user["roles"] and "@" in user["name"], users))
        p["number_all_users"] = len(users)
        p["number_all_users_ever_active"] = filter_users(lambda user: user["last_activity"], users)
        p["number_all_users_ever_active_fall"] = users_active_since_date(fall_begin_date, fall_end_date, users)
        p["number_all_users_ever_active_spring"] = users_active_since_date(spring_begin_date, spring_end_date, users)
        row= list([pilot["name"],p["number_all_users"],p["number_all_users_ever_active"],p["number_all_users_ever_active_fall"],p["number_all_users_ever_active_spring"]])
        csv_writer.writerow(row)
    
    stats[pilot["url"]] = p

data_file = open('numbers.csv', 'w')
fall_begin_date = datetime(2022, 7, 15, 0, 0, 0, 0)
fall_end_date = datetime(2022, 12, 31, 0, 0, 0, 0)
spring_begin_date = datetime(2023, 1, 1, 0, 0, 0, 0)
spring_end_date = datetime(2023, 6, 1, 0, 0, 0, 0)
process_all = True
if len(sys.argv) > 1:
    process_all = False
    one = sys.argv[1]

# create the csv writer object
csv_writer = csv.writer(data_file)
stats = {}
header = list(["college","all-users", "all-users-ever-active", "all-users-active-fall(since 2022-07-15)","all-users-active-spring(since 2023-01-01)"])
csv_writer.writerow(header)

f = open('pilots.json')
data = json.load(f)

for pilot in data["pilots"]:
    if process_all or pilot["url"] == one:
        process_pilot(pilot)
 
data_file.close()
