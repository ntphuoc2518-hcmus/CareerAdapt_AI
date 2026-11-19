"""The Career Adapt process end to end: order, single attempt, locks, reset and account isolation."""
import json
import uuid

import pytest

from backend import exam_service
from backend.ai_service import assessment_provider, llm_grader
from backend.ai_service.assessment_provider import AssessmentProviderError
from backend.background import purge_expired_answers
from backend.career_process import run_history
from backend.database import Database
from backend.store import store
from v5_helpers import ADMIN, BANK, P, STUDENT, STUDENT_2, STUDENT_ID, answer_all, client, clock, complete_process, good_answer, questions_of, set_default_jd, set_skills, step, timedelta, to_exam


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield
    store.reset()
    clock.set_clock(None)


def start(headers=STUDENT, career="DATA_ANALYST"):
    return client.post(f"{P}/runs", json={"career_code": career}, headers=headers)


# --- Career choice and the one-process rule ---

def test_state_lists_three_careers_and_marks_two_as_simulated():
    state = client.get(f"{P}/state", headers=STUDENT).json()
    assert {item["career_code"]: item["status"] for item in state["careers"]} == {"DATA_ANALYST": "ACTIVE", "BACKEND_DEVELOPER": "SIMULATED", "QA_TESTER": "SIMULATED"}
    assert state["run"] is None


@pytest.mark.parametrize("career", ["BACKEND_DEVELOPER", "QA_TESTER"])
def test_simulated_careers_cannot_be_started_on_the_server(career):
    response = start(career=career)
    assert response.status_code == 409 and "mô phỏng" in response.json()["error"]["message"]
    assert step() is None


def test_unknown_career_is_rejected():
    assert start(career="DOCTOR").status_code == 422


def test_one_account_has_one_process():
    assert start().status_code == 201
    second = start()
    assert second.status_code == 409 and "reset" in second.json()["error"]["message"]


def test_database_refuses_a_second_active_run():
    assert start().status_code == 201
    with pytest.raises(Exception):
        store.db.execute("INSERT INTO career_runs(run_id, user_id, career_code, status, step, payload, created_at, updated_at) VALUES ('x', ?, 'DATA_ANALYST', 'IN_PROGRESS', 'SKILLS', '{}', 'a', 'a')", (str(STUDENT_ID),))


# --- Order of steps ---

def test_steps_cannot_be_skipped():
    start()
    assert set_default_jd().status_code == 409
    assert client.post(f"{P}/exam/start", headers=STUDENT).status_code == 409
    assert client.post(f"{P}/result/confirm", headers=STUDENT).status_code == 409
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 5, "timeline_weeks": 8}, headers=STUDENT).status_code == 409
    assert client.post("/roadmaps", headers=STUDENT).status_code == 409
    assert step() == "SKILLS"


def test_a_confirmed_step_cannot_be_changed():
    start()
    assert set_skills().status_code == 200
    assert step() == "JD"
    assert set_skills({"SQL": 3}).status_code == 409
    assert set_default_jd().status_code == 200
    assert step() == "EXAM"
    assert set_default_jd().status_code == 409
    assert client.patch("/api/v1/me/skill-report/skills/SQL", json={"description": "sửa"}, headers=STUDENT).status_code == 409


def test_profile_form_cannot_rewrite_process_data():
    start()
    set_skills({"SQL": 1})
    profile = client.get("/me/profile", headers=STUDENT).json()
    body = {**{key: profile[key] for key in ("target_career_id", "target_career_version", "job_profile_id", "major")}, "weekly_hours_budget": 9, "target_timeline_weeks": 3, "self_reported_skills": [{"skill_code": "SQL", "level": 3}]}
    assert client.put("/me/profile", json=body, headers=STUDENT).status_code == 200
    after = client.get("/me/profile", headers=STUDENT).json()
    assert after["self_reported_skills"][0]["level"] == 1 and after["weekly_hours_budget"] == 9


# --- Exam form ---

