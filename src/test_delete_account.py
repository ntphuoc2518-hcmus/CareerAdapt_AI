"""Test account deletion; runs only against the careeradapt_demo database."""

import os
import sys
import uuid

# Force the demo DB before importing lifecycle code (which loads .env).
os.environ["DB_NAME"] = "careeradapt_demo"

from psycopg2 import sql
from user_data_lifecycle import get_db_connection, delete_user_account_safe
from file_storage_service import validate_and_save_file, delete_physical_file, STORAGE_ROOT

TASK_VERSION_ID = "20000000-0000-0000-0000-000000000001"  # DA01A from seed 006


def one(cur):
    row = cur.fetchone()
    assert row is not None, "Query returned no rows"
    return row


def absolute_path(stored_path):
    return os.path.join(STORAGE_ROOT, os.path.basename(stored_path))


def create_test_user(cur, prefix):
    """Create one fake user, profile, submission, and physical file."""
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.local"
    cur.execute(
        """INSERT INTO users (email, password_hash, role)
           VALUES (%s, %s, 'learner') RETURNING user_id""",
        (email, "DISABLED-NO-LOGIN"),
    )
    user_id = str(one(cur)[0])
    cur.execute(
        "INSERT INTO profiles (user_id, display_name) VALUES (%s, %s)",
        (user_id, f"Test {prefix}"),
    )
    cur.execute(
        """INSERT INTO submissions
           (user_id, task_version_id, mode, submitted_text, idempotency_key)
           VALUES (%s, %s, 'PRACTICE', %s, %s) RETURNING submission_id""",
        (user_id, TASK_VERSION_ID, "fake test submission", uuid.uuid4().hex),
    )
    submission_id = str(one(cur)[0])

    ok, path, file_type, size, sha, error = validate_and_save_file(
        "test.sql", b"SELECT 1;", submission_id
    )
    assert ok and path is not None, error
    cur.execute(
        """INSERT INTO submission_files
           (submission_id, stored_path, original_name, file_type, size_bytes, sha256)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (submission_id, path, "test.sql", file_type, size, sha),
    )
    return user_id, submission_id, path


def run_tests():
    print("--- TEST ACCOUNT DELETION (careeradapt_demo only) ---")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_database()")
    db_name = one(cur)[0]
    if db_name != "careeradapt_demo":
        cur.close()
        conn.close()
        print(f"STOP: connected to '{db_name}', expected 'careeradapt_demo'.")
        sys.exit(1)

    created_user_ids = []
    created_paths = []
    try:
        a_id, a_sub, a_path = create_test_user(cur, "test_a")
        created_user_ids.append(a_id)
        created_paths.append(a_path)
        b_id, b_sub, b_path = create_test_user(cur, "test_b")
        created_user_ids.append(b_id)
        created_paths.append(b_path)

        cur.execute(
            """INSERT INTO audit_logs (actor_user_id, action, target_type, outcome)
               VALUES (%s, 'TEST_DELETE_ACCOUNT', 'user', 'ALLOWED')
               RETURNING audit_id""",
            (a_id,),
        )
        audit_id = str(one(cur)[0])
        conn.commit()
        assert os.path.exists(absolute_path(a_path))
        assert os.path.exists(absolute_path(b_path))

        # 1. Account A and its physical file are removed.
        result = delete_user_account_safe(a_id)
        assert result["account_deleted"] is True, result
        assert result["files_deleted"] == 1 and result["files_failed"] == [], result
        assert not os.path.exists(absolute_path(a_path)), "A's physical file still exists"
        print("OK 1: Account A and its physical file deleted.")

        # 2. No rows for A remain in tables with a user_id column.
        cur.execute(
            """SELECT table_name FROM information_schema.columns
               WHERE table_schema = 'public' AND column_name = 'user_id'
               GROUP BY table_name ORDER BY table_name"""
        )
        tables = [row[0] for row in cur.fetchall()]
        for table_name in tables:
            cur.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE user_id = %s").format(
                    sql.Identifier(table_name)
                ),
                (a_id,),
            )
            assert one(cur)[0] == 0, f"Table {table_name} still has rows for A"
        cur.execute("SELECT count(*) FROM submission_files WHERE submission_id = %s", (a_sub,))
        assert one(cur)[0] == 0, "A's submission_files row remains"
        print(f"OK 2: No A data remains in {len(tables)} user_id tables or submission_files.")

        # 3. Audit record remains, but its FK is nulled by ON DELETE SET NULL.
        cur.execute("SELECT actor_user_id FROM audit_logs WHERE audit_id = %s", (audit_id,))
        audit_row = cur.fetchone()
        assert audit_row is not None and audit_row[0] is None, "Audit row should remain with NULL actor"
        print("OK 3: Audit record retained; actor_user_id is NULL.")

        # 4. User B remains untouched until explicitly deleted below.
        cur.execute("SELECT count(*) FROM users WHERE user_id = %s", (b_id,))
        assert one(cur)[0] == 1, "B was unexpectedly deleted"
        cur.execute("SELECT count(*) FROM submission_files WHERE submission_id = %s", (b_sub,))
        assert one(cur)[0] == 1, "B's submission_files row was unexpectedly deleted"
        assert os.path.exists(absolute_path(b_path)), "B's physical file was unexpectedly deleted"
        print("OK 4: Account B and its file remain untouched.")

        # 5. A missing physical file counts as already deleted, not as failure.
        os.remove(absolute_path(b_path))
        result = delete_user_account_safe(b_id)
        assert result["account_deleted"] is True and result["files_failed"] == [], result
        print("OK 5: Missing physical file is handled as success.")

        # 6. Deleting an unknown user returns a false result and no file errors.
        result = delete_user_account_safe(str(uuid.uuid4()))
        assert result == {
            "account_deleted": False,
            "files_deleted": 0,
            "files_failed": [],
        }, result
        print("OK 6: Unknown user returns account_deleted=False.")
        print("ALL 6 ACCOUNT-DELETION TESTS PASSED.")
    finally:
        # Cleanup is limited to IDs and file paths created by this test.
        for user_id in created_user_ids:
            try:
                delete_user_account_safe(user_id)
            except Exception as exc:
                print(f"Cleanup warning for test user {user_id}: {exc}")
        for path in created_paths:
            delete_physical_file(path)
        cur.close()
        conn.close()


if __name__ == "__main__":
    run_tests()
