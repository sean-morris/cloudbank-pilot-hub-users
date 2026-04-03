# ...existing code...

import threading
import users
import otter_standalone_use
import subprocess

# Decrypt pilot tokens
open('pilots.json', 'w').write(
    subprocess.run(['sops', '--decrypt', 'enc-pilots.json'], capture_output=True, text=True).stdout
)

errors = []

def run_thread(fn, *args):
    try:
        fn(*args)
    except Exception as e:
        errors.append(e)
        raise

# Run user statistics and notebook usage aggregation in parallel
thread1 = threading.Thread(target=run_thread, args=(users.main, True, None))
thread2 = threading.Thread(target=run_thread, args=(otter_standalone_use.main,))

thread1.start()
thread2.start()

thread1.join()
thread2.join()

if errors:
    raise Exception(f"Thread errors: {errors}")

print("Done.")