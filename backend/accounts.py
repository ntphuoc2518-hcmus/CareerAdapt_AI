"""Persistent accounts, password hashes, throttling and revocable sessions."""
from __future__ import annotations

import hashlib

from backend.filelock import exclusive
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from pwdlib import PasswordHash

DB_PATH = Path(os.getenv("CAREERADAPT_ACCOUNTS_DB", Path(__file__).resolve().parents[1] / "data" / "accounts.sqlite3"))
PASSWORD_HASH = PasswordHash.recommended()
_DUMMY_HASH = PASSWORD_HASH.hash(secrets.token_urlsafe(24))
SESSION_SECONDS = 8 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_FAILURES = 6
MAX_LOGIN_FAILURES_PER_IP = 30
MAX_SIGNUPS_PER_IP_PER_HOUR = 10
MAX_RESET_REQUESTS_PER_IP_PER_HOUR = 10
RESET_TOKEN_SECONDS = 30 * 60
SUPPORTED_LANGUAGES = ("vi", "en")
PROFILE_COLUMNS = {
    "phone": "TEXT NOT NULL DEFAULT ''",
    "preferred_language": "TEXT NOT NULL DEFAULT 'vi'",
    "last_login_at": "INTEGER",
    "password_changed_at": "INTEGER",
}

# Rule ids are shared with the browser checklist (frontend/js/password.js).
# Team decision (5.26): at least 8 characters, with at least one uppercase letter and one special character.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128  # an upper bound only, so a huge input cannot slow the hashing down


def _has_upper(password: str) -> bool:
    return any(char.isupper() for char in password)


def _has_special(password: str) -> bool:
    """Anything that is not a letter, a digit or a space: ! @ # $ % - _ . and so on."""
    return any(not char.isalnum() and not char.isspace() for char in password)


PASSWORD_RULES = (
    ("length", lambda p, ctx: PASSWORD_MIN_LENGTH <= len(p) <= PASSWORD_MAX_LENGTH),
    ("upper", lambda p, ctx: _has_upper(p)),
    ("special", lambda p, ctx: _has_special(p)),
)


def password_policy_failures(password: str, email: str = "", full_name: str = "") -> list[str]:
    """Return the ids of unmet rules; an empty list means the password is acceptable."""
    context = {"email": email or "", "full_name": full_name or ""}
    failures = [rule_id for rule_id, check in PASSWORD_RULES if not check(password, context)]
    if len(password.encode("utf-8")) > 1024:
        failures.append("max_size")
    return failures


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            DB_PATH.parent.chmod(0o700)
        except OSError:
            pass
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    if os.name != "nt":
        try:
            DB_PATH.chmod(0o600)
        except OSError:
            pass
    return conn


