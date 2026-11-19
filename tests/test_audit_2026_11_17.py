"""Regression tests for the 2026-11-17 master audit (FINAL_IMPLEMENTATION_AND_UPGRADE_REPORT.md).

P1-2 keyword stuffing, P1-4 leaving an open goal change, P1-1 the assessment reliability table.
"""
from __future__ import annotations

import pytest

from backend.assessment_reliability import rate
from backend.clock import set_clock
from backend.engine.exam_grader import BANK, verify_exam
from backend.store import store
from v5_helpers import FACTS, GOOD, P, STUDENT, STUDENT_2, client, good_answer, questions_of, set_default_jd, set_skills, step


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    set_clock(None)
    yield
    set_clock(None)


def question(item_id: str, variant: str = "A") -> dict:
    item = next(entry for entry in BANK["items"] if entry["item_id"] == item_id)
    return {**item, "question_id": "Q1", "label": "Bài 1", "dataset": BANK["datasets"][variant], "gates": item.get("gates", []), "weight": 1.0, "target_level": item["tier"]}


def graded(item_id: str, answer: str, variant: str = "A") -> dict:
    q = question(item_id, variant)
    return verify_exam([q], {"Q1": answer})["skill_results"][q["skill_code"]]


FILLER = "điều này rất quan trọng cho công việc của chúng ta hiện nay"


# --- P1-2: keyword stuffing earns nothing ---

@pytest.mark.parametrize("item_id,answer", [
    # Each concept padded with the same filler sentence: the filler is not the learner's explanation.
    ("STAT-3", f"Cỡ mẫu nhỏ {FILLER}. Dùng kiểm định t-test với p-value và khoảng tin cậy {FILLER}. Chia ngẫu nhiên nhóm đối chứng {FILLER}."),
    ("VIZ-1", f"Biểu đồ cột bar chart {FILLER}. So sánh cao nhất xếp hạng {FILLER}. Vùng doanh thu {FILLER}."),
    ("WC-2", f"Chúng ta nên đề xuất khuyến nghị {FILLER}. Dữ liệu ít, mẫu nhỏ, chưa thể kết luận {FILLER}."),
])
def test_repeated_padding_does_not_make_a_concept_count(item_id, answer):
    result = graded(item_id, answer)
    assert result["score"] <= 0.15 and result["level"] == 0


def test_copying_the_question_is_not_an_explanation():
    # The prompt's own sentence around the concept gives the answer no words of its own.
    copied = "Giải thích vì sao với dữ liệu này chưa thể kết luận hai tháng khác nhau có ý nghĩa thống kê: mẫu nhỏ."
    outcome = verify_exam([question("STAT-3")], {"Q1": copied})["test_cases"]["Q1.sample"]
    assert outcome["passed"] is False


def test_a_keyword_list_sentence_does_not_count():
    listed = "Kiểm định t-test, p-value, khoảng tin cậy, z-test, mức ý nghĩa."
    assert verify_exam([question("STAT-3")], {"Q1": listed})["test_cases"]["Q1.method"]["passed"] is False


def test_stuffing_after_correct_figures_no_longer_reaches_the_top_level():
    f = FACTS["A"]
    stuffed = f"Số liệu {f['a1']} và {f['a2']}. Cỡ mẫu nhỏ {FILLER}. Dùng kiểm định t-test {FILLER}. Chia ngẫu nhiên nhóm đối chứng {FILLER}."
    assert graded("STAT-3", stuffed)["level"] <= 1


@pytest.mark.parametrize("item_id", sorted(GOOD))
@pytest.mark.parametrize("variant", "ABCD")
def test_reference_answers_still_score_full_marks(item_id, variant):
    assert graded(item_id, GOOD[item_id](FACTS[variant]), variant)["score"] == 1.0


