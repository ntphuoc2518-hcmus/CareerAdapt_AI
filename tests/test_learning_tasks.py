"""Learning tasks and knowledge checks: studied is progress, only a passed check is evidence."""
import json

import pytest

from backend.ai_service import gateway
from backend.ai_service.gateway import GatewayError
from backend.api.learning_cycle import grade_micro
from backend.learning_cycle_service import PASS_THRESHOLD
from datetime import timedelta

from backend.clock import set_clock, utcnow
from backend.lesson_checks import LESSON_PASS_THRESHOLD, RETRY_WAIT_HOURS, _words, select_lesson_items
from backend.store import store
from v4_helpers import STUDENT, STUDENT_2, STUDENT_ID, client

ACTIVITY = "ACT_SQL_01"


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {code: {"level": level} for code, level in {"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2}.items()}
    assert client.post("/roadmaps", headers=STUDENT).status_code in (200, 201)
    yield


def task(activity=ACTIVITY, headers=STUDENT):
    return next(item for item in client.get("/me/learning-tasks", headers=headers).json()["tasks"] if item["activity_id"] == activity)


def start_check(activity=ACTIVITY, headers=STUDENT):
    response = client.post(f"/activities/{activity}/knowledge-check", json={"confirm": True}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["lesson_check"]


def stored_items(micro_id):
    return json.loads(store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (micro_id,))["payload"])["items"]


def wrong(item):
    if item["type"] == "ordering":
        return list(reversed(item["answer"]))
    return {"single": "zz", "multiple": ["zz"], "numeric": "-987654"}[item["type"]]


def submit(micro_id, responses, key="k1", headers=STUDENT):
    return client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": responses, "idempotency_key": key}, headers=headers)


def evidence_rows():
    return store.db.query("SELECT * FROM skill_evidence WHERE user_id = ? AND task_id LIKE 'LESSON:%'", (str(STUDENT_ID),))


# 1. In progress
def test_marking_in_progress_needs_no_check():
    response = client.patch(f"/activities/{ACTIVITY}/progress", json={"status": "IN_PROGRESS", "progress_percent": 40, "actual_hours": 1.5}, headers=STUDENT)
    assert response.status_code == 200
    current = task()
    assert current["state"] == "IN_PROGRESS" and current["latest_check"] is None and current["progress"]["actual_hours"] == 1.5


# 2. Completed moves to the check
def test_completing_needs_confirmation_and_moves_to_pending_assessment():
    assert client.post(f"/activities/{ACTIVITY}/knowledge-check", json={"confirm": False}, headers=STUDENT).status_code == 422
    before = store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"]
    check = start_check()
    assert check["status"] == "PENDING" and check["kind"] == "LESSON_CHECK"
    assert task()["state"] == "PENDING_ASSESSMENT" and task()["progress"]["status"] == "COMPLETED"
    assert store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] == before


# 3. The check fits the activity
def test_the_check_matches_skill_level_and_objectives():
    activity = store.get_activity(ACTIVITY)
    check = start_check()
    items = stored_items(check["micro_id"])
    assert 3 <= len(items) <= 8
    assert {item["skill_code"] for item in items} == {"SQL"}
    assert all(int(item["level"]) <= int(activity["target_level"]) for item in items) and 1 in {int(item["level"]) for item in items}
    goal = _words(" ".join([activity["title"], activity["learning_outcome"], *activity["learning_objectives"]]))
    best = max(len(goal & _words(f"{item['topic']} {item['stem']}")) for item in store.question_items if item["skill_code"] == "SQL" and int(item["level"]) <= 2)
    assert max(len(goal & _words(f"{item['topic']} {item['stem']}")) for item in items) == best
    assert all("answer" not in item and "explanation" not in item for item in check["items"])


def test_reopening_returns_the_same_open_check():
    assert start_check()["micro_id"] == start_check()["micro_id"]


# 4 and 6. Full and correct: verified, evidence recorded
def test_passing_verifies_the_task_and_records_evidence_once():
    check = start_check()
    items = stored_items(check["micro_id"])
    result = submit(check["micro_id"], {item["item_id"]: item["answer"] for item in items}).json()
    assert result["status"] == "PASSED" and result["score"] == 100 and result["pass_threshold"] == LESSON_PASS_THRESHOLD
    assert result["counts"] == {"correct": len(items), "wrong": 0, "unanswered": 0}
    assert task()["state"] == "VERIFIED"
    assert result["current_level"] == 2 and store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] == 2
    assert len(evidence_rows()) == 1
    assert client.post(f"/activities/{ACTIVITY}/knowledge-check", json={"confirm": True}, headers=STUDENT).status_code == 409
    mastery = {item["skill_code"]: item for item in client.get("/me/skill-mastery", headers=STUDENT).json()["skills"]}
    assert mastery["SQL"]["latest_check"]["status"] == "PASSED"


