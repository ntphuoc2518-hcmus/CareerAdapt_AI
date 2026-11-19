"""Audit 2026-11-18: every request that executes a learner's or contributor's code takes their one code-run slot.

Before the fix, "Kiểm tra" on a practice exercise and an expert's automatic check ran code in the sandbox without
the slot that "Chạy thử" takes. The per-learner request lock (5.34) already serialised one account's requests, so
this is defence in depth: code execution no longer depends on that lock alone, which some routes skip.
"""
import pytest

from backend import exam_service
from backend.store import store
from v5_helpers import ADMIN, STUDENT, STUDENT_ID, client

A = "/api/v1"
SQL_EXERCISE = "PR-SQL-01"
GOOD_SQL = "SELECT status, COUNT(*) AS n FROM orders_raw GROUP BY status ORDER BY n DESC;"
EXAM_PAYLOAD = {
    "topic": "Đếm đơn hoàn thành", "answer_type": "sql", "workspace": "sql", "minutes": 6, "max_chars": 2000, "placeholder": "SELECT ...",
    "prompt": "Từ bảng orders_raw, viết truy vấn đếm số dòng có status = 'completed'. Kết quả là một ô duy nhất.",
    "cases": [
        {"id": "runs", "type": "sql_runs", "points": 10, "description": "Câu truy vấn chạy được và trả về dữ liệu"},
        {"id": "result", "type": "sql_result", "points": 90, "expected_sql": "SELECT COUNT(*) FROM orders_raw WHERE status = 'completed'", "description": "Đếm đúng số dòng hoàn thành"},
    ],
    "reference_answers": {"*": "SELECT COUNT(*) FROM orders_raw WHERE status = 'completed';"},
}


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    exam_service._running.clear()
    exam_service._last_run.clear()
    yield
    exam_service._running.clear()
    exam_service._last_run.clear()
    store.reset()


def sql_roadmap():
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {code: {"level": level} for code, level in {"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2}.items()}
    assert client.post("/roadmaps", headers=STUDENT).status_code in (200, 201)


def practice_check(answer=GOOD_SQL):
    return client.post(f"/me/practice/{SQL_EXERCISE}/check", json={"answer": answer}, headers=STUDENT)


def test_a_practice_check_waits_for_the_run_already_going():
    sql_roadmap()
    exam_service._running.add(str(STUDENT_ID))  # a run started from another tab is still going
    response = practice_check()
    assert response.status_code == 429
    assert store.db.one("SELECT COUNT(*) AS n FROM practice_attempts")["n"] == 0
    exam_service._running.discard(str(STUDENT_ID))
    assert practice_check().json()["score"] == 100


def test_a_practice_check_releases_the_slot_and_needs_no_pause_between_checks():
    sql_roadmap()
    assert practice_check().status_code == 200
    assert str(STUDENT_ID) not in exam_service._running
    # Checks one after another are fine: the pause applies to "Chạy thử", a graded check is bounded by its run.
    assert practice_check("SELECT 1;").status_code == 200
    assert str(STUDENT_ID) not in exam_service._running


def test_a_written_practice_answer_runs_no_code_and_needs_no_slot():
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {code: {"level": level} for code, level in {"SQL": 2, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 0}.items()}
    assert client.post("/roadmaps", headers=STUDENT).status_code in (200, 201)
    exam_service._running.add(str(STUDENT_ID))
    response = client.post("/me/practice/PR-COMM-01/check", json={"answer": "Trong dữ liệu có 1 đơn bị hủy."}, headers=STUDENT)
    assert response.status_code == 200, response.text


def test_the_run_button_keeps_its_pause_and_shares_the_slot():
    sql_roadmap()
    first = client.post(f"/me/practice/{SQL_EXERCISE}/run", json={"code": GOOD_SQL}, headers=STUDENT)
    assert first.status_code == 200, first.text
    assert client.post(f"/me/practice/{SQL_EXERCISE}/run", json={"code": GOOD_SQL}, headers=STUDENT).status_code == 429
    exam_service._running.add(str(STUDENT_ID))
    exam_service._last_run.clear()
    assert client.post(f"/me/practice/{SQL_EXERCISE}/run", json={"code": GOOD_SQL}, headers=STUDENT).status_code == 429


def test_an_expert_check_of_a_code_question_takes_the_slot():
    assert client.post(f"{A}/admin/contributors", json={"user_id": str(STUDENT_ID)}, headers=ADMIN).status_code == 201
    item = client.post(f"{A}/contributions", json={"bank": "EXAM", "skill_code": "SQL", "level": 1, "payload": EXAM_PAYLOAD}, headers=STUDENT).json()
    exam_service._running.add(str(STUDENT_ID))
    assert client.post(f"{A}/contributions/{item['contribution_id']}/check", headers=STUDENT).status_code == 429
    assert client.post(f"{A}/contributions/{item['contribution_id']}/submit", headers=STUDENT).status_code == 429
    exam_service._running.discard(str(STUDENT_ID))
    checked = client.post(f"{A}/contributions/{item['contribution_id']}/check", headers=STUDENT)
    assert checked.status_code == 200 and checked.json()["validation"]["ok"] is True
    assert str(STUDENT_ID) not in exam_service._running
