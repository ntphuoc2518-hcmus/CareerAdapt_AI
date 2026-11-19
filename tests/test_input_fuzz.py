"""Audit 2026-11-04: wrong-typed bodies on every learner write endpoint must give a 4xx, never a 500."""
from fastapi.testclient import TestClient

from backend.main import app
from backend.store import store
from v4_helpers import STUDENT, STUDENT_ID
from v5_helpers import complete_process

safe = TestClient(app, raise_server_exceptions=False)
BODIES = [None, [], [1, 2], 5, "x", {"x": None}, {"value": {"a": [1]}}, {"responses": [1]}, {"responses": {"a": {"b": 1}}},
          {"status": 5, "progress_percent": "x"}, {"action": "SET_CYCLE", "cycle_days": "abc"}, {"days": 10**12}, {"text": ["a"]},
          {"skills": [{"skill_code": None, "level": "x"}]}, {"content": {"a": 1}}, {"weekly_hours": "a", "timeline_weeks": None},
          {"blueprint_id": ["a"]}, {"confirm": "yes", "actual_hours": "x"}, {"jd_id": 5, "decisions": "x"}, {"type": "paste", "detail": ["x"]}]


def test_wrong_typed_bodies_never_crash_the_server():
    store.reset()
    complete_process()
    micro = store.db.query("SELECT micro_id FROM micro_assessments LIMIT 1")
    paths = [
        ("post", "/api/v1/career-process/runs"), ("put", "/api/v1/career-process/exam/responses/Q1"), ("post", "/api/v1/career-process/exam/events"),
        ("post", "/api/v1/career-process/roadmap"), ("post", "/api/v1/career-process/reset"),
        ("post", "/me/skill-report/confirm"), ("patch", "/me/skill-report/skills/SQL"), ("post", "/me/skill-report/analyze"), ("post", "/me/target-jd"),
        ("patch", "/activities/ACT_SQL_01/progress"), ("patch", "/activities/ACT_SQL_01/schedule"), ("post", "/activities/ACT_SQL_01/knowledge-check"),
        ("put", "/me/reminder-preferences"), ("post", "/api/v1/tests/attempts"), ("post", "/api/v1/assistant/conversations"),
        ("post", "/submissions"), ("put", "/micro-tests/NOPE/draft"), ("post", "/micro-tests/NOPE/submissions"),
    ] + ([("put", f"/micro-tests/{micro[0]['micro_id']}/draft"), ("post", f"/micro-tests/{micro[0]['micro_id']}/submissions")] if micro else [])
    crashes = []
    for method, path in paths:
        for body in BODIES:
            response = getattr(safe, method)(path, json=body, headers=STUDENT)
            if response.status_code >= 500:
                crashes.append((method, path, body, response.status_code))
    assert not crashes, crashes
