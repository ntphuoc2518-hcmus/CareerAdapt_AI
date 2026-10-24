"""DB integration test. Always targets careeradapt_demo and rolls back its fixtures."""
import os
os.environ["DB_NAME"] = "careeradapt_demo"  # set before importing .env-loading modules

import uuid
import unittest
try:
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv()
    from data_access import get_owned_submission, list_owned_submissions, update_owned_submission_status
except ImportError as exc:
    psycopg2 = None
    IMPORT_ERROR = exc

@unittest.skipIf(psycopg2 is None, "psycopg2/python-dotenv are not installed")
class DataAccessIntegrationTests(unittest.TestCase):
    def test_cross_user_is_hidden_and_audited(self):
        conn = None
        try:
            conn = psycopg2.connect(
                dbname="careeradapt_demo", user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"], host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"))
            conn.autocommit = False
            cur = conn.cursor()
            cur.execute("SELECT task_version_id FROM task_versions LIMIT 1")
            task = cur.fetchone()
            if not task:
                self.skipTest("careeradapt_demo has no task_versions seed; run migrations/seeds first")
            user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
            submission_id = str(uuid.uuid4())
            cur.execute("INSERT INTO users(user_id,email,password_hash,role) VALUES (%s,%s,%s,'learner'),(%s,%s,%s,'learner')",
                        (user_a, f"{user_a}@test.local", "TEST-NO-LOGIN", user_b, f"{user_b}@test.local", "TEST-NO-LOGIN"))
            idempotency_key = f"test-{uuid.uuid4()}"
            cur.execute("INSERT INTO submissions(submission_id,user_id,task_version_id,mode,idempotency_key,submitted_text) VALUES (%s,%s,%s,'PRACTICE',%s,%s)",
                        (submission_id, user_b, task[0], idempotency_key, "private fixture"))
            # Verify duplicate idempotency key is rejected; isolate expected error with savepoint.
            cur.execute("SAVEPOINT duplicate_idempotency")
            try:
                cur.execute("INSERT INTO submissions(user_id,task_version_id,mode,idempotency_key,submitted_text) VALUES (%s,%s,'PRACTICE',%s,%s)",
                            (user_b, task[0], idempotency_key, "duplicate fixture"))
                self.fail("duplicate idempotency_key unexpectedly accepted")
            except psycopg2.IntegrityError:
                cur.execute("ROLLBACK TO SAVEPOINT duplicate_idempotency")
            cur.execute("RELEASE SAVEPOINT duplicate_idempotency")
            # Keep fixture and audit writes in this uncommitted transaction; rollback below.
            self.assertIsNone(get_owned_submission(conn, user_a, submission_id))
            self.assertEqual(list_owned_submissions(conn, user_a), [])
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM audit_logs WHERE actor_user_id=%s AND target_id=%s AND outcome='DENIED'", (user_a, submission_id))
            self.assertGreaterEqual(cur.fetchone()[0], 1)
            self.assertFalse(update_owned_submission_status(conn, user_a, submission_id, "PROCESSING"))
        finally:
            if conn is not None:
                conn.rollback()
                conn.close()

if __name__ == "__main__": unittest.main(verbosity=2)