# 5 and 11. Blanks score zero; an all-blank check is not graded
def test_blank_answers_never_count():
    check = start_check()
    items = stored_items(check["micro_id"])
    assert submit(check["micro_id"], {}).json()["status"] == "INCOMPLETE"
    assert task()["state"] == "PENDING_ASSESSMENT" and not evidence_rows()
    first = items[0]
    result = submit(check["micro_id"], {first["item_id"]: first["answer"]}, key="k2").json()
    assert result["counts"]["unanswered"] == len(items) - 1 and result["counts"]["correct"] == 1
    blanks = [entry for entry in result["item_results"] if not entry["answered"]]
    assert blanks and all(entry["credit"] == 0 for entry in blanks)
    assert result["status"] == "FAILED" and not evidence_rows()


# 7 and 11. Failing: needs review, no evidence, review material
def test_failing_needs_review_without_evidence():
    check = start_check()
    items = stored_items(check["micro_id"])
    result = submit(check["micro_id"], {item["item_id"]: wrong(item) for item in items}).json()
    assert result["status"] == "FAILED" and result["can_retry"] and result["review_resources"]
    assert result["weak_topics"] and result["counts"]["wrong"] == len(items)
    assert task()["state"] == "NEEDS_REVIEW" and not evidence_rows()
    assert store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] == 1


# 8 and 9. A retry keeps every earlier attempt
def test_retry_creates_a_new_attempt_and_keeps_the_old_one():
    first = start_check()
    items = stored_items(first["micro_id"])
    submit(first["micro_id"], {item["item_id"]: wrong(item) for item in items})
    # Audit A-03: an immediate retake is refused; after the wait a new attempt opens.
    assert client.post(f"/activities/{ACTIVITY}/knowledge-check", json={"confirm": True}, headers=STUDENT).status_code == 409
    later = utcnow() + timedelta(hours=RETRY_WAIT_HOURS, minutes=1)
    set_clock(lambda: later)
    try:
        second = start_check()
    finally:
        set_clock(None)
    assert second["micro_id"] != first["micro_id"] and second["attempt_no"] == 2
    assert task()["state"] == "NEEDS_REVIEW" and task()["open_check_id"] == second["micro_id"]
    assert client.get(f"/micro-tests/{first['micro_id']}", headers=STUDENT).json()["result"]["status"] == "FAILED"
    retry_items = stored_items(second["micro_id"])
    submit(second["micro_id"], {item["item_id"]: item["answer"] for item in retry_items}, key="k2")
    detail = client.get(f"/activities/{ACTIVITY}/detail", headers=STUDENT).json()
    assert [entry["status"] for entry in detail["checks"]] == ["PASSED", "FAILED"] and detail["state"] == "VERIFIED"


# 10. Per account
def test_results_belong_to_one_account():
    check = start_check()
    assert client.get(f"/micro-tests/{check['micro_id']}", headers=STUDENT_2).status_code == 404
    assert client.put(f"/micro-tests/{check['micro_id']}/draft", json={"responses": {}}, headers=STUDENT_2).status_code == 404
    items = stored_items(check["micro_id"])
    assert submit(check["micro_id"], {item["item_id"]: item["answer"] for item in items}, headers=STUDENT_2).status_code == 404
    assert client.post(f"/activities/{ACTIVITY}/knowledge-check", json={"confirm": True}, headers=STUDENT_2).status_code == 404
    assert client.get(f"/activities/{ACTIVITY}/detail", headers=STUDENT_2).status_code == 404


# 12. Resubmission is idempotent
def test_a_resubmission_records_no_second_evidence():
    check = start_check()
    answers = {item["item_id"]: item["answer"] for item in stored_items(check["micro_id"])}
    assert submit(check["micro_id"], answers).json()["status"] == "PASSED"
    assert submit(check["micro_id"], answers).json()["is_duplicate"] is True
    assert submit(check["micro_id"], answers, key="other").status_code == 409
    assert len(evidence_rows()) == 1