def test_confidence_follows_the_kind_of_evidence():
    assert graded("SQL-2", good_answer("SQL-2-A"))["confidence"] == 0.7
    assert graded("STAT-3", GOOD["STAT-3"](FACTS["A"]))["confidence"] == 0.6
    assert graded("VIZ-1", GOOD["VIZ-1"](FACTS["A"]))["confidence"] == 0.3
    assert graded("SQL-1", "")["confidence"] == 0.0


# --- P1-4: an open goal change can be left without picking a JD ---

def _finished_process():
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    set_skills()
    set_default_jd()
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    for q in questions_of(exam["attempt_id"]):
        client.put(f"{P}/exam/responses/{q['question_id']}", json={"text": good_answer(q["item_id"])}, headers=STUDENT)
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    client.post(f"{P}/result/confirm", headers=STUDENT)
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 6, "timeline_weeks": 8}, headers=STUDENT).status_code == 200


def test_cancelling_a_goal_change_restores_the_finished_run():
    _finished_process()
    before = client.get(f"{P}/state", headers=STUDENT).json()["run"]
    assert before["status"] == "COMPLETED"
    assert client.post(f"{P}/change-goal", json={"confirm": True}, headers=STUDENT).status_code == 200
    assert step() == "JD"
    cancelled = client.post(f"{P}/change-goal/cancel", headers=STUDENT)
    assert cancelled.status_code == 200
    after = client.get(f"{P}/state", headers=STUDENT).json()["run"]
    assert (after["status"], after["step"], after["completed_at"], after["goal_change"], after["goal_changes"]) == (before["status"], before["step"], before["completed_at"], False, 0)
    assert after["jd"] == before["jd"]
    events = [row["event"] for row in store.db.query("SELECT event FROM history_events WHERE user_id = (SELECT user_id FROM career_runs LIMIT 1)")]
    assert "GOAL_CHANGE_CANCELLED" in events
    # Nothing to cancel any more, and the change can be opened again afterwards.
    assert client.post(f"{P}/change-goal/cancel", headers=STUDENT).status_code == 409
    assert client.post(f"{P}/change-goal", json={"confirm": True}, headers=STUDENT).status_code == 200


def test_cancel_is_refused_without_an_open_change_and_for_another_account():
    _finished_process()
    assert client.post(f"{P}/change-goal/cancel", headers=STUDENT).status_code == 409
    assert client.post(f"{P}/change-goal", json={"confirm": True}, headers=STUDENT).status_code == 200
    assert client.post(f"{P}/change-goal/cancel", headers=STUDENT_2).status_code == 409
    assert step() == "JD"
    assert client.post(f"{P}/change-goal/cancel").status_code in (401, 403)


# --- P1-1: the reliability table ---

def _source(kind: str, level: int, label: str = "Bài kiểm tra đầu vào") -> dict:
    return {"kind": kind, "level": level, "source_label": label}


@pytest.mark.parametrize("level,sources,expected", [
    (None, [], "NONE"),
    (2, [_source("CODE", 2)], "MEDIUM"),
    (2, [_source("CODE", 2), _source("QUIZ", 2)], "HIGH"),
    (2, [_source("WRITTEN_KEYWORDS", 2)], "LOW"),
    (2, [_source("QUIZ", 2)], "LOW"),
    (2, [_source("QUIZ", 2), _source("QUIZ", 2)], "MEDIUM"),
    (2, [_source("CODE", 2), _source("CODE", 2), _source("QUIZ", 1, "Kiểm tra kiến thức")], "LOW"),
    (2, [_source("CODE", 1), _source("QUIZ", 2)], "LOW"),
    (0, [_source("NOTHING", 0)], "LOW"),
])
def test_rating_rules(level, sources, expected):
    rating, reasons = rate(level, sources)
    assert rating == expected and reasons


