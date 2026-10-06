"""Daily / weekly / monthly active users -> data/active_{daily,weekly,monthly}.csv.

JupyterHub reports, at each moment, how many users were active in the trailing
24h / 7d / 30d (`jupyterhub_active_users`). Sampled at 23:59 PT of each day,
each Sunday and each month-end, that is real daily, weekly (Mon-Sun) and
monthly active users. Unlike users.csv it does not depend on hubs keeping their
accounts, so it survives the kind of account loss CloudBank had in Aug 2026.

  cloudbank  CloudBank Prometheus (PROM_USER / PROM_PASS), all hubs but staging
  icor       the CSVs cal-icor/hub-users-page commits nightly from the
             Cal-ICOR Prometheus

Each run upserts, so history outlives Prometheus retention.
"""

import base64
import datetime
import io
import json
import os
import urllib.parse
import urllib.request
import zoneinfo
from pathlib import Path

import pandas as pd

PT = zoneinfo.ZoneInfo("America/Los_Angeles")
DATA = Path(__file__).resolve().parent.parent / "data"
PROM_URL = "https://prometheus.cloudbank.2i2c.cloud"
QUERY = 'sum(jupyterhub_active_users{{period="{period}", namespace!="staging"}})'
ICOR_CSV = "https://raw.githubusercontent.com/cal-icor/hub-users-page/main/data/{name}.csv"
START = datetime.date(2025, 1, 1)


def prom_range(period, start, end):
    """{date: users} for the trailing-`period` gauge at 23:59 PT each day."""
    auth = base64.b64encode(f"{os.environ['PROM_USER']}:{os.environ['PROM_PASS']}".encode()).decode()
    first = datetime.datetime.combine(start, datetime.time(23, 59), PT)
    last = datetime.datetime.combine(end, datetime.time(23, 59), PT) + datetime.timedelta(hours=2)
    params = {"query": QUERY.format(period=period), "start": first.timestamp(),
              "end": last.timestamp(), "step": 86400}
    req = urllib.request.Request(f"{PROM_URL}/api/v1/query_range?" + urllib.parse.urlencode(params))
    req.add_header("Authorization", "Basic " + auth)
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.load(resp)["data"]["result"]
    if not result:
        return {}
    # Samples are 86400s apart from a PST start, so in PDT they land at 00:59
    # the next day. Labelling by (sample - 2h) gives the right date either way.
    return {
        datetime.datetime.fromtimestamp(float(t) - 7200, PT).date(): int(float(v))
        for t, v in result[0]["values"]
    }


def icor(name, key):
    with urllib.request.urlopen(ICOR_CSV.format(name=name), timeout=60) as resp:
        df = pd.read_csv(io.StringIO(resp.read().decode()))
    return df.rename(columns={"users": "icor"})[[key, "icor"]]


def upsert(name, df, key):
    path = DATA / name
    df = df.set_index(key)
    if path.is_file():
        # New values win, but a column this run could not fetch keeps its history.
        df = df.combine_first(pd.read_csv(path).set_index(key))
    df = df.sort_index().reset_index()
    df.to_csv(path, index=False, float_format="%.0f")
    print(f"  {name}: {len(df)} rows")


def main():
    DATA.mkdir(exist_ok=True)
    yesterday = datetime.datetime.now(PT).date() - datetime.timedelta(days=1)

    daily = prom_range("24h", START, yesterday)
    weekly = {d: v for d, v in prom_range("7d", START, yesterday).items() if d.weekday() == 6}
    monthly = {d: v for d, v in prom_range("30d", START, yesterday).items()
               if (d + datetime.timedelta(days=1)).day == 1}

    d = pd.DataFrame({"date": [str(k) for k in daily], "cloudbank": list(daily.values())})
    w = pd.DataFrame({"week_start": [str(k - datetime.timedelta(days=6)) for k in weekly],
                      "cloudbank": list(weekly.values())})
    m = pd.DataFrame({"month": [k.strftime("%Y-%m") for k in monthly], "cloudbank": list(monthly.values())})

    try:
        d = d.merge(icor("daily", "date"), on="date", how="outer")
        w = w.merge(icor("weekly", "week_start"), on="week_start", how="outer")
        m = m.merge(icor("monthly", "month"), on="month", how="outer")
    except Exception as e:  # the ICOR page is a convenience; never block CloudBank on it
        print(f"  WARNING: could not read ICOR active users: {e}")

    upsert("active_daily.csv", d, "date")
    upsert("active_weekly.csv", w, "week_start")
    upsert("active_monthly.csv", m, "month")


if __name__ == "__main__":
    main()
