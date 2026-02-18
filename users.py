"""
users.py

Collects user statistics from multiple JupyterHub deployments for various colleges and universities.
Fetches user data via REST API, computes statistics for each academic term, and writes results to a CSV file.

Usage:
    python users.py           # Process all pilots
    python users.py <hub>     # Process a single pilot by hub name

Outputs:
    - users.csv: User statistics per pilot and term

Requires:
    - pilots.json: Decrypted pilot tokens and metadata
"""

import csv
import json
import sys
from datetime import datetime
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


def filter_users(func, users):
    """
    Returns the count of users matching the filter function.

    Args:
        func (callable): Function to filter users.
        users (list): List of user dicts.

    Returns:
        int: Number of users matching the filter.
    """
    return len(list(filter(func, users)))


# Function to convert string to datetime
def convert(datetime_str):
    """
    Converts an ISO datetime string to a datetime object.

    Args:
        datetime_str (str): Datetime string in ISO format.

    Returns:
        datetime: Parsed datetime object.
    """
    try:
        date_time_obj = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%fZ')
    except Exception:
        datetime_str = datetime_str[:-1] + ".0000Z"
        date_time_obj = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%fZ')
    return date_time_obj


def users_active_since_date(begin_d, end_d, users):
    """
    Counts users with last activity between begin_d and end_d.

    Args:
        begin_d (datetime): Start date.
        end_d (datetime): End date.
        users (list): List of user dicts.

    Returns:
        int: Number of active users in the date range.
    """
    users = list(filter(lambda user: user["last_activity"], users))

    def process(user):
        la = convert(user["last_activity"])
        return la > begin_d and la < end_d

    return len(list(filter(lambda user: process(user), users)))


def get_users(url, where, token):
    """
    Fetches user data from the JupyterHub API.

    Args:
        url (str): Hub URL prefix.
        where (str): Deployment type.
        token (str): API token.

    Returns:
        list: List of user dicts.
    """
    all_data = []
    api_url = f'http://{url}.cloudbank.2i2c.cloud/hub/api'
    if url == "mills":
        api_url = f'http://datahub.{url}.edu/hub/api'
    if where == "icor":
        api_url = f'http://{url}.jupyter.cal-icor.org/hub/api'
    offset = 0
    while True:
        r = requests.get(
            api_url + f'/users?limit=200&offset={offset}',
            headers={
                'Authorization': f'token {token}'
            }
        )
        if r.status_code == 403:
            print(f"{url}: 403 error")
            return []
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("Error getting users")
        r.raise_for_status()
        data = r.json()
        all_data.extend(data)
        # Stop if we got fewer than 200 users (indicating end of results)
        if len(data) < 200:
            break
        offset += 200
    return all_data


def process_pilot(pilot, dates):
    """
    Processes a single pilot, collecting user statistics for each term.

    Args:
        pilot (dict): Pilot metadata.
        dates (list): List of (term, begin, end) tuples.

    Returns:
        dict: Statistics for the pilot.
    """
    p = {}
    print(f"Processing {pilot['name']} ({pilot['url']})")
    users = get_users(pilot["url"], pilot["where"], pilot["token"])
    if users:
        users = list(filter(lambda user: "admin" not in user["roles"] and user['admin'] is False and "service-hub" not in user['name'] and "deployment-service" not in user['name'], users))
        p["name"] = pilot["name"]
        p["where"] = pilot["where"]
        p["number_all_users"] = len(users)
        p["number_all_users_ever_active"] = filter_users(lambda user: user["last_activity"], users)
        for term, begin, end in dates:
            p[term] = users_active_since_date(begin, end, users)
    
    return p


