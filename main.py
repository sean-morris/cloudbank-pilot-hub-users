#!/usr/bin/env python3

import sys
import threading
import users
import otter_standalone_use
import subprocess


def format_final_message(user_summary, otter_summary, failures):
    otter_part = (
        "otter_standalone "
        f"records={otter_summary['records']} "
        f"notebooks={otter_summary['total_notebooks']} "
        f"projects={otter_summary['project_count']}"
    )
    users_part = (
        "users "
        f"successful={user_summary['successful_pilots']} "
        f"failed={user_summary['failed_pilots']} "
        f"total={user_summary['total_pilots']}"
    )
    detail_parts = [otter_part, users_part]
    if user_summary["failed_pilots"]:
        detail_parts.append(f"user_failures={'; '.join(user_summary['failures'])}")
    if failures:
        detail_parts.append(f"errors={'; '.join(failures)}")
    return " | ".join(detail_parts)


def main():
    # Decrypt pilot tokens
    open('pilots.json', 'w').write(
        subprocess.run(['sops', '--decrypt', 'enc-pilots.json'], capture_output=True, text=True).stdout
    )

    errors = []
    results = {}

    def run_thread(key, fn, *args):
        try:
            results[key] = fn(*args)
        except Exception as e:
            errors.append(e)
            results[key] = None

    # Run user statistics and notebook usage aggregation in parallel
    thread1 = threading.Thread(target=run_thread, args=("users", users.main, True, None))
    thread2 = threading.Thread(target=run_thread, args=("otter", otter_standalone_use.main))

    thread1.start()
    thread2.start()

    thread1.join()
    thread2.join()

    if results.get("users") is None or results.get("otter") is None:
        raise Exception(f"Thread errors: {errors}")

    return {
        "users": results["users"],
        "otter": results["otter"],
        "errors": [str(error) for error in errors],
    }


if __name__ == "__main__":
    try:
        summary = main()
        has_failures = bool(summary["errors"] or summary["users"]["failed_pilots"])
        status = "Finished with failure" if has_failures else "Finished successfully"
        print(f"{status}: {format_final_message(summary['users'], summary['otter'], summary['errors'])}")
        if has_failures:
            sys.exit(1)
    except Exception as exc:
        print(f"Finished with failure: {exc}")
        sys.exit(1)