def test_exam_follows_the_jd_level_not_the_declared_level():
    # Audit A-01 (2026-11-12): the old rule took the difficulty from the declared level, so a learner
    # who declared low could never prove the JD level. The difficulty now follows the JD target.
    exam = to_exam(levels={"SQL": 3, "DATA_QUALITY": 0, "PYTHON": 2})
    questions = questions_of(exam["attempt_id"])
    assert all(question["tier"] == min(max(question["target_level"], 1), 3) for question in questions)
    assert {question["skill_code"] for question in questions} == {"SQL", "DATA_QUALITY", "PYTHON", "DATA_VIZ", "WRITTEN_COMM"}
    minutes = {(item["skill_code"], item["tier"]): item["minutes"] for item in BANK["items"]}
    assert exam["remaining_seconds"] > 0 and exam["time_limit_minutes"] == sum(minutes[(question["skill_code"], question["tier"])] for question in questions)


def test_jd_with_fewer_skills_gives_fewer_questions():
    from tests_jd import confirm_two_skill_jd  # noqa: F401
    start()
    set_skills({"SQL": 2})
    assert confirm_two_skill_jd(STUDENT) == 200
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    assert len(exam["questions"]) == 2
    assert {item["skill_code"] for item in questions_of(exam["attempt_id"])} == {"SQL", "DATA_QUALITY"}


def test_learner_view_never_contains_the_answer_key():
    exam = to_exam()
    text = json.dumps(exam, ensure_ascii=False)
    assert "expected_sql" not in text and "cases" not in text and "gates" not in text and "reference" not in text


def test_answers_are_saved_on_the_server_and_survive_switching():
    exam = to_exam()
    client.put(f"{P}/exam/responses/Q1", json={"text": "bài 1 chưa xong"}, headers=STUDENT)
    client.put(f"{P}/exam/responses/Q2", json={"text": "bài 2"}, headers=STUDENT)
    client.put(f"{P}/exam/responses/Q1", json={"text": "bài 1 đã sửa"}, headers=STUDENT)
    state = client.get(f"{P}/exam", headers=STUDENT).json()
    assert [question["answer"] for question in state["questions"]][:3] == ["bài 1 đã sửa", "bài 2", ""]
    assert state["attempt_id"] == exam["attempt_id"]


def test_reopening_the_exam_does_not_restart_the_clock():
    exam = to_exam()
    again = client.post(f"{P}/exam/start", headers=STUDENT).json()
    assert again["attempt_id"] == exam["attempt_id"] and again["started_at"] == exam["started_at"]


def test_oversized_and_unknown_answers_are_rejected():
    to_exam()
    assert client.put(f"{P}/exam/responses/Q99", json={"text": "x"}, headers=STUDENT).status_code == 404
    assert client.put(f"{P}/exam/responses/Q1", json={"text": "x" * 19000}, headers=STUDENT).status_code == 413


# --- Submission ---

def test_good_exam_end_to_end_gives_score_levels_and_explanations():
    exam = to_exam()
    answer_all(exam)
    response = client.post(f"{P}/exam/submit", json={}, headers=STUDENT).json()
    assert response["status"] == "GRADED" and step() == "RESULT"
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["score"] == 100 and review["passed"] is True
    assert all(question["correct"] and question["cases"] and question["answer"] for question in review["questions"])
    assert all(case["explanation"].startswith("Đúng") for question in review["questions"] for case in question["cases"])
    # Audit A-01: questions are set at the JD level, so a full-marks exam proves exactly the JD level
    # for every skill (before, it proved the declared level, e.g. WRITTEN_COMM 3 and DATA_QUALITY 1).
    levels = {item["skill_code"]: item["verified_level"] for item in review["conclusion"]["skills"]}
    assert levels == {item["skill_code"]: item["target_level"] for item in review["conclusion"]["skills"]}
    assert "Trình độ đã xác thực" in review["conclusion"]["summary"] and "Đáp ứng 5/5" in review["conclusion"]["summary"]
    profile = client.get("/me/profile", headers=STUDENT).json()
    assert profile["assessed_skills"]["WRITTEN_COMM"]["level"] == levels["WRITTEN_COMM"]