def generate_dates(start_year, end_year):
    """
    Generates academic term date ranges for summer, fall, and spring.

    Args:
        start_year (int): Start year.
        end_year (int): End year.

    Returns:
        list: List of (term, begin, end) tuples.
    """
    dates = []
    for year in range(start_year, end_year + 1):
        # Summer semester
        summer_begin = datetime(year, 6, 15, 0, 0, 0, 0)
        summer_end = datetime(year, 8, 10, 0, 0, 0, 0)
        dates.append((f"summer_{year}", summer_begin, summer_end))

        # Fall semester
        fall_begin = datetime(year, 8, 11, 0, 0, 0, 0)
        fall_end = datetime(year, 12, 31, 0, 0, 0, 0)
        dates.append((f"fall_{year}", fall_begin, fall_end))

        # Spring semester (spills into next year)
        spring_begin = datetime(year + 1, 1, 1, 0, 0, 0, 0)
        spring_end = datetime(year + 1, 6, 14, 0, 0, 0, 0)
        dates.append((f"spring_{year + 1}", spring_begin, spring_end))
    return dates


def config_stats(dates):
    """
    Initializes statistics dictionary for all terms.

    Args:
        dates (list): List of (term, begin, end) tuples.

    Returns:
        dict: Stats dictionary.
    """
    s = {}
    s["all-users"] = [0, 0]
    s["all-users-ever-active"] = [0, 0]
    for term, begin, end in dates:
        s[term] = [0, 0]
    return s


def config_csvwriter(dates, data_file):
    """
    Configures CSV writer and writes header row.

    Args:
        dates (list): List of (term, begin, end) tuples.
        data_file (file): Open file object.

    Returns:
        csv.writer: CSV writer object.
    """
    csv_writer = csv.writer(data_file)

    header = list(["college", "where", "all-users", "all-users-ever-active"])
    header.extend(list(map(lambda row: row[0], dates)))
    csv_writer.writerow(header)
    return csv_writer


def write_csvwriter_stats(csv_writer, stats):
    """
    Writes summary statistics rows to the CSV file.

    Args:
        csv_writer (csv.writer): CSV writer object.
        stats (dict): Aggregated statistics.
    """
    row = ["Total", ""] + list(map(lambda c: c[0], stats.values()))
    csv_writer.writerow(row)
    row = ["Total Schools > 5 Users", ""] + list(map(lambda c: c[1], stats.values()))
    csv_writer.writerow(row)


def get_current_academic_year():
    """
    Gets the first year of the current academmic year: 
    Current Academic year: 2025-26 ==> 2025
    
    Returns:
        integer: beginning year of current academic year
    """
    today = datetime.today()
    year = today.year
    month = today.month

    # Academic year starts in summer (June)
    if month >= 6:
        return year
    else:
        return year - 1


def main(process_all, one):
    """
    Main entry point. Processes pilots and writes statistics to CSV.

    Args:
        process_all (bool): If True, process all pilots. If False, process one.
        one (str): Hub name to process if not all.
    """
    data_file = open('users.csv', 'w')
    dates = generate_dates(2022, get_current_academic_year())
    stats = config_stats(dates)
    csv_writer = config_csvwriter(dates, data_file)
    f = open('pilots.json')
    data = json.load(f)
    
    # Filter pilots to process
    pilots_to_process = [pilot for pilot in data["pilots"] 
                         if process_all or pilot["url"] == one]
    
    # Process pilots in parallel using ThreadPoolExecutor
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all pilot processing tasks
        future_to_pilot = {executor.submit(process_pilot, pilot, dates): pilot 
                          for pilot in pilots_to_process}
        
        # Collect results as they complete
        for future in as_completed(future_to_pilot):
            pilot = future_to_pilot[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as exc:
                print(f"{pilot['name']} generated an exception: {exc}")
    # Aggregate statistics and write to CSV
    for p in results:
        csv_writer.writerow(p.values())
        
        # Update aggregate statistics
        if "number_all_users" in p:
            stats["all-users"][0] += p["number_all_users"]
        if "number_all_users_ever_active" in p:
            stats["all-users-ever-active"][0] += p["number_all_users_ever_active"]

        for term, begin, end in dates:
            if term in p:
                stats[term][0] += p[term]
                if p[term] > 5:
                    stats[term][1] += 1
    write_csvwriter_stats(csv_writer, stats)
    data_file.close()


if __name__ == "__main__":
    process_all = True
    one = None
    if len(sys.argv) > 1:
        process_all = False
        one = sys.argv[1]
    main(process_all, one)