def initialize_database() -> None:
    # Server processes starting together take turns creating and upgrading the account tables.
    with exclusive(DB_PATH), closing(_connect()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'admin')),
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                csrf_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
            CREATE TABLE IF NOT EXISTS login_attempts (
                key_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS login_attempts_window ON login_attempts(key_hash, created_at);
            CREATE TABLE IF NOT EXISTS registration_attempts (
                key_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS registration_attempts_window ON registration_attempts(key_hash, created_at);
            CREATE TABLE IF NOT EXISTS password_resets (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                used_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS password_resets_user ON password_resets(user_id);
            CREATE TABLE IF NOT EXISTS account_avatars (
                user_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                image BLOB NOT NULL,
                updated_at INTEGER NOT NULL
            );
        """)
        # Additive migrations for databases created before profile settings existed. Several server processes
        # may start at once (CAREERADAPT_WORKERS): the write lock makes them take turns, and each re-reads the
        # columns inside it, so the second one finds the column already added instead of failing on it.
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(accounts)")}
            for column, ddl in PROFILE_COLUMNS.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE accounts ADD COLUMN {column} {ddl}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _attempt_keys(email: str, ip: str) -> tuple[str, str]:
    return _digest("email:" + email.casefold()), _digest("ip:" + (ip or "unknown"))


def begin_login_attempt(email: str, ip: str) -> bool:
    """Atomically throttle and count an attempt before expensive password verification."""
    now = int(time.time())
    keys = _attempt_keys(email, ip)
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM login_attempts WHERE created_at < ?", (now - LOGIN_WINDOW_SECONDS,))
            counts = [conn.execute("SELECT COUNT(*) FROM login_attempts WHERE key_hash = ? AND created_at >= ?", (key, now - LOGIN_WINDOW_SECONDS)).fetchone()[0] for key in keys]
            if counts[0] >= MAX_LOGIN_FAILURES or counts[1] >= MAX_LOGIN_FAILURES_PER_IP:
                conn.commit()
                return False
            conn.executemany("INSERT INTO login_attempts(key_hash, created_at) VALUES (?, ?)", [(key, now) for key in keys])
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise


def clear_login_failures(email: str, ip: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM login_attempts WHERE key_hash = ?", (_attempt_keys(email, ip)[0],))


def begin_registration_attempt(ip: str) -> bool:
    """Atomically cap account creation attempts by source address."""
    now = int(time.time())
    key = _digest("signup-ip:" + (ip or "unknown"))
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM registration_attempts WHERE created_at < ?", (now - 60 * 60,))
            count = conn.execute(
                "SELECT COUNT(*) FROM registration_attempts WHERE key_hash = ? AND created_at >= ?",
                (key, now - 60 * 60),
            ).fetchone()[0]
            if count >= MAX_SIGNUPS_PER_IP_PER_HOUR:
                conn.commit()
                return False
            conn.execute("INSERT INTO registration_attempts(key_hash, created_at) VALUES (?, ?)", (key, now))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise


def begin_reset_request(ip: str) -> bool:
    """Cap password-reset requests per source address (shares the attempts table)."""
    now = int(time.time())
    key = _digest("reset-ip:" + (ip or "unknown"))
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM registration_attempts WHERE key_hash = ? AND created_at >= ?",
                (key, now - 60 * 60),
            ).fetchone()[0]
            if count >= MAX_RESET_REQUESTS_PER_IP_PER_HOUR:
                conn.commit()
                return False
            conn.execute("INSERT INTO registration_attempts(key_hash, created_at) VALUES (?, ?)", (key, now))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise


def create_account(email: str, full_name: str, password: str, role: str = "student") -> dict[str, Any]:
    account_id = str(uuid.uuid4())
    password_hash = PASSWORD_HASH.hash(password)
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO accounts(id, email, full_name, role, password_hash, created_at, password_changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (account_id, email.strip().casefold(), full_name.strip(), role, password_hash, int(time.time()), int(time.time())),
        )
        return dict(conn.execute("SELECT id, email, full_name, role FROM accounts WHERE id = ?", (account_id,)).fetchone())


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM accounts WHERE email = ? COLLATE NOCASE", (email.strip(),)).fetchone()
    candidate = row["password_hash"] if row else _DUMMY_HASH
    try:
        valid_password = PASSWORD_HASH.verify(password, candidate)
    except Exception:
        valid_password = False
    if not row or not valid_password or row["disabled"]:
        return None
    with closing(_connect()) as conn:
        conn.execute("UPDATE accounts SET last_login_at = ? WHERE id = ?", (int(time.time()), row["id"]))
    return {"id": row["id"], "email": row["email"], "full_name": row["full_name"], "role": row["role"]}


def create_session(user_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = int(time.time())
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.execute(
            "INSERT INTO sessions(token_hash, user_id, csrf_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (_digest(token), user_id, _digest(csrf_token), now, now + SESSION_SECONDS),
        )
    return token, csrf_token


def get_session(token: str, csrf_token: str | None = None) -> dict[str, Any] | None:
    now = int(time.time())
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT a.id, a.email, a.full_name, a.role, a.disabled, s.csrf_hash "
            "FROM sessions s JOIN accounts a ON a.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (_digest(token), now),
        ).fetchone()
        if not row or row["disabled"]:
            return None
        if csrf_token is not None and not secrets.compare_digest(row["csrf_hash"], _digest(csrf_token)):
            return None
        return {"id": row["id"], "email": row["email"], "full_name": row["full_name"], "role": row["role"]}


def find_account_by_email(email: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT id, email, full_name, role FROM accounts WHERE email = ? COLLATE NOCASE", (email,)).fetchone()
    return dict(row) if row else None


def get_account_profile(user_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id, email, full_name, role, phone, preferred_language, created_at, last_login_at, password_changed_at "
            "FROM accounts WHERE id = ?", (user_id,),
        ).fetchone()
    return dict(row) if row else None


def set_avatar(user_id: str, image: bytes) -> int:
    """Store the processed picture (see backend/avatar.py). Returns its version, used to refresh browser caches."""
    now = int(time.time() * 1000)
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO account_avatars(user_id, image, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET image = excluded.image, updated_at = excluded.updated_at",
            (user_id, image, now),
        )
    return now


def get_avatar(user_id: str) -> tuple[bytes, int] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT image, updated_at FROM account_avatars WHERE user_id = ?", (user_id,)).fetchone()
    return (bytes(row["image"]), int(row["updated_at"])) if row else None


def avatar_version(user_id: str) -> int | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT updated_at FROM account_avatars WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["updated_at"]) if row else None


def delete_avatar(user_id: str) -> bool:
    with closing(_connect()) as conn:
        return conn.execute("DELETE FROM account_avatars WHERE user_id = ?", (user_id,)).rowcount > 0


def update_account_profile(user_id: str, full_name: str, phone: str, preferred_language: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE accounts SET full_name = ?, phone = ?, preferred_language = ? WHERE id = ?",
            (full_name.strip(), phone.strip(), preferred_language, user_id),
        )
    return get_account_profile(user_id)


def _set_password(conn: sqlite3.Connection, user_id: str, new_password: str) -> None:
    conn.execute(
        "UPDATE accounts SET password_hash = ?, password_changed_at = ? WHERE id = ?",
        (PASSWORD_HASH.hash(new_password), int(time.time()), user_id),
    )


def change_password(user_id: str, current_password: str, new_password: str, keep_session_token: str | None) -> bool:
    """Verify the current password, store the new one and sign out every other session."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT password_hash FROM accounts WHERE id = ?", (user_id,)).fetchone()
        try:
            valid = bool(row) and PASSWORD_HASH.verify(current_password, row["password_hash"])
        except Exception:
            valid = False
        if not valid:
            return False
        _set_password(conn, user_id, new_password)
        conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?",
            (user_id, _digest(keep_session_token or "")),
        )
    return True


def create_password_reset(email: str) -> tuple[str, dict[str, Any]] | None:
    """Issue a single-use reset token; returns None for unknown or disabled accounts."""
    now = int(time.time())
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id, email, full_name, preferred_language, disabled FROM accounts WHERE email = ? COLLATE NOCASE",
            (email.strip(),),
        ).fetchone()
        if not row or row["disabled"]:
            return None
        token = secrets.token_urlsafe(32)
        # Only the newest link works; older unused links are invalidated.
        conn.execute("DELETE FROM password_resets WHERE user_id = ? OR expires_at <= ?", (row["id"], now))
        conn.execute(
            "INSERT INTO password_resets(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_digest(token), row["id"], now, now + RESET_TOKEN_SECONDS),
        )
    return token, dict(row)


def account_for_reset_token(token: str) -> dict[str, Any] | None:
    """Email and name behind a live reset token, so the new password can be checked against them. Changes nothing."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT a.email, a.full_name FROM password_resets r JOIN accounts a ON a.id = r.user_id "
            "WHERE r.token_hash = ? AND r.used_at IS NULL AND r.expires_at > ?", (_digest(token), int(time.time())),
        ).fetchone()
    return dict(row) if row else None


def reset_password(token: str, new_password: str) -> bool:
    """Consume a reset token, set the password and revoke all sessions for that account."""
    now = int(time.time())
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT user_id FROM password_resets WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
                (_digest(token), now),
            ).fetchone()
            if not row:
                conn.commit()
                return False
            conn.execute("UPDATE password_resets SET used_at = ? WHERE token_hash = ?", (now, _digest(token)))
            _set_password(conn, row["user_id"], new_password)
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["user_id"],))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise


def revoke_session(token: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))


initialize_database()
