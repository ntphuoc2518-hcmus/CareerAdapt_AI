"""Check the seed data files (skills, tasks, activities, job profiles) for consistency.

Usage (from the CareerAdapt_AI folder):  python scripts/verify_seed.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
from seed import verify_seed_integrity

if __name__ == "__main__":
    verify_seed_integrity()
