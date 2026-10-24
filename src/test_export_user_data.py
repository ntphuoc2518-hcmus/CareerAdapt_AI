"""Unit test for export coverage and owner-scoped SQL without touching a database."""
import unittest
import sys
import types
from unittest.mock import patch
# The export test uses a fake connection, so psycopg2 is not required here.
if "psycopg2" not in sys.modules:
    fake_pg = types.ModuleType("psycopg2")
    fake_extras = types.ModuleType("psycopg2.extras")
    fake_extras.RealDictCursor = object
    fake_pg.extras = fake_extras
    sys.modules["psycopg2"] = fake_pg
    sys.modules["psycopg2.extras"] = fake_extras
import user_data_lifecycle as lifecycle

class FakeCursor:
    def __init__(self):
        self.queries = []
        self.fetchone_calls = 0
    def execute(self, query, params=None):
        self.queries.append((" ".join(query.split()), params))
    def fetchone(self):
        self.fetchone_calls += 1
        return {"user_id": "test-user", "email": "owner@test.local"}
    def fetchall(self):
        return []
    def close(self):
        pass

class FakeConnection:
    def __init__(self): self.cur = FakeCursor()
    def cursor(self, cursor_factory=None): return self.cur
    def close(self): pass

class ExportTests(unittest.TestCase):
    def test_exports_all_personal_data_groups_and_scopes_queries(self):
        conn = FakeConnection()
        with patch.object(lifecycle, "get_db_connection", return_value=conn):
            result = lifecycle.export_user_data("test-user")
        expected = {"account", "profile", "submissions", "assessments", "criterion_scores",
                    "roadmaps", "learning_activities", "progress_records", "checklist_items", "reminders"}
        self.assertTrue(expected.issubset(result.keys()))
        self.assertEqual(len(conn.cur.queries), 10)
        for query, params in conn.cur.queries:
            self.assertEqual(params, ("test-user",))
            self.assertIn("where", query.lower())
        sql = "\n".join(q for q, _ in conn.cur.queries).lower()
        for table in ("profiles", "submissions", "assessments", "criterion_scores", "roadmap_versions",
                      "learning_activities", "progress_records", "checklist_items", "reminders"):
            self.assertIn(table, sql)

if __name__ == "__main__": unittest.main(verbosity=2)