def test_wrong_exam_explains_each_mistake():
    exam = to_exam()
    answer_all(exam, "wrong")
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["passed"] is False and review["score"] < 40
    failed = [case for question in review["questions"] for case in question["cases"] if not case["passed"]]
    assert failed and all(case["explanation"].startswith("Sai") for case in failed)


def test_blank_exam_is_final_with_zero_and_level_zero():
    to_exam()
    assert client.post(f"{P}/exam/submit", json={}, headers=STUDENT).json()["status"] == "GRADED"
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["score"] == 0 and all(question["blank"] for question in review["questions"])
    assert all(item["verified_level"] == 0 for item in review["conclusion"]["skills"])
    assert "Bỏ trống" in review["conclusion"]["skills"][0]["reason"]


def test_submitted_exam_is_locked_and_cannot_be_submitted_twice():
    exam = to_exam()
    answer_all(exam)
    first = client.post(f"{P}/exam/submit", json={}, headers=STUDENT).json()
    assert first["is_duplicate"] is False
    assert client.put(f"{P}/exam/responses/Q1", json={"text": "sửa sau khi nộp"}, headers=STUDENT).status_code == 409
    second = client.post(f"{P}/exam/submit", json={}, headers=STUDENT).json()
    assert second["is_duplicate"] is True
    assert store.db.one("SELECT COUNT(*) AS n FROM final_assessments")["n"] == 1
    assert store.db.one("SELECT COUNT(*) AS n FROM exam_attempts")["n"] == 1
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert "sửa sau khi nộp" not in json.dumps(review, ensure_ascii=False)


def test_exam_cannot_be_started_again_after_grading():
    exam = to_exam()
    answer_all(exam)
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    assert client.post(f"{P}/exam/start", headers=STUDENT).status_code == 409


def test_review_is_refused_before_submission():
    to_exam()
    assert client.get(f"{P}/exam/review", headers=STUDENT).status_code == 409


def test_old_assessment_route_is_closed_for_learners(monkeypatch):
    monkeypatch.setenv("CAREERADAPT_LEGACY_ASSESSMENT_API", "false")
    response = client.post("/submissions", json={"task_id": "DA01A", "mode": "PRACTICE", "answers": {"Q2_SQL": "SELECT 1"}}, headers=STUDENT)
    assert response.status_code == 410


# --- Timer and integrity ---

def test_time_up_submits_what_was_saved_on_the_server():
    from datetime import datetime, timezone
    exam = to_exam()
    client.put(f"{P}/exam/responses/Q1", json={"text": "SELECT 1;"}, headers=STUDENT)
    fixed = datetime.fromisoformat(exam["started_at"]) + timedelta(hours=2)
    clock.set_clock(lambda: fixed)
    assert client.put(f"{P}/exam/responses/Q2", json={"text": "muộn"}, headers=STUDENT).status_code == 409
    state = client.get(f"{P}/state", headers=STUDENT).json()
    assert state["run"]["step"] == "RESULT" and state["exam_status"] == "GRADED"
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["auto_submitted"] is True and datetime.fromisoformat(review["submitted_at"]).tzinfo == timezone.utc


def test_background_sweep_submits_abandoned_exams():
    from datetime import datetime
    exam = to_exam()
    fixed = datetime.fromisoformat(exam["started_at"]) + timedelta(hours=2)
    clock.set_clock(lambda: fixed)
    assert exam_service.finish_expired() == 1
    assert store.db.one("SELECT status FROM exam_attempts")["status"] == "GRADED"


def test_third_tab_switch_submits_the_exam():
    to_exam()
    event = {"kind": "focus_lost", "detail": "tab"}
    assert client.post(f"{P}/exam/events", json=event, headers=STUDENT).json()["violations"] == 1
    second = client.post(f"{P}/exam/events", json=event, headers=STUDENT).json()
    assert second["auto_submitted"] is False and second["max_violations"] == 3
    third = client.post(f"{P}/exam/events", json=event, headers=STUDENT).json()
    assert third["auto_submitted"] is True
    assert step() == "RESULT"
    assert client.get(f"{P}/exam/review", headers=STUDENT).json()["violations"] == 3


