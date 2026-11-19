"""Start the app on port 8765 with throwaway data, for manual and browser testing.

Nothing touches data/accounts.sqlite3, data/careeradapt.sqlite3 or the learner file: all state
goes to a new temporary folder. Demo tools and fault injection are on.

Usage (from the CareerAdapt_AI folder):  python scripts/dev_server_isolated.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
folder = Path(tempfile.mkdtemp(prefix="careeradapt-dev-"))
os.environ.update({
    "CAREERADAPT_ACCOUNTS_DB": str(folder / "accounts.sqlite3"),
    "CAREERADAPT_DB": str(folder / "careeradapt.sqlite3"),
    "CAREERADAPT_STATE_PATH": str(folder / "no_legacy.json"),
    "CAREERADAPT_QUESTION_BANK_OVERRIDES_PATH": str(folder / "bank_overrides.json"),
    "CAREERADAPT_ENABLE_DEMO_TOOLS": "true",
    "CAREERADAPT_ENABLE_FAULT_INJECTION": "true",
    "CAREERADAPT_AUTO_LINK_CHECK": "false",
})

import uvicorn  # noqa: E402

if __name__ == "__main__":
    print(f"Throwaway data folder: {folder}")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, log_level="warning")
