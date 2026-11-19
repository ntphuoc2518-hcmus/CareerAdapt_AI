"""Pytest configuration: Add project root to sys.path and isolate the accounts database."""
import os
import sys
import tempfile

# Tests create accounts; keep them out of data/accounts.sqlite3. Must be set before backend imports.
os.environ.setdefault("CAREERADAPT_ACCOUNTS_DB", os.path.join(tempfile.mkdtemp(prefix="careeradapt-tests-"), "accounts.sqlite3"))

# V4 tests exercise the grading engine directly; learners reach it only through the Career Adapt process.
os.environ.setdefault("CAREERADAPT_LEGACY_ASSESSMENT_API", "true")

# Ensure CareerAdapt_AI root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# Shared benchmark submissions (tests/sample_submissions.py)
TESTS_DIR = os.path.dirname(__file__)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