def test_blocked_paste_is_logged_but_not_a_strike():
    to_exam()
    result = client.post(f"{P}/exam/events", json={"kind": "paste_blocked"}, headers=STUDENT).json()
    assert result["violations"] == 0
    assert store.db.one("SELECT COUNT(*) AS n FROM exam_events")["n"] == 1


# --- AI layer ---

def ai_payload(exam, level=None, quote=None):
    questions = questions_of(exam["attempt_id"])
    return {"criteria": [{"criterion_id": question["question_id"], "proposed_level": question["tier"] if level is None else level, "evidence": [{"kind": "quote", "value": quote or good_answer(question["item_id"])[:30]}], "reason": f"Nhận xét {question['question_id']}", "uncertainties": "", "needs_review": False} for question in questions], "overall_feedback": "Tổng thể khá."}


def enable_ai(monkeypatch, handler):
    monkeypatch.setattr(assessment_provider, "is_enabled", lambda: True)
    monkeypatch.setattr(llm_grader, "evaluate_submission", handler)


def test_valid_ai_comment_is_shown_per_question_and_cannot_change_score(monkeypatch):
    exam = to_exam()
    answer_all(exam)
    enable_ai(monkeypatch, lambda *args: ai_payload(exam))
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["score"] == 100 and review["ai"]["used"] is True and review["ai"]["overall"] == "Tổng thể khá."
    assert review["questions"][0]["ai_comment"]["reason"] == "Nhận xét Q1"


def test_fake_ai_quote_is_dropped_and_flagged_without_blocking(monkeypatch):
    exam = to_exam()
    answer_all(exam)
    enable_ai(monkeypatch, lambda *args: ai_payload(exam, quote="ĐOẠN KHÔNG CÓ TRONG BÀI"))
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    assert step() == "RESULT"
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["score"] == 100 and review["ai"]["used"] is False and review["ai"]["flag"]["code"] == "FAKE_EVIDENCE"
    assert review["questions"][0]["ai_comment"] is None
    flags = client.get(f"{P}/admin/ai-flags", headers=ADMIN).json()
    assert len(flags) == 1 and flags[0]["code"] == "FAKE_EVIDENCE"
    assert client.get(f"{P}/admin/ai-flags", headers=STUDENT).status_code == 403


def test_ai_timeout_does_not_block_or_lose_the_exam(monkeypatch):
    exam = to_exam()
    answer_all(exam)

    def fail(*args):
        raise AssessmentProviderError("timeout", "AI_TIMEOUT")
    enable_ai(monkeypatch, fail)
    assert client.post(f"{P}/exam/submit", json={}, headers=STUDENT).json()["status"] == "GRADED"
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["score"] == 100 and review["ai"]["flag"]["code"] == "AI_TIMEOUT"


def test_ai_cannot_inflate_a_wrong_exam(monkeypatch):
    exam = to_exam()
    answer_all(exam, "wrong")
    enable_ai(monkeypatch, lambda *args: {**ai_payload(exam, level=3), "overall_feedback": "Xuất sắc, 100 điểm."})
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["score"] < 40 and review["ai"]["used"] is False


def test_jd_summary_is_labelled_rule_without_ai():
    start()
    set_skills()
    set_default_jd()
    jd = client.get(f"{P}/state", headers=STUDENT).json()["run"]["jd"]
    assert jd["summary_source"] == "RULE" and "SQL" in jd["summary"]