def test_reliability_api_reads_the_exam_evidence():
    _finished_process()
    data = client.get("/me/assessment-reliability", headers=STUDENT).json()
    by_code = {item["skill_code"]: item for item in data["skills"]}
    assert by_code, data
    sql = by_code["SQL"]
    assert sql["current_level"] is not None and sql["supporting"] == 1 and sql["rating"] == "MEDIUM"
    assert [source["kind"] for source in sql["sources"]] == ["CODE"]
    # One question per skill: the table says so instead of hiding it.
    assert any("một bài duy nhất" in reason for reason in sql["reasons"])
    assert sum(data["counts"].values()) == len(data["skills"])
    assert client.get("/me/assessment-reliability").status_code == 401
    other = client.get("/me/assessment-reliability", headers=STUDENT_2).json()
    assert all(item["rating"] == "NONE" for item in other["skills"])


# --- Recovery: an abandoned final assessment is submitted by the background sweep ---

def test_the_background_sweep_submits_an_abandoned_final_assessment():
    from backend import background, final_assessment
    from test_learning_roadmap_2 import Clock, finish_all_lessons, sql_only

    clock = Clock()
    set_clock(clock)
    sql_only()
    finish_all_lessons(clock)
    attempt = client.post("/me/final-assessment/start", headers=STUDENT).json()
    stored = final_assessment._attempt(attempt["attempt_id"])
    assert stored["status"] == "IN_PROGRESS"
    clock.advance(minutes=stored["payload"]["time_limit_minutes"] + 5)
    # No request from the learner: only the background tick runs.
    assert background.finish_expired_exams() >= 1
    settled = final_assessment._attempt(attempt["attempt_id"])
    assert settled["status"] == "GRADED" and settled["auto_submitted"]


# --- Several tabs: an older page cannot overwrite a newer saved answer ---

def test_a_second_tab_cannot_overwrite_a_newer_answer():
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    set_skills()
    set_default_jd()
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    qid = exam["questions"][0]["question_id"]
    assert exam["questions"][0]["saved_at"] == ""
    url = f"{P}/exam/responses/{qid}"
    first = client.put(url, json={"text": "SELECT 1;", "base_saved_at": ""}, headers=STUDENT)
    assert first.status_code == 200
    # Tab B opened before that save still believes nothing was saved.
    stale = client.put(url, json={"text": "SELECT 2;", "base_saved_at": ""}, headers=STUDENT)
    assert stale.status_code == 409 and "tab" in stale.json()["error"]["message"]
    assert client.put(url, json={"text": "SELECT 3;", "base_saved_at": first.json()["saved_at"]}, headers=STUDENT).status_code == 200
    # Re-sending the text already stored is never a conflict; a client without a base keeps last-write-wins.
    assert client.put(url, json={"text": "SELECT 3;", "base_saved_at": ""}, headers=STUDENT).status_code == 200
    assert client.put(url, json={"text": "SELECT 4;"}, headers=STUDENT).status_code == 200
    state = client.get(f"{P}/exam", headers=STUDENT).json()
    assert state["questions"][0]["answer"] == "SELECT 4;" and state["questions"][0]["saved_at"]


def test_a_large_insert_is_noted_for_the_review_and_changes_no_mark():
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    set_skills()
    set_default_jd()
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    questions = questions_of(exam["attempt_id"])
    answers = {q["question_id"]: good_answer(q["item_id"]) for q in questions}
    longest = max(answers, key=lambda key: len(answers[key]))
    padded = answers[longest] + "\n" + "-- ghi chú " * 40 if any(q["question_id"] == longest and q["answer_type"] == "sql" for q in questions) else answers[longest] + " " + "x" * 400
    for qid, text in answers.items():
        client.put(f"{P}/exam/responses/{qid}", json={"text": padded if qid == longest else text}, headers=STUDENT)
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    integrity = review["integrity"]
    assert integrity["large_inserts"] >= 1 and longest in integrity["large_insert_questions"]
    assert "không ảnh hưởng điểm" in integrity["note"]


# --- C-08: one assessment policy ---

