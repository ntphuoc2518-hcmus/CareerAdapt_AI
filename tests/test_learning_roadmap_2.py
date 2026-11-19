"""Learning Roadmap 2.0: study timer, lesson states, spaced review, practice and the final assessment."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend import final_assessment, learning_journey, practice
from backend.clock import set_clock
from backend.lesson_checks import RETRY_WAIT_HOURS
from backend.store import store
from v5_helpers import P, STUDENT, STUDENT_2, STUDENT_ID, client, complete_process, good_answer

START = datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc)  # 10:00 in Asia/Ho_Chi_Minh
LESSON = "ACT_SQL_01"


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    fake = Clock()
    set_clock(fake)
    yield fake
    set_clock(None)


def roadmap_for(levels, headers=STUDENT, user=STUDENT_ID):
    profile = store.get_or_create_profile(user)
    profile["assessed_skills"] = {code: {"level": level} for code, level in levels.items()}
    assert client.post("/roadmaps", headers=headers).status_code in (200, 201)


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    set_clock(None)
    yield
    set_clock(None)


def sql_only():
    """SQL one level short; every other skill at its default target. The roadmap holds one SQL lesson."""
    roadmap_for({"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2})


def start(activity=LESSON, days=3, switch=False, headers=STUDENT):
    return client.post("/me/study/start", json={"activity_id": activity, "review_cycle_days": days, "switch": switch}, headers=headers)


def act(session_id, action, headers=STUDENT):
    response = client.post(f"/me/study/{session_id}", json={"action": action}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["session"]


def study(session_id, clock, minutes):
    """Study with the page open: it reports a heartbeat every minute."""
    for _ in range(minutes):
        clock.advance(minutes=1)
        act(session_id, "heartbeat")


def lesson(activity=LESSON, headers=STUDENT):
    return client.get(f"/me/journey/lessons/{activity}", headers=headers).json()


def answers_of(micro_id, correct=True):
    items = json.loads(store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (micro_id,))["payload"])["items"]
    if correct:
        return {item["item_id"]: item["answer"] for item in items}
    wrong = {"single": "zz", "multiple": ["zz"], "numeric": -987654}
    return {item["item_id"]: list(reversed(item["answer"])) if item["type"] == "ordering" else wrong[item["type"]] for item in items}


def take_check(activity=LESSON, correct=True, headers=STUDENT, key="k"):
    check = client.post(f"/activities/{activity}/knowledge-check", json={"confirm": True}, headers=headers).json()["lesson_check"]
    response = client.post(f"/micro-tests/{check['micro_id']}/submissions", json={"responses": answers_of(check["micro_id"], correct), "idempotency_key": key}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def level(skill="SQL", user=STUDENT_ID):
    return (store.get_or_create_profile(user)["assessed_skills"].get(skill) or {}).get("level")


# ---------------------------------------------------------------- A. Timer
def test_the_first_start_needs_a_review_cycle_and_then_locks_it(clock):
    sql_only()
    assert client.post("/me/study/start", json={"activity_id": LESSON}, headers=STUDENT).status_code == 422
    assert start(days=0).status_code == 422
    first = start(days=3)
    assert first.status_code == 200 and first.json()["review_cycle_days"] == 3
    session = first.json()["session"]
    act(session["session_id"], "end")
    # A later start keeps the locked cycle whatever it sends.
    assert start(days=14).json()["review_cycle_days"] == 3
    assert client.patch(f"/activities/{LESSON}/schedule", json={"action": "SET_CYCLE", "cycle_days": 7}, headers=STUDENT).status_code == 409


def test_start_pause_resume_end_count_only_running_time(clock):
    sql_only()
    session = start().json()["session"]
    assert session["status"] == "RUNNING" and session["elapsed_seconds"] == 0
    clock.advance(seconds=50)
    act(session["session_id"], "heartbeat")
    clock.advance(seconds=40)
    assert act(session["session_id"], "pause")["elapsed_seconds"] == 90
    clock.advance(hours=2)  # paused time never counts
    assert client.get("/me/study/current", headers=STUDENT).json()["session"]["elapsed_seconds"] == 90
    act(session["session_id"], "resume")
    clock.advance(seconds=30)
    ended = act(session["session_id"], "end")
    assert ended["status"] == "ENDED" and ended["elapsed_seconds"] == 120
    assert lesson()["state"]["study_seconds"] == 120


def test_a_refresh_or_a_second_tab_joins_the_same_session_and_never_doubles_time(clock):
    sql_only()
    first = start().json()["session"]
    clock.advance(seconds=30)
    again = start().json()["session"]  # the second tab
    assert again["session_id"] == first["session_id"]
    for _ in range(5):  # both tabs report heartbeats
        clock.advance(seconds=10)
        act(first["session_id"], "heartbeat")
        act(first["session_id"], "heartbeat")
    assert client.get("/me/study/current", headers=STUDENT).json()["session"]["elapsed_seconds"] == 80
    assert store.db.one("SELECT COUNT(*) AS n FROM study_sessions")["n"] == 1


def test_a_lost_connection_pauses_at_the_last_heartbeat_and_can_be_resumed(clock):
    sql_only()
    session = start().json()["session"]
    clock.advance(seconds=60)
    act(session["session_id"], "heartbeat")
    clock.advance(hours=3)  # laptop asleep, tab closed or offline
    current = client.get("/me/study/current", headers=STUDENT).json()["session"]
    assert current["status"] == "PAUSED" and current["pause_reason"] == "INTERRUPTED" and current["elapsed_seconds"] == 60
    resumed = act(session["session_id"], "resume")
    assert resumed["status"] == "RUNNING" and resumed["elapsed_seconds"] == 60


def test_one_running_timer_per_account(clock):
    roadmap_for({"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 0, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    first = start("ACT_SQL_01").json()["session"]
    other = start("ACT_PY_01")
    assert other.status_code == 409 and "đang bấm giờ" in other.json()["error"]["message"]
    clock.advance(seconds=20)
    switched = start("ACT_PY_01", switch=True)
    assert switched.status_code == 200
    assert learning_journey._session(first["session_id"])["status"] == "PAUSED"
    assert store.db.one("SELECT COUNT(*) AS n FROM study_sessions WHERE status = 'RUNNING'")["n"] == 1


def test_sessions_belong_to_their_owner_and_survive_a_new_login(clock):
    sql_only()
    session = start().json()["session"]
    clock.advance(seconds=45)
    act(session["session_id"], "end")
    assert client.post(f"/me/study/{session['session_id']}", json={"action": "pause"}, headers=STUDENT_2).status_code == 404
    # Nothing is kept in the browser: a fresh request (new login) reads the same history.
    history = lesson()["sessions"]
    assert len(history) == 1 and history[0]["elapsed_seconds"] == 45


def test_a_segment_never_counts_more_than_the_limit(clock):
    sql_only()
    session = start().json()["session"]
    for _ in range(60):  # five hours of heartbeats
        clock.advance(minutes=5)
        act(session["session_id"], "heartbeat")
    current = client.get("/me/study/current", headers=STUDENT).json()["session"]
    assert current["status"] == "PAUSED" and current["pause_reason"] == "LIMIT" and current["elapsed_seconds"] == learning_journey.MAX_SEGMENT_SECONDS


# ---------------------------------------------------------------- B. Lesson progress
def test_lesson_states_move_with_study_and_the_completion_check_only(clock):
    sql_only()
    assert lesson()["state"]["learning_state"] == "NOT_STARTED"
    session = start().json()["session"]
    assert lesson()["state"]["learning_state"] == "STUDYING"
    act(session["session_id"], "pause")
    assert lesson()["state"]["learning_state"] == "PAUSED"
    clock.advance(hours=10)
    act(session["session_id"], "resume")
    study(session["session_id"], clock, 4 * 60)
    # Study time reaching the estimate completes nothing and verifies nothing.
    state = lesson()["state"]
    assert state["time_reached"] and state["learning_state"] == "STUDYING" and level() == 1


def test_a_failed_check_keeps_the_history_and_a_retake_completes_the_lesson(clock):
    sql_only()
    session = start().json()["session"]
    study(session["session_id"], clock, 20)
    failed = take_check(correct=False, key="a")
    assert failed["status"] == "FAILED" and failed["review_resources"]
    state = lesson()["state"]
    assert state["learning_state"] == "NEEDS_REVIEW" and state["study_seconds"] == 1200 and state["review_state"] == "NONE"
    # Opening the check ended the session: taking a test is not study time.
    assert learning_journey._session(session["session_id"])["status"] == "ENDED"
    # Audit A-03: a new form opens only after time to study again, and the lesson says when.
    assert client.post(f"/activities/{LESSON}/knowledge-check", json={"confirm": True}, headers=STUDENT).status_code == 409
    assert lesson()["state"]["retry_at"]
    clock.advance(hours=RETRY_WAIT_HOURS)
    passed = take_check(correct=True, key="b")
    assert passed["status"] == "PASSED"
    detail = lesson()
    assert detail["state"]["learning_state"] == "COMPLETED" and detail["state"]["study_seconds"] == 1200 and len(detail["checks"]) == 2


def test_locked_prerequisites_cannot_be_started():
    roadmap_for({"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    store.roadmaps[STUDENT_ID]["activity_plan"]["ACT_SQL_02"] = {"kind": "LEARNING", "planned_start": "2026-11-02", "planned_end": "2026-11-08"}
    response = start("ACT_SQL_02")
    assert response.status_code == 409 and "tiên quyết" in response.json()["error"]["message"]


def test_weeks_and_overview_report_progress_from_stored_records(clock):
    roadmap_for({"SQL": 1, "DATA_QUALITY": 1, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    overview = client.get("/me/journey", headers=STUDENT).json()
    assert overview["lessons_total"] >= 2 and overview["lessons_done"] == 0 and overview["next_lesson"]
    assert overview["final"]["eligible"] is False
    start()
    take_check(correct=True)
    overview = client.get("/me/journey", headers=STUDENT).json()
    assert overview["lessons_done"] == 1 and overview["percent"] == round(100 / overview["lessons_total"])
    week = client.get(f"/me/journey/weeks/{overview['weeks'][0]['week_number']}", headers=STUDENT).json()
    assert week["topics"] and all(lesson_item["learning_state"] for topic in week["topics"] for lesson_item in topic["lessons"])
    assert client.get("/me/journey/weeks/99", headers=STUDENT).status_code == 404
    assert client.get("/me/journey/lessons/ACT_VIZ_02", headers=STUDENT).status_code == 404


# ---------------------------------------------------------------- C. Review
def test_the_review_is_counted_from_the_passed_check_with_the_locked_cycle(clock):
    sql_only()
    start(days=3)
    clock.advance(days=2)  # studying for two days does not start the review clock
    assert client.get("/me/checkins", headers=STUDENT).json() == []
    result = take_check(correct=True)
    # Passed on 4 Nov; 3 days later at 08:00 in Ho Chi Minh is 01:00 UTC on 7 Nov.
    assert result["review_cycle_days"] == 3 and result["review_due_at"].startswith("2026-11-07T01:00:00")
    state = lesson()["state"]
    assert state["review_state"] == "SCHEDULED" and state["review_due_at"].startswith("2026-11-07")


def test_a_due_review_opens_a_test_and_its_result_never_lowers_the_level(clock):
    sql_only()
    start(days=1)
    take_check(correct=True)
    verified = level()
    clock.advance(days=2)
    state = lesson()["state"]
    assert state["review_state"] == "DUE" and state["review_micro_id"]
    micro = state["review_micro_id"]
    response = client.post(f"/micro-tests/{micro}/submissions", json={"responses": answers_of(micro, correct=False), "idempotency_key": "r1"}, headers=STUDENT)
    assert response.json()["status"] == "FAILED" and level() == verified
    state = lesson()["state"]
    assert state["review_state"] == "RELEARN" and state["learning_state"] == "COMPLETED"
    rescheduled = client.post(f"/activities/{LESSON}/review/reschedule", headers=STUDENT)
    assert rescheduled.status_code == 200 and rescheduled.json()["review_cycle_days"] == 1
    assert lesson()["state"]["review_state"] == "SCHEDULED"
    assert client.post(f"/activities/{LESSON}/review/reschedule", headers=STUDENT).status_code == 409
    clock.advance(days=2)
    micro = lesson()["state"]["review_micro_id"]
    response = client.post(f"/micro-tests/{micro}/submissions", json={"responses": answers_of(micro), "idempotency_key": "r2"}, headers=STUDENT)
    assert response.json()["status"] == "PASSED" and lesson()["state"]["review_state"] == "PASSED" and level() >= verified


# ---------------------------------------------------------------- Practice
def test_practice_is_graded_by_test_cases_and_is_never_evidence():
    sql_only()
    exercise = lesson()["practice"][0]
    assert "expected_sql" not in json.dumps(exercise) and exercise["checks"]
    before = store.db.one("SELECT COUNT(*) AS n FROM skill_evidence")["n"]
    good = client.post(f"/me/practice/{exercise['exercise_id']}/check", json={"answer": "SELECT status, COUNT(*) AS n FROM orders_raw GROUP BY status ORDER BY n DESC;"}, headers=STUDENT).json()
    bad = client.post(f"/me/practice/{exercise['exercise_id']}/check", json={"answer": "SELECT 1;"}, headers=STUDENT).json()
    assert good["score"] == 100 and bad["score"] < 100
    assert store.db.one("SELECT COUNT(*) AS n FROM skill_evidence")["n"] == before and lesson()["state"]["learning_state"] == "NOT_STARTED"
    assert client.post(f"/me/practice/{exercise['exercise_id']}/check", json={"answer": "   "}, headers=STUDENT).status_code == 422
    assert client.post("/me/practice/PR-PY-01/check", json={"answer": "print(1)"}, headers=STUDENT).status_code == 404  # not in this roadmap


def test_every_practice_exercise_accepts_a_correct_answer():
    assert practice.validate() == []
    answers = {
        "PR-SQL-01": "SELECT status, COUNT(*) FROM orders_raw GROUP BY status ORDER BY 2 DESC;",
        "PR-SQL-02": "WITH c AS (SELECT DISTINCT * FROM orders_raw WHERE status = 'completed' AND quantity > 0 AND region <> ''), r AS (SELECT order_id, region, ROW_NUMBER() OVER (PARTITION BY region ORDER BY quantity * unit_price DESC) AS rn FROM c) SELECT order_id, region FROM r WHERE rn = 1;",
        "PR-DQ-01": "1. Bị hủy: ORD008\n2. Có giảm giá: ORD003, ORD008",
        "PR-DQ-02": "import pandas as pd\ndef check_quality(df):\n    return {'dup': int(df.duplicated().sum()), 'qty': int((df['quantity'] <= 0).sum()), 'region': int(df['region'].isna().sum())}\nprint(check_quality(pd.read_csv('orders.csv')))",
        "PR-PY-01": "import pandas as pd\ndf = pd.read_csv('orders.csv')\nprint(df['customer_id'].nunique())\nprint(df['unit_price'].max())",
        "PR-PY-02": "import pandas as pd\ndf = pd.read_csv('orders.csv').drop_duplicates()\ndf = df[(df['status'] == 'completed') & (df['quantity'] > 0)].copy()\ndf['region'] = df['region'].fillna('Unknown')\ndf['month'] = df['order_date'].str[:7]\nprint(df.pivot_table(index='region', columns='month', values='quantity', aggfunc='sum'))",
        "PR-VIZ-01": "import pandas as pd\nimport matplotlib.pyplot as plt\ndf = pd.read_csv('orders.csv')\nkq = df.groupby('status')['quantity'].sum()\nplt.bar(kq.index, kq.values)\nplt.title('Số lượng theo trạng thái')\nplt.xlabel('Trạng thái')\nplt.ylabel('Số lượng')\nplt.show()",
        "PR-VIZ-02": "KPI 1: 9 khách hàng, trình bày bằng thẻ KPI.\nKPI 2: tổng số lượng 15 sản phẩm, biểu đồ cột theo vùng.\nKPI 3: tỷ lệ hủy 11,11%, biểu đồ đường theo tháng.\nChú giải: tỷ lệ hủy cho thấy cần rà soát khâu giao hàng.",
        "PR-COMM-01": "Trong dữ liệu có 1 đơn bị hủy. Có 2 mã đơn được giảm giá. Dữ liệu chỉ có hai tháng nên chưa thể kết luận nguyên nhân.",
        "PR-COMM-02": "Chỉ số: tỷ lệ hủy đơn.\nHiện tại: 11,11%.\nMục tiêu: giảm xuống dưới 5%.\nThời hạn: trong 2 tháng, nhóm vận hành phụ trách.",
        "PR-STAT-01": "Trung bình: 90.000\nTrung vị: 80.000",
        "PR-STAT-02": "import pandas as pd\ndf = pd.read_csv('orders.csv').drop_duplicates()\nprint(df.groupby('status')['unit_price'].agg(['min', 'max', 'mean']))",
        "PR-STAT-03": "Giả thuyết: xác nhận đơn qua điện thoại làm giảm tỷ lệ hủy. Chỉ số chính là tỷ lệ hủy, hiện là 11,11%. Chia khách ngẫu nhiên vào nhóm đối chứng và nhóm thử. Chạy 4 tuần với cỡ mẫu tính trước. Kết luận bằng kiểm định với mức ý nghĩa 5% (p-value).",
    }
    assert set(answers) == set(practice.EXERCISES)
    for exercise_id, answer in answers.items():
        outcomes, _ = practice.evaluate_question(practice.question_of(practice.EXERCISES[exercise_id]), answer)
        failed = [case_id for case_id, outcome in outcomes.items() if not outcome["passed"]]
        assert not failed, (exercise_id, failed)


# ---------------------------------------------------------------- D. Final assessment
def finish_all_lessons(clock):
    for activity_id in list(learning_journey.lesson_states(STUDENT_ID)):
        start(activity_id, switch=True)
        take_check(activity_id, correct=True, key=activity_id)


def answer_final(kind="good"):
    attempt = client.get("/me/final-assessment", headers=STUDENT).json()["attempt"]
    stored = final_assessment._attempt(attempt["attempt_id"])["payload"]["questions"]
    for question in stored:
        text = good_answer(question["item_id"]) if kind == "good" else "Em chưa làm được."
        assert client.put(f"/me/final-assessment/responses/{question['question_id']}", json={"text": text}, headers=STUDENT).status_code == 200
    return attempt


def test_the_final_assessment_opens_only_after_every_lesson(clock):
    sql_only()
    assert client.post("/me/final-assessment/start", headers=STUDENT).status_code == 409
    finish_all_lessons(clock)
    status = client.get("/me/final-assessment", headers=STUDENT).json()
    assert status["eligible"] and status["can_start"]
    attempt = client.post("/me/final-assessment/start", headers=STUDENT).json()
    again = client.post("/me/final-assessment/start", headers=STUDENT).json()
    assert attempt["attempt_id"] == again["attempt_id"] and "cases" not in json.dumps(attempt["questions"])
    # One practical task per JD skill, at the difficulty of the JD level, not the self-declared one.
    stored = final_assessment._attempt(attempt["attempt_id"])["payload"]["questions"]
    assert {question["skill_code"] for question in stored} == {"SQL", "DATA_QUALITY", "PYTHON", "DATA_VIZ", "WRITTEN_COMM"}
    assert all(question["tier"] == max(question["target_level"], 1) for question in stored)
    # The assistant is paused while the final assessment is open.
    status = client.get("/api/v1/assistant/status", headers=STUDENT).json()
    assert status["blocked"] and status["block_link"] == "#/final-exam"


def test_a_good_final_passes_records_evidence_and_shows_the_completion_summary(clock):
    sql_only()
    finish_all_lessons(clock)
    client.post("/me/final-assessment/start", headers=STUDENT)
    attempt = answer_final("good")
    result = client.post("/me/final-assessment/submit", headers=STUDENT).json()
    assert result["status"] == "GRADED"
    review = client.get(f"/me/final-assessment/{attempt['attempt_id']}/review", headers=STUDENT).json()
    assert review["passed"] and all(rule["passed"] for rule in review["rules"]) and review["score"] >= 70
    assert review["summary"]["lessons_done"] == review["summary"]["lessons_total"] and "không bảo đảm" in review["scope_note"]
    assert {item["skill_code"] for item in review["skills"]} and all(item["level_after"] >= (item["level_before"] or 0) for item in review["skills"])
    rows = store.db.query("SELECT * FROM skill_evidence WHERE source_type = 'FINAL_ASSESSMENT'")
    assert len(rows) == len(review["skills"])
    status = client.get("/me/final-assessment", headers=STUDENT).json()
    assert status["passed_attempt_id"] == attempt["attempt_id"] and not status["can_start"]
    assert client.get("/me/journey", headers=STUDENT).json()["final"]["passed_attempt_id"] == attempt["attempt_id"]


def test_a_failed_final_keeps_levels_points_to_lessons_and_waits_before_a_retake(clock):
    sql_only()
    finish_all_lessons(clock)
    levels = {code: item["level"] for code, item in store.get_or_create_profile(STUDENT_ID)["assessed_skills"].items()}
    client.post("/me/final-assessment/start", headers=STUDENT)
    attempt = answer_final("wrong")
    client.post("/me/final-assessment/submit", headers=STUDENT)
    review = client.get(f"/me/final-assessment/{attempt['attempt_id']}/review", headers=STUDENT).json()
    assert not review["passed"] and any(not rule["passed"] for rule in review["rules"])
    assert {code: item["level"] for code, item in store.get_or_create_profile(STUDENT_ID)["assessed_skills"].items()} == levels
    assert review["summary"]["weak_lessons"] and review["summary"]["lessons_done"] == review["summary"]["lessons_total"]
    assert client.post("/me/final-assessment/start", headers=STUDENT).status_code == 409
    clock.advance(hours=final_assessment.RETAKE_HOURS + 1)
    assert client.post("/me/final-assessment/start", headers=STUDENT).status_code == 200


def test_the_verdict_needs_every_rule_not_only_the_total():
    questions = [
        {"question_id": "Q1", "label": "Bài 1", "skill_code": "SQL", "topic": "t", "tier": 2, "target_level": 2, "weight": 0.5, "is_core": True, "cases": [], "gates": []},
        {"question_id": "Q2", "label": "Bài 2", "skill_code": "PYTHON", "topic": "t", "tier": 1, "target_level": 1, "weight": 0.5, "is_core": False, "cases": [], "gates": []},
    ]
    fake = {"critical": {}, "test_cases": {}, "skill_results": {
        "SQL": {"level": 1, "score": 0.6, "blank": False, "next_steps": []},
        "PYTHON": {"level": 1, "score": 1.0, "blank": False, "next_steps": []},
    }}
    original = final_assessment.verify_exam
    final_assessment.verify_exam = lambda *_: fake
    try:
        verdict = final_assessment.evaluate(questions, {})
    finally:
        final_assessment.verify_exam = original
    rules = {rule["rule"]: rule["passed"] for rule in verdict["rules"]}
    # 80/100 total, but the core SQL skill is below its JD level and only half the weight is met.
    assert verdict["score"] == 80 and rules["SCORE"] and not rules["CORE"] and not rules["COVERAGE"] and not verdict["passed"]


# ---------------------------------------------------------------- E. Personalisation and reset
def test_two_learners_with_the_same_target_get_different_roadmaps():
    roadmap_for({"SQL": 2, "PYTHON": 0, "DATA_QUALITY": 2, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    roadmap_for({"SQL": 0, "PYTHON": 2, "DATA_QUALITY": 2, "DATA_VIZ": 2, "WRITTEN_COMM": 2}, headers=STUDENT_2, user=__import__("uuid").UUID("22222222-2222-2222-2222-222222222222"))
    first = set(learning_journey.lesson_states(STUDENT_ID))
    second = set(learning_journey.lesson_states(__import__("uuid").UUID("22222222-2222-2222-2222-222222222222")))
    assert any(item.startswith("ACT_PY") for item in first) and not any(item.startswith("ACT_SQL") for item in first)
    assert any(item.startswith("ACT_SQL") for item in second) and not any(item.startswith("ACT_PY") for item in second)


def test_a_reset_closes_the_timer_and_takes_the_new_records_out_of_view(clock):
    complete_process(kind="wrong")
    states = learning_journey.lesson_states(STUDENT_ID)
    activity_id = next(iter(states))
    start(activity_id)
    assert client.post(f"{P}/reset", json={"confirm": True}, headers=STUDENT).status_code == 200
    assert store.db.one("SELECT COUNT(*) AS n FROM study_sessions WHERE status IN ('RUNNING', 'PAUSED')")["n"] == 0
    assert store.db.one("SELECT COUNT(*) AS n FROM study_sessions WHERE archived_by_run IS NULL")["n"] == 0
    assert store.db.one("SELECT COUNT(*) AS n FROM lesson_plans WHERE archived_by_run IS NULL")["n"] == 0
    assert client.get("/me/journey", headers=STUDENT).json() is None
    assert client.get("/me/study/current", headers=STUDENT).json()["session"] is None


# ---------------------------------------------------------------- F. Re-planning
def versions():
    return [item["roadmap_version"] for item in client.get("/me/roadmaps/history", headers=STUDENT).json()]


def test_a_pass_that_changes_nothing_else_does_not_reshuffle_the_weeks(clock):
    sql_only()
    start()
    before = versions()
    result = take_check(correct=True)
    assert result["current_level"] == 2 and result["roadmap_update"]["changed"] is False
    assert versions() == before


def test_a_level_change_that_removes_a_lesson_replans_and_keeps_the_history(clock):
    roadmap_for({"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 0, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    assert {"ACT_SQL_01", "ACT_PY_01"} <= set(learning_journey.lesson_states(STUDENT_ID))
    python = start("ACT_PY_01").json()["session"]
    study(python["session_id"], clock, 15)
    act(python["session_id"], "pause")
    before = versions()
    # Python is verified at its target elsewhere (for example by a review), then the SQL lesson is passed.
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["PYTHON"] = {"level": 1}
    start("ACT_SQL_01", switch=True)
    result = take_check("ACT_SQL_01", correct=True)
    assert result["roadmap_update"]["changed"] and result["roadmap_update"]["removed"] == ["ACT_PY_01"]
    journey = client.get("/me/journey", headers=STUDENT).json()
    assert [item["activity_id"] for item in journey["carried_lessons"]] == ["ACT_SQL_01"] and journey["carried_lessons"][0]["learning_state"] == "COMPLETED"
    assert journey["retired_lessons"][0]["activity_id"] == "ACT_PY_01" and "đã đạt" in journey["retired_lessons"][0]["reason"]
    assert "ACT_PY_01" not in learning_journey.lesson_states(STUDENT_ID) and journey["replanned_at"]
    # Nothing is deleted: the old version, the study time and the passed check are all still there.
    assert versions()[: len(before)] == before and len(versions()) == len(before) + 1
    assert learning_journey.study_seconds(STUDENT_ID)["ACT_PY_01"] == 900
    assert learning_journey._session(python["session_id"])["status"] == "ENDED"
    assert client.get("/me/journey/lessons/ACT_SQL_01", headers=STUDENT).json()["carried_over"] is True


def test_a_manual_replan_reschedules_the_rest_from_today_and_keeps_done_lessons(clock):
    roadmap_for({"SQL": 1, "DATA_QUALITY": 1, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    start("ACT_SQL_01")
    take_check("ACT_SQL_01", correct=True)
    dq = start("ACT_DQ_01").json()["session"]
    study(dq["session_id"], clock, 10)
    act(dq["session_id"], "end")
    clock.advance(days=12)
    before = client.get("/me/journey", headers=STUDENT).json()
    result = client.post("/me/journey/replan", headers=STUDENT).json()
    assert result["changed"] and result["added"] == [] and result["removed"] == []
    after = client.get("/me/journey", headers=STUDENT).json()
    assert after["weeks"][0]["start_date"] == "2026-11-14" and after["weeks"][0]["start_date"] > before["weeks"][0]["start_date"]
    assert after["lessons_total"] == before["lessons_total"] and after["lessons_done"] == 1
    assert "ACT_DQ_01" in {lesson["activity_id"] for week in after["weeks"] for topic in week["topics"] for lesson in topic["lessons"]}
    assert after["study_seconds"] == before["study_seconds"] == 600
    # The review schedule survives the re-plan (3-day cycle, 12 days later: due).
    assert learning_journey.lesson_plan(STUDENT_ID, "ACT_SQL_01") and lesson("ACT_SQL_01")["state"]["review_state"] == "DUE"
    assert client.post("/me/journey/replan", headers=STUDENT_2).json()["changed"] is False


# ---------------------------------------------------------------- G. A completed lesson closes its gap
def gap_of(skill):
    return next(item for item in client.get("/me/gap", headers=STUDENT).json()["skill_evaluations"] if item["skill_code"] == skill)


def test_a_full_pass_from_level_zero_confirms_the_lessons_level_and_closes_the_gap(clock):
    """Bug report 11/11/2026: three lesson checks at 100/100 left SQL and visualisation at level 1 of 2."""
    roadmap_for({"SQL": 0, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    start()
    result = take_check(correct=True)
    assert result["status"] == "PASSED" and result["previous_level"] == 0 and result["current_level"] == 2
    assert lesson()["state"]["learning_state"] == "COMPLETED" and gap_of("SQL")["gap"] == 0


def old_rule_pass(level_two_correct=True):
    """A check passed under the old one-step rule: graded 100/100 (or not), level left one step below the lesson."""
    roadmap_for({"SQL": 0, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    start()
    result = take_check(correct=True)
    if not level_two_correct:
        row = store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (result["micro_id"],))
        payload = json.loads(row["payload"])
        for item in payload["result"]["item_results"]:
            if item["level"] == 2:
                item["credit"] = 0.0
        store.db.execute("UPDATE micro_assessments SET payload = ? WHERE micro_id = ?", (json.dumps(payload), result["micro_id"]))
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] = 1
    return result


def test_stored_answers_that_prove_the_level_are_reconfirmed_without_a_new_test(clock):
    """Bug report 12/11/2026: after the fix the gap still showed level 1 until the old answers were read again."""
    result = old_rule_pass()
    before = store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (result["micro_id"],))["payload"]
    assert gap_of("SQL")["current_level"] == 2 and gap_of("SQL")["gap"] == 0
    assert lesson()["state"]["learning_state"] == "COMPLETED"
    rows = store.db.query("SELECT * FROM skill_evidence WHERE skill_code = 'SQL' AND scope_note LIKE 'Tính lại%'")
    assert len(rows) == 1 and rows[0]["level"] == 2 and rows[0]["source_id"] == f"{result['micro_id']}:reconfirm"
    # The graded record itself is untouched, and reading again changes nothing.
    assert store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (result["micro_id"],))["payload"] == before
    gap_of("SQL")
    assert len(store.db.query("SELECT * FROM skill_evidence WHERE scope_note LIKE 'Tính lại%'")) == 1


def test_a_check_passed_under_the_old_one_step_rule_asks_for_a_confirmation(clock):
    old_rule_pass(level_two_correct=False)
    state = lesson()["state"]
    assert state["learning_state"] == "NEEDS_REVIEW" and state["level_short"] and state["skill_level"] == 1 and state["target_level"] == 2
    assert client.get("/me/final-assessment", headers=STUDENT).json()["eligible"] is False
    assert LESSON not in __import__("backend.api.roadmaps", fromlist=["x"]).verified_lessons(STUDENT_ID, store.roadmaps[STUDENT_ID]["activity_plan"])
    again = take_check(correct=True, key="confirm")
    assert again["status"] == "PASSED" and again["current_level"] == 2
    assert lesson()["state"]["learning_state"] == "COMPLETED" and gap_of("SQL")["gap"] == 0
    assert client.post(f"/activities/{LESSON}/knowledge-check", json={"confirm": True}, headers=STUDENT).status_code == 409


def test_a_spaced_review_still_confirms_one_step_at_a_time(clock):
    sql_only()
    start(days=1)
    passed = take_check(correct=True)
    # Stored answers that prove nothing, so the start level stays 0 and only the review can move it.
    row = store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (passed["micro_id"],))
    payload = json.loads(row["payload"])
    for item in payload["result"]["item_results"]:
        item["credit"] = 0.0
    store.db.execute("UPDATE micro_assessments SET payload = ? WHERE micro_id = ?", (json.dumps(payload), passed["micro_id"]))
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] = 0
    clock.advance(days=2)
    micro = lesson()["state"]["review_micro_id"]
    result = client.post(f"/micro-tests/{micro}/submissions", json={"responses": answers_of(micro), "idempotency_key": "rv"}, headers=STUDENT).json()
    assert result["status"] == "PASSED" and result["current_level"] == 1