# Draft answers survive a reload but are never graded
def test_drafts_are_saved_validated_and_closed_after_submission():
    check = start_check()
    item = stored_items(check["micro_id"])[0]
    saved = client.put(f"/micro-tests/{check['micro_id']}/draft", json={"responses": {item["item_id"]: item["answer"], "unknown": "x"}}, headers=STUDENT)
    assert saved.status_code == 200 and saved.json()["answered"] == 1
    assert client.get(f"/micro-tests/{check['micro_id']}", headers=STUDENT).json()["draft"] == {item["item_id"]: item["answer"]}
    assert client.put(f"/micro-tests/{check['micro_id']}/draft", json={"responses": {item["item_id"]: {"bad": 1}}}, headers=STUDENT).status_code == 422
    submit(check["micro_id"], {item["item_id"]: item["answer"]})
    assert client.put(f"/micro-tests/{check['micro_id']}/draft", json={"responses": {}}, headers=STUDENT).status_code == 409


# 13. AI feedback never changes a result and fails loudly
def graded_check():
    check = start_check()
    items = stored_items(check["micro_id"])
    submit(check["micro_id"], {item["item_id"]: wrong(item) for item in items})
    return check["micro_id"]


def test_ai_feedback_reports_an_unavailable_service(monkeypatch):
    micro_id = graded_check()
    monkeypatch.setattr(gateway, "is_available", lambda: False)
    assert client.post(f"/micro-tests/{micro_id}/ai-feedback", headers=STUDENT).status_code == 503
    assert task()["state"] == "NEEDS_REVIEW"


def test_ai_feedback_reports_a_failed_call(monkeypatch):
    micro_id = graded_check()
    monkeypatch.setattr(gateway, "is_available", lambda: True)

    def broken(*args, **kwargs):
        raise GatewayError("TIMEOUT")
    monkeypatch.setattr(gateway, "structured", broken)
    assert client.post(f"/micro-tests/{micro_id}/ai-feedback", headers=STUDENT).status_code == 503
    assert client.get(f"/micro-tests/{micro_id}", headers=STUDENT).json()["result"]["status"] == "FAILED"


def test_ai_feedback_with_an_invented_number_is_discarded(monkeypatch):
    micro_id = graded_check()
    monkeypatch.setattr(gateway, "is_available", lambda: True)
    monkeypatch.setattr(gateway, "structured", lambda *args, **kwargs: {"summary": "Bạn đạt 97% bài này.", "strengths": [], "to_review": [], "next_steps": []})
    assert client.post(f"/micro-tests/{micro_id}/ai-feedback", headers=STUDENT).status_code == 502


def test_ai_feedback_is_kept_once_accepted(monkeypatch):
    micro_id = graded_check()
    calls = []
    monkeypatch.setattr(gateway, "is_available", lambda: True)

    def answer(*args, **kwargs):
        calls.append(args[1])
        return {"summary": "Hãy ôn lại phần lọc sau tổng hợp.", "strengths": [], "to_review": ["HAVING"], "next_steps": ["Làm lại bài kiểm tra."]}
    monkeypatch.setattr(gateway, "structured", answer)
    first = client.post(f"/micro-tests/{micro_id}/ai-feedback", headers=STUDENT)
    assert first.status_code == 200 and first.json()["to_review"] == ["HAVING"]
    assert client.post(f"/micro-tests/{micro_id}/ai-feedback", headers=STUDENT).json() == first.json() and len(calls) == 1
    assert all(set(question) == {"topic", "answered", "correct"} for question in calls[0]["facts"]["questions"])


def test_ai_feedback_needs_a_graded_check():
    check = start_check()
    assert client.post(f"/micro-tests/{check['micro_id']}/ai-feedback", headers=STUDENT).status_code == 409


# 14. The earlier roadmap behaviour still holds
def test_the_old_progress_api_still_completes_and_leaves_the_check_pending():
    response = client.patch(f"/activities/{ACTIVITY}/progress", json={"status": "COMPLETED"}, headers=STUDENT).json()
    # Roadmap 2.0: no review date until the completion check is passed.
    assert response["status"] == "COMPLETED" and response["checkin"] is None
    assert task()["state"] == "PENDING_ASSESSMENT" and task()["latest_check"] is None
    assert client.get("/me/learning-tasks", headers=STUDENT).json()["counts"]["PENDING_ASSESSMENT"] == 1


def test_review_mini_tests_keep_their_own_threshold():
    item = next(item for item in store.question_items if item["skill_code"] == "SQL" and item["type"] == "single")
    assert grade_micro([item], {item["item_id"]: item["answer"]})["passed"] is True
    assert PASS_THRESHOLD == 70.0 and grade_micro([item], {item["item_id"]: "zz"})["passed"] is False


def test_activities_outside_the_roadmap_are_refused():
    assert client.get("/activities/NOT_A_REAL_ACTIVITY/detail", headers=STUDENT).status_code == 404


def test_selection_needs_enough_questions():
    assert select_lesson_items({"activity_id": "X", "target_skill": "NO_SUCH_SKILL", "target_level": 2}, set()) == []
