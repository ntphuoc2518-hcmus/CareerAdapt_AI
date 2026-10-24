"""Run the Step 12–18 test suite with the database target forced to careeradapt_demo."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "src/test_security.py",
    "src/test_file_storage.py",
    "src/test_data_access.py",
    "src/test_export_user_data.py",
    "src/test_delete_account.py",
    "src/test_cleanup_job.py",
]

def main():
    env = os.environ.copy()
    env["DB_NAME"] = "careeradapt_demo"
    failed = []
    for test in TESTS:
        print(f"\n===== RUN {test} (DB_NAME=careeradapt_demo) =====", flush=True)
        result = subprocess.run([sys.executable, test], cwd=ROOT, env=env)
        if result.returncode != 0:
            failed.append(test)
    if failed:
        print("\nFAILED:", ", ".join(failed))
        return 1
    print("\nALL AVAILABLE STEP 12–18 TEST SCRIPTS PASSED")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