def test_jd_summary_uses_ai_when_configured(monkeypatch):
    monkeypatch.setattr(assessment_provider, "is_enabled", lambda: True)
    monkeypatch.setattr(assessment_provider.config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(assessment_provider, "_call_openai", lambda *args: {"summary": "Tóm tắt AI."})
    assert assessment_provider.summarize_jd({"name": "X"}, "Nội dung JD") == {"text": "Tóm tắt AI.", "source": "AI"}
    monkeypatch.setattr(assessment_provider, "_call_openai", lambda *args: (_ for _ in ()).throw(OSError("mạng lỗi")))
    assert assessment_provider.summarize_jd({"name": "X"}, "Nội dung JD")["source"] == "RULE"


# --- Roadmap, completion and locks ---

def test_full_process_completes_and_freezes():
    complete_process()
    state = client.get(f"{P}/state", headers=STUDENT).json()
    assert state["run"]["status"] == "COMPLETED" and state["run"]["step"] == "DONE"
    roadmap = client.get("/me/roadmap", headers=STUDENT).json()
    assert roadmap["weekly_hours_budget"] == 6 and roadmap["schedule"]["scheduled_weeks"] is not None
    assert client.post("/roadmaps", headers=STUDENT).status_code == 409
    assert set_default_jd().status_code == 409
    assert set_skills({"SQL": 3}).status_code == 409
    assert client.post(f"{P}/exam/start", headers=STUDENT).status_code == 409
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 409


def test_process_gap_uses_only_verified_levels():
    complete_process(levels={"SQL": 0, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 1, "WRITTEN_COMM": 1}, kind="good")
    gap = client.get("/me/gap", headers=STUDENT).json()
    assert gap["coverage"] == 1
    sql = next(item for item in gap["skill_evaluations"] if item["skill_code"] == "SQL")
    # Audit A-01: declaring 0 no longer caps a full-marks answer at level 1; the verified level is the JD level.
    assert sql["current_level"] == sql["target_level"] and sql["self_reported_level"] == 0 and sql["gap"] == 0


def test_weak_exam_gets_a_roadmap_with_weeks():
    complete_process(kind="wrong", weekly_hours=5)
    roadmap = client.get("/me/roadmap", headers=STUDENT).json()
    weeks = roadmap["schedule"]["scheduled_weeks"]
    assert weeks and weeks[0]["week_number"] == 1
    assert all(activity["kind"] == "LEARNING" for week in weeks for activity in week["activities"])
    assert all(activity["resources"] for week in weeks for activity in week["activities"])


def test_prerequisite_outside_the_jd_is_still_scheduled():
    from tests_jd import JD_VIZ_ONLY, confirm_jd
    start()
    set_skills({"DATA_VIZ": 2})
    assert confirm_jd(STUDENT, JD_VIZ_ONLY, {"DATA_VIZ"}) == 200
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    assert [question["skill_code"] for question in questions_of(exam["attempt_id"])] == ["DATA_VIZ"]
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    client.post(f"{P}/result/confirm", headers=STUDENT)
    client.post(f"{P}/roadmap", json={"weekly_hours": 6, "timeline_weeks": 8}, headers=STUDENT)
    roadmap = client.get("/me/roadmap", headers=STUDENT).json()
    planned = [activity["activity_id"] for week in roadmap["schedule"]["scheduled_weeks"] for activity in week["activities"]]
    assert "ACT_PY_01" in planned and "ACT_VIZ_01" in planned and planned.index("ACT_PY_01") < planned.index("ACT_VIZ_01")


def test_progress_updates_after_completion_without_changing_levels():
    complete_process(kind="wrong")
    roadmap = client.get("/me/roadmap", headers=STUDENT).json()
    activity = roadmap["schedule"]["scheduled_weeks"][0]["activities"][0]["activity_id"]
    before = client.get("/me/profile", headers=STUDENT).json()["assessed_skills"]
    response = client.patch(f"/activities/{activity}/progress", json={"status": "COMPLETED", "progress_percent": 100}, headers=STUDENT)
    assert response.status_code == 200 and response.json()["overall_progress_percent"] > 0
    assert client.get("/me/profile", headers=STUDENT).json()["assessed_skills"] == before
    # Roadmap 2.0: "studied" alone does not start the review clock.
    assert client.get("/me/checkins", headers=STUDENT).json() == []


def test_results_survive_a_restart():
    complete_process()
    run = store.db.one("SELECT * FROM career_runs")
    assert json.loads(run["payload"])["exam"]["submission_id"]
    assert client.get(f"{P}/exam/review", headers=STUDENT).status_code == 200


def test_invalid_hours_are_rejected():
    exam = to_exam()
    answer_all(exam)
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    client.post(f"{P}/result/confirm", headers=STUDENT)
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 0, "timeline_weeks": 8}, headers=STUDENT).status_code == 422
    assert step() == "ROADMAP"