def test_every_module_applies_the_numbers_of_the_one_policy():
    from backend import assessment_policy as policy, final_assessment, learning_cycle_service, lesson_checks
    from backend.engine import exam_grader

    assert exam_grader.PASS_THRESHOLD == policy.EXAM_PASS_SCORE and exam_grader.validate_bank() == []
    assert (exam_grader.PASS_RATIO, exam_grader.PARTIAL_RATIO) == (policy.QUESTION_PASS_RATIO, policy.QUESTION_PARTIAL_RATIO)
    assert (lesson_checks.LESSON_PASS_THRESHOLD, lesson_checks.QUIZ_LEVEL_CEILING, lesson_checks.RETRY_WAIT_HOURS) == (policy.LESSON_CHECK_PASS_SCORE, policy.LESSON_QUIZ_LEVEL_CEILING, policy.LESSON_RETRY_WAIT_HOURS)
    assert learning_cycle_service.PASS_THRESHOLD == policy.MINI_TEST_PASS_SCORE
    assert (final_assessment.RETAKE_HOURS, final_assessment.COVERAGE_REQUIRED) == (policy.FINAL_RETAKE_HOURS, policy.FINAL_COVERAGE_REQUIRED)
    shown = {rule["key"]: rule["value"] for rule in client.get("/me/assessment-policy", headers=STUDENT).json()["rules"]}
    assert shown["EXAM_PASS_SCORE"] == 70 and shown["LESSON_CHECK_PASS_SCORE"] == 80 and shown["FINAL_RETAKE_HOURS"] == 24
    assert client.get("/me/assessment-policy").status_code == 401


# --- Upgrade: lessons list the checks the learner actually failed ---

def _process_with_wrong(skill: str, headers=STUDENT):
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=headers).status_code == 201
    set_skills(headers=headers)
    set_default_jd(headers)
    exam = client.post(f"{P}/exam/start", headers=headers).json()
    for q in questions_of(exam["attempt_id"]):
        text = "" if q["skill_code"] == skill else good_answer(q["item_id"])
        client.put(f"{P}/exam/responses/{q['question_id']}", json={"text": text}, headers=headers)
    client.post(f"{P}/exam/submit", json={}, headers=headers)
    client.post(f"{P}/result/confirm", headers=headers)
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 6, "timeline_weeks": 8}, headers=headers).status_code == 200


def _lessons(headers):
    journey = client.get("/me/journey", headers=headers).json()
    ids = [lesson["activity_id"] for week in journey.get("weeks", []) for topic in week["topics"] for lesson in topic["lessons"]]
    return [client.get(f"/me/journey/lessons/{activity_id}", headers=headers).json() for activity_id in ids]


def test_a_lesson_shows_the_checks_failed_in_its_skill_only():
    _process_with_wrong("SQL")
    lessons = _lessons(STUDENT)
    sql = [item for item in lessons if item["activity"]["target_skill"] == "SQL"]
    assert sql, [item["activity"]["target_skill"] for item in lessons]
    mistakes = sql[0]["mistakes"]
    assert mistakes and all(item["skill_code"] == "SQL" and item["source"] == "Bài kiểm tra đầu vào" and item["blank"] for item in mistakes)
    assert all(not item["mistakes"] for item in lessons if item["activity"]["target_skill"] != "SQL")
    # Another learner who failed another skill gets that skill's checks instead.
    _process_with_wrong("PYTHON", STUDENT_2)
    other = [item for item in _lessons(STUDENT_2) if item["mistakes"]]
    assert other and all(entry["skill_code"] == "PYTHON" for item in other for entry in item["mistakes"])


def test_a_blank_answer_is_not_shown_as_code_evidence():
    _process_with_wrong("SQL")
    sql = next(item for item in client.get("/me/assessment-reliability", headers=STUDENT).json()["skills"] if item["skill_code"] == "SQL")
    assert sql["current_level"] == 0 and sql["rating"] == "LOW"
    assert [source["kind"] for source in sql["sources"]] == ["NOTHING"]
