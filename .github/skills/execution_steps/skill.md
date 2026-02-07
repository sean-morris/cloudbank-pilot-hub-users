# Main.py Execution Steps

**Date:** February 7, 2026  
**Project:** cloudbank-pilot-hub-users

## Prerequisites Verification

### 1. Check Conda Environment
```bash
conda env list | grep cloudbank-pilot-hub-users
```
**Result:** Environment found at `/opt/miniconda3/envs/cloudbank-pilot-hub-users`

### 2. Activate Conda Environment
```bash
source /opt/miniconda3/bin/activate cloudbank-pilot-hub-users
```
**Result:** Environment activated successfully ✓

### 3. Verify Conda Environment Activation
```bash
conda info --envs | grep '*'
```
**Result:** `cloudbank-pilot-hub-users *` (active)

### 4. Verify GCloud Project Authentication
```bash
gcloud config get-value project
```
**Result:** `data8x-scratch` ✓ (correct project)

## Execution

### 5. Run main.py
```bash
python main.py
```

**What main.py does:**
- Decrypts pilot tokens from `enc-pilots.json` to `pilots.json` using sops
- Runs user statistics collection (`users.py`) in parallel thread
- Runs notebook usage aggregation (`otter_standalone_use.py`) in parallel thread
- Waits for both tasks to complete

**Output Files Generated:**
- `pilots.json` - Decrypted pilot tokens (runtime only)
- `users.csv` - User statistics per pilot and term
- `otter_standalone_use.csv` - Weekly notebook usage statistics

**Execution Result:** SUCCESS ✓

## Summary

All prerequisites were already properly configured:
- ✓ Conda environment `cloudbank-pilot-hub-users` exists and activated
- ✓ GCloud authenticated to correct project `data8x-scratch`
- ✓ Script executed successfully
- ✓ All pilots processed
- ✓ Output CSV files generated

## User Statistics Analysis

### How to Analyze User Statistics from users.csv

After running `main.py`, analyze the `users.csv` output file:

1. **Open the CSV file:**
   ```bash
   open users.csv
   # or
   cat users.csv
   ```

2. **Identify key columns:**
   - Column 2 (`where`): Shows if institution is `cloudbank` or `icor`
   - Last column with data: Current semester
   - Previous columns: Historical semester data

3. **Calculate totals by filtering the "where" column:**
   - Look at the last row labeled "Total" for overall numbers
   - Sum rows where `where=cloudbank` for CloudBank total
   - Sum rows where `where=icor` for ICOR total

4. **Compare across semesters:**
   - Current semester (spring_2026): Last column
   - Last semester (fall_2025): Second-to-last column
   - Year ago (spring_2025): Look back to same semester previous year



## Otter Standalone Notebook Usage Analysis

### How to Analyze otter_standalone_use.csv

After running `main.py`, analyze the `otter_standalone_use.csv` output file:

1. **Open the CSV file:**
   ```bash
   open otter_standalone_use.csv
   # or
   cat otter_standalone_use.csv
   ```

2. **File structure:**
   - First line: Total number of notebooks (cumulative)
   - Column 1: Year-Month
   - Column 2: Week of Year
   - Column 3: Number of Users (unique users that week)
   - Column 4: Number of Notebooks (notebooks used that week)

3. **Calculate semester totals:**
   - Filter by date range for current semester
   - Sum the users and notebooks columns
   - Compare week-over-week and semester-over-semester


