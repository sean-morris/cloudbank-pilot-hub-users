import json
import pandas as pd
from pathlib import Path
from datetime import date, timedelta

BASE_DIR = Path(__file__).parent.parent
DOCS_DIR = BASE_DIR / "docs"


def resolve_week_start(year_month, week_number):
    year, month = map(int, str(year_month).split("-"))
    month_anchor = date(year, month, 1)
    candidates = []

    for iso_year in (year - 1, year, year + 1):
        try:
            week_start = date.fromisocalendar(iso_year, int(week_number), 1)
        except ValueError:
            continue

        week_end = week_start + timedelta(days=6)
        score = 0
        if week_start.year == year and week_start.month == month:
            score += 2
        if week_end.year == year and week_end.month == month:
            score += 2
        if week_start.year == year or week_end.year == year:
            score += 1

        distance = min(
            abs((week_start - month_anchor).days),
            abs((week_end - month_anchor).days),
        )
        candidates.append((score, -distance, week_start.toordinal(), week_start))

    if not candidates:
        raise ValueError(f"Unable to resolve week {week_number} for {year_month}")

    return max(candidates)[-1]


def format_semester_label(semester):
    season, year = semester.split("_", 1)
    return f"{season.title()} {year}"


# -- Load users.csv --
users_df = pd.read_csv(BASE_DIR / "users.csv")

# Remove summary rows
users_df = users_df[~users_df["college"].isin(["Total", "Total Schools > 5 Users"])]

# Semester columns are everything after the fixed metadata columns
fixed_cols = ["college", "where", "all-users", "all-users-ever-active"]
semester_cols = [c for c in users_df.columns if c not in fixed_cols]

cloudbank_df = users_df[users_df["where"] == "cloudbank"]
icor_df = users_df[users_df["where"] == "icor"]

semester_data = []
for col in semester_cols:
  semester_data.append(
    {
      "semester": col,
      "cloudbank": int(cloudbank_df[col].sum()),
      "icor": int(icor_df[col].sum()),
    }
  )

# Current + 3 previous semesters for the table
recent_sems = semester_cols[-4:]
current_sem = recent_sems[-1]
current_sem_label = format_semester_label(current_sem)

institution_threshold = 5
current_institution_counts = {
    "cloudbank": int((cloudbank_df[current_sem] > institution_threshold).sum()),
    "icor": int((icor_df[current_sem] > institution_threshold).sum()),
}

institutions = (
    users_df[["college", "where", "all-users", "all-users-ever-active"] + recent_sems]
    .sort_values(current_sem, ascending=False)
    .to_dict(orient="records")
)

# -- Load otter_standalone_use.csv --
otter_df = pd.read_csv(BASE_DIR / "otter_standalone_use.csv", skiprows=1, skipinitialspace=True)
otter_df.columns = [c.strip() for c in otter_df.columns]

otter_df["week_start"] = pd.to_datetime(
    otter_df.apply(lambda row: resolve_week_start(row["Year-Month"], row["Week Of Year"]), axis=1)
)

weekly_otter_df = (
    otter_df.groupby("week_start", sort=True)
    .agg({"Number of Users": "sum", "Number of Notebooks": "sum"})
    .reset_index()
)

latest_week = weekly_otter_df.iloc[-1]
latest_week_label = latest_week["week_start"].strftime("%b %-d, %Y")

otter_cutoff = weekly_otter_df["week_start"].max() - pd.DateOffset(months=12)
weekly_otter = weekly_otter_df[weekly_otter_df["week_start"] >= otter_cutoff].copy()
weekly_otter["label"] = weekly_otter["week_start"].dt.strftime("%Y-%m-%d")
weekly_otter["week_start"] = weekly_otter["week_start"].dt.strftime("%Y-%m-%d")
weekly_otter = weekly_otter.to_dict(orient="records")

summary_cards = [
    {
        "label": f"CloudBank Institutions > {institution_threshold}",
        "value": current_institution_counts["cloudbank"],
        "detail": current_sem_label,
    },
    {
        "label": f"ICOR Institutions > {institution_threshold}",
        "value": current_institution_counts["icor"],
        "detail": current_sem_label,
    },
    {
        "label": "Notebooks Graded This Week",
        "value": int(latest_week["Number of Notebooks"]),
        "detail": latest_week_label,
    },
    {
        "label": "Submissions This Week",
        "value": int(latest_week["Number of Users"]),
        "detail": latest_week_label,
    },
]

# -- Build HTML --
updated = date.today().isoformat()
recent_sem_labels = {s: format_semester_label(s) for s in recent_sems}
semester_json = json.dumps(semester_data)
institutions_json = json.dumps(institutions)
otter_json = json.dumps(weekly_otter)
recent_sems_json = json.dumps(recent_sems)
recent_sem_labels_json = json.dumps(recent_sem_labels)
current_sem_json = json.dumps(current_sem)