# --- Reset ---

def test_reset_preview_lists_exact_data():
    complete_process(kind="wrong")
    preview = client.get(f"{P}/reset-preview", headers=STUDENT).json()
    counts = {item["label"]: item["count"] for item in preview["items"]}
    assert counts["Kỹ năng đã khai báo"] == 5 and counts["Bài kiểm tra, điểm và nhận xét"] == 1 and counts["Lộ trình học tập"] == 1
    assert "Tài khoản và mật khẩu" in preview["kept"]


def test_reset_requires_confirmation_and_an_existing_run():
    assert client.post(f"{P}/reset", json={"confirm": True}, headers=STUDENT).status_code == 404
    start()
    assert client.post(f"{P}/reset", json={"confirm": False}, headers=STUDENT).status_code == 422
    assert step() == "SKILLS"


def test_reset_is_refused_while_the_exam_is_running():
    to_exam()
    assert client.post(f"{P}/reset", json={"confirm": True}, headers=STUDENT).status_code == 409


def test_reset_clears_the_view_and_allows_starting_again():
    exam = complete_process(kind="wrong")
    roadmap = client.get("/me/roadmap", headers=STUDENT).json()
    activity = roadmap["schedule"]["scheduled_weeks"][0]["activities"][0]["activity_id"]
    client.patch(f"/activities/{activity}/progress", json={"status": "COMPLETED", "progress_percent": 100}, headers=STUDENT)
    assert client.post(f"{P}/reset", json={"confirm": True}, headers=STUDENT).status_code == 200
    state = client.get(f"{P}/state", headers=STUDENT).json()
    assert state["run"] is None and state["archived_runs"] == 1
    profile = client.get("/me/profile", headers=STUDENT).json()
    assert profile["assessed_skills"] == {} and profile["self_reported_skills"] == [] and "target_jd" not in profile
    assert client.get("/me/roadmap", headers=STUDENT).json() is None
    assert client.get("/me/skill-history", headers=STUDENT).json() == []
    assert client.get("/me/checkins", headers=STUDENT).json() == []
    assert client.get("/me/gap", headers=STUDENT).json()["skills_measured"] == 0
    assert client.get("/me/assessments", headers=STUDENT).json() == []
    assert client.get(f"{P}/exam/review", headers=STUDENT).status_code == 409
    # Nothing was lost: the rows and a snapshot stay in the archive.
    assert store.db.one("SELECT COUNT(*) AS n FROM skill_evidence")["n"] == 5
    archived = store.db.one("SELECT status, payload FROM career_runs")
    assert archived["status"] == "ARCHIVED" and json.loads(archived["payload"])["archive"]["profile"]["assessed_skills"]
    second = to_exam(levels={"SQL": 2, "DATA_QUALITY": 2, "PYTHON": 2, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    assert second["attempt_id"] != exam["attempt_id"]
    assert store.db.one("SELECT COUNT(*) AS n FROM exam_attempts")["n"] == 2


def test_reset_gives_a_new_dataset_for_the_same_questions():
    first = complete_process(levels={"SQL": 2, "DATA_QUALITY": 2, "PYTHON": 2, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    client.post(f"{P}/reset", json={"confirm": True}, headers=STUDENT)
    second = to_exam(levels={"SQL": 2, "DATA_QUALITY": 2, "PYTHON": 2, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    assert {item["item_id"] for item in questions_of(first["attempt_id"])}.isdisjoint(item["item_id"] for item in questions_of(second["attempt_id"]))


def test_reset_keeps_knowledge_test_history():
    attempt = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    start()
    client.post(f"{P}/reset", json={"confirm": True}, headers=STUDENT)
    assert any(item["attempt_id"] == attempt["attempt_id"] for item in client.get("/api/v1/tests/attempts", headers=STUDENT).json()["attempts"])


def test_reset_never_touches_another_account():
    complete_process(STUDENT_2, kind="wrong")
    before = client.get("/me/roadmap", headers=STUDENT_2).json()["roadmap_id"]
    complete_process(STUDENT, kind="good")
    client.post(f"{P}/reset", json={"confirm": True}, headers=STUDENT)
    state = client.get(f"{P}/state", headers=STUDENT_2).json()
    assert state["run"]["status"] == "COMPLETED"
    assert client.get("/me/roadmap", headers=STUDENT_2).json()["roadmap_id"] == before
    assert client.get(f"{P}/exam/review", headers=STUDENT_2).status_code == 200
    assert client.get("/me/skill-history", headers=STUDENT_2).json()


def test_accounts_do_not_see_each_others_exam():
    exam = to_exam(STUDENT)
    client.put(f"{P}/exam/responses/Q1", json={"text": "bí mật"}, headers=STUDENT)
    assert client.get(f"{P}/exam", headers=STUDENT_2).status_code == 404
    other = to_exam(STUDENT_2)
    assert other["attempt_id"] != exam["attempt_id"]
    assert other["questions"][0]["answer"] == ""
    assert client.put(f"{P}/exam/responses/Q1", json={"text": "của tài khoản 2"}, headers=STUDENT_2).status_code == 200
    assert client.get(f"{P}/exam", headers=STUDENT).json()["questions"][0]["answer"] == "bí mật"


def test_old_results_are_archived_when_a_process_starts():
    from v4_helpers import DA01_GOOD, submit
    assert submit(DA01_GOOD).status_code == 201
    assert client.get("/me/profile", headers=STUDENT).json()["assessed_skills"]
    start()
    assert client.get("/me/profile", headers=STUDENT).json()["assessed_skills"] == {}
    history = run_history(STUDENT_ID)
    assert len(history) == 1 and history[0]["status"] == "ARCHIVED"
    legacy = json.loads(store.db.one("SELECT payload FROM career_runs WHERE status = 'ARCHIVED'")["payload"])
    assert legacy["legacy"] is True and legacy["archive"]["profile"]["assessed_skills"]


def test_erasure_removes_every_process_row():
    complete_process(kind="wrong")
    assert client.delete("/me/data", headers=STUDENT).status_code == 200
    for table in ("career_runs", "exam_attempts", "exam_responses", "exam_events"):
        assert store.db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"] == 0
    assert step() is None


def test_retention_keeps_exam_answers_for_review():
    exam = complete_process()
    fixed = clock.utcnow() + timedelta(days=200)
    clock.set_clock(lambda: fixed)
    purge_expired_answers()
    answers = store.db.query("SELECT answer_text FROM submission_answers")
    assert answers and all(row["answer_text"] for row in answers)
    assert client.get(f"{P}/exam/review", headers=STUDENT).json()["questions"][0]["answer"]
    assert exam


# --- Migration ---

def test_migration_adds_columns_keeps_rows_and_backs_up(tmp_path):
    path = tmp_path / "old.sqlite3"
    old = Database(path)
    for table in ("history_events", "target_versions", "skill_evidence", "roadmap_versions", "progress_records"):
        old.execute(f"ALTER TABLE {table} DROP COLUMN archived_by_run")
    old.set_meta("schema_version", "1")
    old.execute("INSERT INTO skill_evidence(evidence_id, user_id, skill_code, level, source_type, source_id, created_at) VALUES ('e1', 'u', 'SQL', 2, 'ASSESSMENT', 's', 'now')")
    old.close()
    upgraded = Database(path)
    assert upgraded.get_meta("schema_version") == "2"
    assert upgraded.one("SELECT evidence_id, archived_by_run FROM skill_evidence") == {"evidence_id": "e1", "archived_by_run": None}
    assert (tmp_path / "old.sqlite3.pre-v2.bak").exists()
    upgraded.close()
    again = Database(path)
    assert again.one("SELECT COUNT(*) AS n FROM skill_evidence")["n"] == 1
    again.close()


def test_uuid_of_helper_is_stable():
    assert isinstance(STUDENT_ID, uuid.UUID)
