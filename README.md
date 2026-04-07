# CloudBank Pilot Hub Users

This repository collects and analyzes user activity data from multiple JupyterHub deployments for various colleges and universities as well as reports the number of users that have used otter-service-standalone by week.

## Setup

1. **Install dependencies**  
   Create a virtual environment and install required packages:
   ```sh
   conda activate cloudbank-pilot-hub-users
   pip install -r requirements.txt
   ```

2. **Configure Google Cloud Access**  
   Authenticate with an account that can read Firestore in both projects used for Otter standalone logging. You can set either project as your active default:
   ```sh
   gcloud config set project data8x-scratch
   ```
   The Otter standalone usage script reads from both `data8x-scratch` and `cb-1003-1696` by default.
   The current workflow credential remains `cloudbank-nightly@cal-icor-hubs.iam.gserviceaccount.com`; grant that service account Firestore read access in `cb-1003-1696` and `data8x-scratch`.
    Example commands:
    ```sh
    gcloud projects add-iam-policy-binding cb-1003-1696 \
       --member="serviceAccount:cloudbank-nightly@cal-icor-hubs.iam.gserviceaccount.com" \
       --role="roles/datastore.viewer"

    gcloud projects add-iam-policy-binding data8x-scratch \
       --member="serviceAccount:cloudbank-nightly@cal-icor-hubs.iam.gserviceaccount.com" \
       --role="roles/datastore.viewer"
    ```

3. **Decrypt pilot tokens**  
   The `main.py` script will automatically decrypt `enc-pilots.json` into `pilots.json` using [sops](https://github.com/mozilla/sops).  
   Ensure you have access to the required GCP KMS key used in the `cal-icor-hubs` project.
   Example command:
   ```sh
   gcloud kms keys add-iam-policy-binding sops \
     --location=global \
     --keyring=jupyterhubs \
     --member="serviceAccount:cloudbank-nightly@cal-icor-hubs.iam.gserviceaccount.com" \
     --role="roles/cloudkms.cryptoKeyDecrypter" \
     --project=cal-icor-hubs
   ```

## Usage

Run the main script to collect user statistics and notebook usage:
```sh
python3 main.py; or
./main.py
```
This will:
- Decrypt pilot tokens
- Collect user activity data from all pilots (see [`users.py`](users.py))
- Collect notebook usage statistics from both Firestore projects by default (see [`otter_standalone_use.py`](otter_standalone_use.py))
- Write results to `users.csv` and `otter_standalone_use.csv`

To override the default Firestore project list, set `OTTER_FIRESTORE_PROJECT_IDS`:
```sh
OTTER_FIRESTORE_PROJECT_IDS=cb-1003-1696,data8x-scratch python3 main.py
```

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
- `pilots.json`: Decrypted pilot tokens generated at runtime and excluded by the repository ignore rules.
- `users.csv`: User statistics per pilot and term.
- `otter_standalone_use.csv`: Notebook usage statistics.

## Notes

- Do not commit `pilots.json`, `users.csv`, or `otter_standalone_use.csv` (see `.gitignore`).
- GitHub Actions and local `act` runs currently authenticate with `GOOGLE_CREDENTIALS` as `cloudbank-nightly@cal-icor-hubs.iam.gserviceaccount.com`.
- That service account must be able to decrypt with the KMS key in `cal-icor-hubs` and read Firestore from `data8x-scratch` and `cb-1003-1696`.

## License

See repository for license