# Default the table sort to the most recent term that actually has data, so
# the dashboard doesn't open sorted by an all-zero future term (e.g. spring_2027).
default_sort_sem = next(
    (s for s in reversed(recent_sems) if int(users_df[s].sum()) > 0),
    current_sem,
)
default_sort_json = json.dumps(default_sort_sem)
summary_json = json.dumps(summary_cards)

# Pre-render the semester <option>s for the term filter
sem_options_html = "".join(
    f'<option value="{s}">{recent_sem_labels[s]}</option>' for s in recent_sems
)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Cal-ICOR and CloudBank Pilot Hub Users</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: #f5f5f5; color: #222; padding: 2rem; }}
    h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
    .updated {{ color: #888; font-size: 0.85rem; margin-bottom: 2rem; }}
    .card {{ background: #fff; border-radius: 8px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    h2 {{ font-size: 1.1rem; margin-bottom: 1rem; }}
    canvas {{ max-height: 320px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
    .summary-card {{ background: #fff; border-radius: 8px; padding: 1.25rem; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
    .summary-label {{ color: #666; font-size: 0.85rem; margin-bottom: 0.5rem; }}
    .summary-value {{ font-size: 1.8rem; font-weight: 700; line-height: 1.1; }}
    .summary-detail {{ color: #888; font-size: 0.8rem; margin-top: 0.35rem; }}
    .table-header {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }}
    .table-header h2 {{ margin-bottom: 0; }}
    .controls {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; }}
    .segmented {{ display: inline-flex; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; background: #fff; }}
    .segmented button {{ border: 0; background: transparent; padding: 0.4rem 0.85rem; font-size: 0.85rem; color: #555; cursor: pointer; border-left: 1px solid #eee; }}
    .segmented button:first-child {{ border-left: 0; }}
    .segmented button:hover {{ background: #f5f5f5; }}
    .segmented button.active {{ background: #4e79a7; color: #fff; }}
    select {{ padding: 0.4rem 0.6rem; border: 1px solid #ddd; border-radius: 6px; font-size: 0.85rem; background: #fff; color: #333; cursor: pointer; }}
    input {{ width: 100%; padding: 0.5rem 0.75rem; border: 1px solid #ddd; border-radius: 6px; font-size: 0.9rem; margin-bottom: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 2px solid #eee; color: #555; cursor: pointer; user-select: none; white-space: nowrap; }}
    th:hover {{ color: #4e79a7; }}
    th.num, td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    th .arrow {{ color: #4e79a7; font-size: 0.75rem; margin-left: 0.25rem; }}
    td {{ padding: 0.45rem 0.75rem; border-bottom: 1px solid #f0f0f0; }}
    tr:hover td {{ background: #fafafa; }}
    .badge {{ display: inline-block; padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
    .badge.cloudbank {{ background: rgba(78,121,167,0.15); color: #3a5e85; }}
    .badge.icor {{ background: rgba(242,142,43,0.18); color: #b3641a; }}
    .zero {{ color: #bbb; }}
    .empty {{ color: #888; font-size: 0.9rem; padding: 1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>Cal-ICOR and CloudBank Pilot Hub Users</h1>
  <p class="updated">Last updated: {updated}</p>

  <div class="summary-grid" id="summary-grid"></div>

  <div class="card">
    <h2>Active Users by Semester</h2>
    <canvas id="semesterChart"></canvas>
  </div>

  <div class="card">
    <h2>Otter Standalone Weekly Usage</h2>
    <canvas id="otterChart"></canvas>
  </div>

  <div class="card">
    <div class="table-header">
      <h2>Institutions</h2>
      <div class="controls">
        <div class="segmented" id="program-filter">
          <button data-program="all" class="active">All</button>
          <button data-program="cloudbank">CloudBank</button>
          <button data-program="icor">ICOR</button>
        </div>
        <select id="semester-filter">
          <option value="all">All recent semesters</option>
          {sem_options_html}
        </select>
      </div>
    </div>
    <input type="text" id="search" placeholder="Search by institution..." />
    <table id="inst-table">
      <thead id="table-head"></thead>
      <tbody id="table-body"></tbody>
    </table>
    <p class="empty" id="empty-msg" hidden>No institutions match the current filters.</p>
  </div>

  <script>
    const semesters       = {semester_json};
    const institutions    = {institutions_json};
    const otter           = {otter_json};
    const recentSems      = {recent_sems_json};
    const recentSemLabels = {recent_sem_labels_json};
    const currentSem      = {current_sem_json};
    const defaultSort     = {default_sort_json};
    const summaries       = {summary_json};

    // --- Summary cards ---
    const summaryGrid = document.getElementById("summary-grid");
    summaryGrid.innerHTML = summaries.map(item => `
      <div class="summary-card">
        <div class="summary-label">${{item.label}}</div>
        <div class="summary-value">${{Number(item.value).toLocaleString()}}</div>
        <div class="summary-detail">${{item.detail}}</div>
      </div>
    `).join("");

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
        labels: otter.map(r => r.label),
        datasets: [
          {{
            label: "Submissions",
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
        scales: {{
          x: {{ ticks: {{ maxTicksLimit: 12 }} }},
          y: {{ beginAtZero: true, ticks: {{ precision: 0 }} }}
        }}
      }}
    }});

    // --- Institution table (sortable + filterable) ---
    const thead = document.getElementById("table-head");
    const tbody = document.getElementById("table-body");
    const emptyMsg = document.getElementById("empty-msg");

    const programLabels = {{ cloudbank: "CloudBank", icor: "ICOR" }};
    const state = {{ program: "all", semester: "all", search: "", sortKey: defaultSort, sortDir: "desc" }};

    function visibleColumns() {{
      const cols = [
        {{ key: "college",   label: "Institution", type: "str" }},
        {{ key: "where",     label: "Program",     type: "str" }},
        {{ key: "all-users", label: "All Users",   type: "num" }},
      ];
      const sems = state.semester === "all" ? recentSems : [state.semester];
      sems.forEach(s => cols.push({{ key: s, label: recentSemLabels[s], type: "num" }}));
      return cols;
    }}

    function applyFilters() {{
      const q = state.search.toLowerCase();
      return institutions.filter(r =>
        (state.program === "all" || r.where === state.program) &&
        r.college.toLowerCase().includes(q)
      );
    }}

    function sortRows(rows) {{
      const {{ sortKey, sortDir }} = state;
      const dir = sortDir === "asc" ? 1 : -1;
      return rows.slice().sort((a, b) => {{
        let va = a[sortKey], vb = b[sortKey];
        if (typeof va === "number" || typeof vb === "number") {{
          return ((va || 0) - (vb || 0)) * dir;
        }}
        return String(va).localeCompare(String(vb)) * dir;
      }});
    }}

    function render() {{
      const cols = visibleColumns();

      thead.innerHTML = "<tr>" + cols.map(c => {{
        const arrow = c.key === state.sortKey
          ? `<span class="arrow">${{state.sortDir === "asc" ? "\\u25B2" : "\\u25BC"}}</span>` : "";
        return `<th data-key="${{c.key}}" class="${{c.type === "num" ? "num" : ""}}">${{c.label}}${{arrow}}</th>`;
      }}).join("") + "</tr>";

      thead.querySelectorAll("th").forEach(th => {{
        th.addEventListener("click", () => {{
          const key = th.dataset.key;
          if (state.sortKey === key) {{
            state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
          }} else {{
            state.sortKey = key;
            state.sortDir = key === "college" || key === "where" ? "asc" : "desc";
          }}
          render();
        }});
      }});

      const rows = sortRows(applyFilters());
      emptyMsg.hidden = rows.length > 0;

      tbody.innerHTML = rows.map(r => "<tr>" + cols.map(c => {{
        if (c.key === "college") return `<td>${{r.college}}</td>`;
        if (c.key === "where") {{
          return `<td><span class="badge ${{r.where}}">${{programLabels[r.where] || r.where}}</span></td>`;
        }}
        const val = r[c.key];
        const cls = "num" + (val === 0 ? " zero" : "");
        return `<td class="${{cls}}">${{Number(val).toLocaleString()}}</td>`;
      }}).join("") + "</tr>").join("");
    }}

    document.getElementById("program-filter").addEventListener("click", e => {{
      const btn = e.target.closest("button");
      if (!btn) return;
      state.program = btn.dataset.program;
      document.querySelectorAll("#program-filter button")
        .forEach(b => b.classList.toggle("active", b === btn));
      render();
    }});

    document.getElementById("semester-filter").addEventListener("change", e => {{
      state.semester = e.target.value;
      // If the active sort column was hidden, fall back to the latest visible term
      if (state.semester !== "all" && recentSems.includes(state.sortKey) && state.sortKey !== state.semester) {{
        state.sortKey = state.semester;
        state.sortDir = "desc";
      }}
      render();
    }});

    document.getElementById("search").addEventListener("input", e => {{
      state.search = e.target.value;
      render();
    }});

    render();
  </script>
</body>
</html>
"""

DOCS_DIR.mkdir(exist_ok=True)
(DOCS_DIR / "index.html").write_text(html)
print(f"Dashboard written to {DOCS_DIR / 'index.html'}")
