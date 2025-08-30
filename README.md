# cloudbank-pilot-hub-users

This repository collects and analyzes user activity data from multiple JupyterHub deployments for various colleges and universities as well as reports the number of users that have used otter-service-standalone by week.

## Setup

1. **Install dependencies**  
   Create a virtual environment and install required packages:
   ```sh
   conda activate cloudbank-pilot-hub-users
   pip install -r requirements.txt
   ```

2. **Configure Google Cloud Project**  
   Set your GCP project:
   ```sh
   gcloud config set project data8x-scratch
   ```

3. **Decrypt pilot tokens**  
   The `main.py` script will automatically decrypt `enc-pilots.json` into `pilots.json` using [sops](https://github.com/mozilla/sops).  
   Ensure you have access to the required GCP KMS key used in the cal-icor project

## Usage

Run the main script to collect user statistics and notebook usage:
```sh
python3 main.py; or
./main.py
```
This will:
- Decrypt pilot tokens
- Collect user activity data from all pilots (see [`users.py`](users.py))
- Collect notebook usage statistics (see [`otter_standalone_use.py`](otter_standalone_use.py))
- Write results to `users.csv` and `otter_standalone_use.csv`

If you want to process just one hub and not all of them to see the number of users:
```sh
python3 user.py [hub_name]  ==> e.g. python3 users.py ccsf
```

## Scripts

- [`main.py`](main.py): Orchestrates data collection and decryption.
- [`users.py`](users.py): Fetches user data from each JupyterHub, computes statistics per term, and writes to `users.csv`.
- [`otter_standalone_use.py`](otter_standalone_use.py): Collects notebook usage statistics from Firestore and writes to `otter_standalone_use.csv`.

## Data Files

- `enc-pilots.json`: Encrypted pilot tokens and metadata.
- `pilots.json`: Decrypted pilot tokens (generated at runtime) and not committed by entry in .gitignore
- `users.csv`: User statistics per pilot and term.
- `otter_standalone_use.csv`: Notebook usage statistics.

## Notes

- Do not commit `pilots.json`, `users.csv`, or `otter_standalone_use.csv` (see `.gitignore`).
- You may need access to GCP KMS for decryption.

## License

See repository for license