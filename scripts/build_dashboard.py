import json
import pandas as pd
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).parent.parent
DOCS_DIR = BASE_DIR / "docs"

# -- Load users.csv --
users_df = pd.read_csv(BASE_DIR / "users.csv")

# Remove summary rows
users_df = users_df[~users_df["college"].isin(["Total", "Total Schools > 5 Users"])]

# Semester columns are everything after the fixed metadata columns
fixed_cols = ["college", "where", "all-users", "all-users-ever-active"]
semester_cols = [c for c in users_df.columns if c not in fixed_cols]

cloudbank_df = users_df[users_df["where"] == "cloudbank"]
icor_df      = users_df[users_df["where"] == "icor"]

semester_data = [
    {
        "semester": col,
        "cloudbank": int(cloudbank_df[col].sum()),
        "icor":      int(icor_df[col].sum()),
    }
    for col in semester_cols
]

# Current + 3 previous semesters for the table
recent_sems = semester_cols[-4:]
current_sem = recent_sems[-1]

institutions = (
    users_df[["college", "where", "all-users", "all-users-ever-active"] + recent_sems]
    .sort_values(current_sem, ascending=False)
    .to_dict(orient="records")
)

# -- Load otter_standalone_use.csv --
otter_df = pd.read_csv(BASE_DIR / "otter_standalone_use.csv", skiprows=1, skipinitialspace=True)
otter_df.columns = [c.strip() for c in otter_df.columns]

monthly_otter = (
    otter_df.groupby("Year-Month", sort=True)
    .agg({"Number of Users": "sum", "Number of Notebooks": "sum"})
    .reset_index()
    .to_dict(orient="records")
)

# -- Build HTML --
updated          = date.today().isoformat()
semester_json     = json.dumps(semester_data)
institutions_json = json.dumps(institutions)
otter_json        = json.dumps(monthly_otter)
recent_sems_json  = json.dumps(recent_sems)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CloudBank Pilot Hub Users</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: #f5f5f5; color: #222; padding: 2rem; }}
    h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
    .updated {{ color: #888; font-size: 0.85rem; margin-bottom: 2rem; }}
    .card {{ background: #fff; border-radius: 8px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    h2 {{ font-size: 1.1rem; margin-bottom: 1rem; }}
    canvas {{ max-height: 320px; }}
    input {{ width: 100%; padding: 0.5rem 0.75rem; border: 1px solid #ddd; border-radius: 6px; font-size: 0.9rem; margin-bottom: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 2px solid #eee; color: #555; }}
    td {{ padding: 0.45rem 0.75rem; border-bottom: 1px solid #f0f0f0; }}
    tr:hover td {{ background: #fafafa; }}
    .cloudbank {{ color: #4e79a7; font-weight: 500; }}
    .icor {{ color: #f28e2b; font-weight: 500; }}
    .zero {{ color: #bbb; }}
  </style>
</head>
<body>
  <h1>CloudBank Pilot Hub Users</h1>
  <p class="updated">Last updated: {updated}</p>

  <div class="card">
    <h2>Active Users by Semester</h2>
    <canvas id="semesterChart"></canvas>
  </div>

  <div class="card">
    <h2>Otter Standalone Monthly Usage</h2>
    <canvas id="otterChart"></canvas>
  </div>

  <div class="card">
    <h2>Institutions &mdash; {current_sem}</h2>
    <input type="text" id="search" placeholder="Search by institution..." />
    <table>
      <thead>
        <tr>
          <th>Institution</th>
          <th>Program</th>
          <th>All Users</th>
          <th>{recent_sems[0]}</th>
          <th>{recent_sems[1]}</th>
          <th>{recent_sems[2]}</th>
          <th>{recent_sems[3]}</th>
        </tr>
      </thead>
      <tbody id="table-body"></tbody>
    </table>
  </div>

  <script>
    const semesters    = {semester_json};
    const institutions = {institutions_json};
    const otter        = {otter_json};
    const recentSems   = {recent_sems_json};

    // --- Semester chart ---
    new Chart(document.getElementById("semesterChart"), {{
      type: "bar",
      data: {{
        labels: semesters.map(r => r.semester),
        datasets: [
          {{ label: "CloudBank", data: semesters.map(r => r.cloudbank), backgroundColor: "#4e79a7" }},
          {{ label: "ICOR",      data: semesters.map(r => r.icor),      backgroundColor: "#f28e2b" }},
        ]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ position: "top" }} }},
        scales: {{ x: {{ stacked: false }}, y: {{ beginAtZero: true, ticks: {{ precision: 0 }} }} }}
      }}
    }});

    // --- Otter chart ---
    new Chart(document.getElementById("otterChart"), {{
      type: "line",
      data: {{
        labels: otter.map(r => r["Year-Month"]),
        datasets: [
          {{
            label: "Users",
            data: otter.map(r => r["Number of Users"]),
            borderColor: "#4e79a7",
            backgroundColor: "rgba(78,121,167,0.1)",
            tension: 0.3,
            fill: true
          }},
          {{
            label: "Notebooks",
            data: otter.map(r => r["Number of Notebooks"]),
            borderColor: "#59a14f",
            backgroundColor: "rgba(89,161,79,0.1)",
            tension: 0.3,
            fill: true
          }},
        ]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ position: "top" }} }},
        scales: {{ y: {{ beginAtZero: true, ticks: {{ precision: 0 }} }} }}
      }}
    }});

    // --- Institution table ---
    const tbody = document.getElementById("table-body");

    function renderTable(rows) {{
      tbody.innerHTML = rows.map(r => `
        <tr>
          <td>${{r.college}}</td>
          <td><span class="${{r.where}}">${{r.where}}</span></td>
          <td>${{Number(r["all-users"]).toLocaleString()}}</td>
          ${{recentSems.map(s => `<td class="${{r[s] === 0 ? "zero" : ""}}">${{r[s]}}</td>`).join("")}}
        </tr>`).join("");
    }}

    renderTable(institutions);

    document.getElementById("search").addEventListener("input", e => {{
      const q = e.target.value.toLowerCase();
      renderTable(institutions.filter(r => r.college.toLowerCase().includes(q)));
    }});
  </script>
</body>
</html>
"""

DOCS_DIR.mkdir(exist_ok=True)
(DOCS_DIR / "index.html").write_text(html)
print(f"Dashboard written to {DOCS_DIR / 'index.html'}")
