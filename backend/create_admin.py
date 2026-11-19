"""Create an administrator account interactively without putting secrets in shell history."""
from __future__ import annotations

import getpass
import re
import sqlite3

from backend.accounts import create_account, password_policy_failures


def main() -> None:
    email = input("Admin email: ").strip().casefold()
    name = input("Full name: ").strip()
    password = getpass.getpass("Password (8+ characters, an uppercase letter and a special character): ")
    confirm = getpass.getpass("Confirm password: ")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("A valid email address is required.")
    if len(name) < 2 or len(name) > 100:
        raise SystemExit("Name must contain 2 to 100 characters.")
    if password_policy_failures(password, email, name):
        raise SystemExit("Password needs at least 8 characters, one uppercase letter and one special character.")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    try:
        create_account(email, name, password, role="admin")
    except sqlite3.IntegrityError:
        raise SystemExit("An account with that email could not be created.")
    print(f"Administrator account created for {email}.")


if __name__ == "__main__":
    main()
