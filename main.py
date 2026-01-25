#!/usr/bin/env python3
"""
main.py

Orchestrates the collection of user statistics and Otter Standalone notebook usage.

- Decrypts pilot tokens from 'enc-pilots.json' to 'pilots.json' using sops.
- Runs user statistics collection (users.py) and notebook usage aggregation (otter_standalone_use.py) in parallel threads.
- Waits for both tasks to complete, then prints "Done."

Usage:
    python main.py ; or  
    ./main.py

Outputs:
    - pilots.json: Decrypted pilot tokens (not committed to repo)
    - users.csv: User statistics per pilot and term
    - otter_standalone_use.csv: Weekly notebook usage statistics

Requires:
    - enc-pilots.json: Encrypted pilot tokens
    - sops: For decryption
    - pilots.json: Generated at runtime
"""

import threading
import subprocess

# Decrypt pilot tokens
open('pilots.json', 'w').write(
    subprocess.run(['sops', '--decrypt', 'enc-pilots.json'], capture_output=True, text=True).stdout
)

# Now import users and otter_standalone_use after pilots.json has been created
import users
import otter_standalone_use

# Run user statistics and notebook usage aggregation in parallel
thread1 = threading.Thread(target=users.main, args=(True, None))
thread2 = threading.Thread(target=otter_standalone_use.main)

thread1.start()
thread2.start()

thread1.join()
thread2.join()

print("Done.")
