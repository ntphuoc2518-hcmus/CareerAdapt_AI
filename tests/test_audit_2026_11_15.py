"""Regression tests for the faults found in the full-system audit of 2026-11-15 (v5.32.0)."""
import pytest

from backend.ai_service import tool_registry
from backend.ai_service.career_context import ToolContext
from backend.main import app
from backend.store import store
from v5_helpers import P, STUDENT, STUDENT_ID, client, complete_process, questions_of, to_exam


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield
    store.reset()


def exam_with(answers: dict[str, str]) -> dict:
    """Sit the exam giving every question of an answer type the same text; returns the review."""
    exam = to_exam()
    for question in questions_of(exam["attempt_id"]):
        text = answers.get(question["answer_type"], "")
        if text:
            assert client.put(f"{P}/exam/responses/{question['question_id']}", json={"text": text}, headers=STUDENT).status_code == 200
    assert client.post(f"{P}/exam/submit", json={}, headers=STUDENT).status_code == 200
    return client.get(f"{P}/exam/review", headers=STUDENT).json()


def levels() -> dict:
    return {code: item.get("level") for code, item in store.get_or_create_profile(STUDENT_ID).get("assessed_skills", {}).items()}


# --- F1: a server error on the final assessment ---

def test_starting_the_final_assessment_without_a_roadmap_is_refused_not_a_crash():
    response = client.post("/api/v1/me/final-assessment/start", headers=STUDENT)
    assert response.status_code == 409 and "lộ trình" in response.json()["error"]["message"]
    state = client.get("/api/v1/me/final-assessment", headers=STUDENT).json()
    assert state["eligible"] is False and state["can_start"] is False and state["attempts"] == []


# --- F2: code that only runs, a table dump, and "I do not know" earn nothing ---

def test_answers_that_only_run_or_say_nothing_score_zero():
    review = exam_with({"sql": "SELECT 1;", "python": "print('xin chao')", "text": "Em chưa rõ nội dung này nên trả lời đại."})
    assert review["score"] == 0 and review["passed"] is False
    assert [question["points_awarded"] for question in review["questions"]] == [0] * len(review["questions"])
    assert set(levels().values()) == {0}
    reasons = {case["actual"] for question in review["questions"] for case in question["cases"]}
    assert any("chưa đáp ứng yêu cầu nào" in reason for reason in reasons) and any("chưa biết" in reason for reason in reasons)


def test_printing_the_whole_table_is_not_a_correct_result():
    review = exam_with({"python": "import pandas as pd\ndf = pd.read_csv('orders.csv')\nprint(df)"})
    python = next(question for question in review["questions"] if question["skill_code"] == "PYTHON")
    result = next(case for case in python["cases"] if "in ra" in case["description"])
    assert result["passed"] is False
    assert levels()["PYTHON"] == 0


def test_a_correct_exam_still_passes_after_the_stricter_rules():
    complete_process(kind="good")
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["passed"] is True and all(question["points_awarded"] == question["max_points"] for question in review["questions"])


# --- F3: marking a lesson done is not progress ---

def test_a_self_marked_lesson_does_not_count_as_verified_progress():
    complete_process(kind="wrong")
    lesson = next(iter(store.roadmaps[STUDENT_ID]["activity_plan"]))
    for _ in range(3):
        marked = client.patch(f"/api/v1/activities/{lesson}/progress", json={"status": "COMPLETED", "progress_percent": 100}, headers=STUDENT)
        assert marked.status_code == 200
    roadmap = client.get("/api/v1/me/roadmap", headers=STUDENT).json()
    journey = client.get("/api/v1/me/journey", headers=STUDENT).json()
    assert roadmap["overall_progress_percent"] > 0  # what the learner marked
    assert roadmap["verified_progress_percent"] == journey["percent"] == 0
    assert roadmap["verified_activity_ids"] == [] and roadmap["lessons_verified"] == 0 and roadmap["lessons_total"] == journey["lessons_total"]
    assert set(levels().values()) == {0}
    # Repeating the same mark adds no log line.
    assert sum(1 for item in store.history_events(STUDENT_ID) if item["event"] == "UPDATE_PROGRESS") == 1


def test_the_assistant_reports_verified_progress_beside_the_self_marked_figure():
    complete_process(kind="wrong")
    lesson = next(iter(store.roadmaps[STUDENT_ID]["activity_plan"]))
    client.patch(f"/api/v1/activities/{lesson}/progress", json={"status": "COMPLETED", "progress_percent": 100}, headers=STUDENT)
    outcome = tool_registry.execute("get_my_learning_progress", {}, ToolContext(STUDENT_ID))
    assert outcome["data"]["verified_progress_percent"] == 0 and outcome["data"]["lessons_verified"] == 0 and outcome["data"]["overall_progress_percent"] > 0
    rows = {row["label"]: row["value"] for row in outcome["card"]["rows"]}
    assert rows["Bài học đã xác minh"] == f"0/{outcome['data']['lessons_total']}" and rows["Tự đánh dấu hoàn thành"] == "1"
    summary = tool_registry.execute("get_my_career_journey_summary", {}, ToolContext(STUDENT_ID))
    assert {row["label"]: row["value"] for row in summary["card"]["rows"]}["Tiến độ đã xác minh"] == "0%"


# --- F4: one error envelope everywhere ---

def test_an_oversized_form_field_gets_the_standard_error_envelope():
    response = client.post("/api/v1/jds/import", data={"text": "Yêu cầu SQL. " * 120000}, headers=STUDENT)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_400" and "quá lớn" in response.json()["error"]["message"]


def test_an_unknown_api_path_gets_the_standard_error_envelope():
    response = client.get("/api/v1/khong-co-duong-dan-nay", headers=STUDENT)
    assert response.status_code == 404 and response.json()["error"]["code"] == "HTTP_404"


# --- Access control sweep: every API route refuses a visitor without a session ---

PUBLIC = {("GET", "/api/v1/auth/csrf"), ("GET", "/api/v1/auth/password-policy"), ("GET", "/api/v1/careers"), ("GET", "/api/v1/careers/data-analyst/profiles"),
          ("GET", "/api/v1/careers/data-analyst/requirements"), ("GET", "/"), ("GET", "/api"), ("GET", "/app"), ("GET", "/gioi-thieu"), ("GET", "/health"), ("GET", "/index.html"), ("GET", "/login")}


def test_every_route_outside_the_public_list_needs_a_session():
    import re

    open_routes = []
    for path, item in app.openapi()["paths"].items():
        for method in (name.upper() for name in item if name in ("get", "post", "put", "patch", "delete")):
            if (method, path) in PUBLIC:
                continue
            response = client.request(method, re.sub(r"\{[^}]+\}", "x", path), json=None if method == "GET" else {})
            if response.status_code not in (401, 403):
                open_routes.append((response.status_code, method, path))
    assert open_routes == []


def test_a_learner_is_refused_on_every_admin_route():
    import re

    leaks = []
    for path, item in app.openapi()["paths"].items():
        if "admin" not in path:
            continue
        for method in (name.upper() for name in item if name in ("get", "post", "put", "patch", "delete")):
            response = client.request(method, re.sub(r"\{[^}]+\}", "x", path), json=None if method == "GET" else {}, headers=STUDENT)
            if response.status_code not in (403, 404):
                leaks.append((response.status_code, method, path))
    assert leaks == []
