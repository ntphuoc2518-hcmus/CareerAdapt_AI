"""Test Center: form assembly, item scoring, level estimation, evaluation and API flow."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.engine.test_engine import (
    assemble_form, build_evaluation, estimate_level, item_analysis, score_attempt, score_item, wilson_interval,
)
from backend.main import app
from backend.store import store

client = TestClient(app)
STUDENT = {"Authorization": "Bearer token_student_1"}
STUDENT_2 = {"Authorization": "Bearer token_student_2"}
ADMIN = {"Authorization": "Bearer token_admin"}


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()
    yield
    store.reset()


def _item(item_id):
    return store.get_question_item(item_id)


# --- Item scoring -----------------------------------------------------------

def test_single_choice_scoring():
    assert score_item(_item("SQL-001"), "b") == 1.0
    assert score_item(_item("SQL-001"), "a") == 0.0
    assert score_item(_item("SQL-001"), None) == 0.0


def test_multiple_choice_partial_credit_penalises_wrong_picks():
    item = _item("SQL-006")  # answer a, b, c
    assert score_item(item, ["a", "b", "c"]) == 1.0
    assert score_item(item, ["a", "b"]) == pytest.approx(2 / 3, abs=1e-3)
    assert score_item(item, ["a", "b", "c", "d"]) == pytest.approx(2 / 3, abs=1e-3)
    # Selecting every option cannot earn more than a careful partial answer.
    assert score_item(item, ["a", "b", "c", "d", "e"]) == pytest.approx(1 / 3, abs=1e-3)
    assert score_item(item, ["d", "e"]) == 0.0


@pytest.mark.parametrize("value,expected", [
    ("270000", 1.0), ("270.000", 1.0), ("270 000", 1.0), (270000, 1.0), ("27000", 0.0), ("abc", 0.0),
])
def test_numeric_accepts_vietnamese_formats(value, expected):
    assert score_item(_item("SQL-005"), value) == expected


def test_numeric_tolerance_and_decimal_comma():
    item = _item("COMM-003")  # -14.29 +/- 0.05
    assert score_item(item, "-14,29") == 1.0
    assert score_item(item, "-14.3") == 1.0
    assert score_item(item, "14.29") == 0.0
    assert score_item(_item("PY-003"), "2.33") == 1.0


def test_ordering_partial_credit():
    item = _item("SQL-007")
    key = item["answer"]
    assert score_item(item, key) == 1.0
    swapped = key[:]
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert 0 < score_item(item, swapped) < 1
    assert score_item(item, list(reversed(key))) == 0.0
    assert score_item(item, key[:-1]) == 0.0


# --- Assembly, levels, evaluation -------------------------------------------

def test_form_follows_blueprint_matrix_without_duplicates():
    blueprint = store.get_blueprint("DA_FULL_ASSESSMENT")
    form = assemble_form(blueprint, store.question_items, seed=7)
    ids = [entry["item_id"] for entry in form]
    assert len(ids) == len(set(ids)) == 23
    for skill, levels in blueprint["matrix"].items():
        for level, count in levels.items():
            assert sum(1 for i in ids if _item(i)["skill_code"] == skill and _item(i)["level"] == int(level)) == count


def test_form_rejects_insufficient_bank():
    blueprint = {"matrix": {"SQL": {"3": 10}}}
    with pytest.raises(ValueError):
        assemble_form(blueprint, store.question_items)


def test_level_ladder_stops_at_untested_or_failed_level():
    assert estimate_level({1: (2, 2), 2: (2, 3), 3: (0, 1)}) == (2, 3)
    assert estimate_level({1: (0, 2), 2: (3, 3)}) == (0, 2)
    assert estimate_level({1: (1, 1), 3: (1, 1)}) == (1, 3)


def test_wilson_interval_bounds():
    low, high = wilson_interval(5, 5)
    assert 0.5 < low < 1 and high == 1.0
    assert wilson_interval(0, 0) == (0.0, 1.0)


def _perfect_responses(items):
    return {i["item_id"]: {"value": i["answer"], "time_spent_seconds": 20} for i in items}


def test_perfect_attempt_scores_100_and_passes():
    blueprint = store.get_blueprint("DA_FULL_ASSESSMENT")
    items = [_item(e["item_id"]) for e in assemble_form(blueprint, store.question_items, seed=1)]
    score = score_attempt(items, _perfect_responses(items), store.skills, store.difficulty_points)
    assert score["composite_score"] == 100.0
    assert score["skills"]["SQL"]["estimated_level"] == 3
    evaluation = build_evaluation(score, blueprint, store.activities)
    assert evaluation["passed"] and evaluation["band"]["code"] == "PROFICIENT"
    assert evaluation["recommendations"] == []


def test_weak_core_skill_fails_even_with_high_composite():
    blueprint = store.get_blueprint("DA_FULL_ASSESSMENT")
    items = [_item(e["item_id"]) for e in assemble_form(blueprint, store.question_items, seed=2)]
    responses = _perfect_responses(items)
    for i in items:
        if i["skill_code"] == "DATA_QUALITY":
            responses.pop(i["item_id"])
    score = score_attempt(items, responses, store.skills, store.difficulty_points)
    evaluation = build_evaluation(score, blueprint, store.activities)
    assert score["composite_score"] >= 60
    assert not evaluation["passed"]
    assert any("cốt lõi" in reason for reason in evaluation["fail_reasons"])
    rec = next(r for r in evaluation["recommendations"] if r["skill_code"] == "DATA_QUALITY")
    assert rec["priority"] == "HIGH" and rec["activities"]


def test_item_analysis_flags_after_enough_data():
    attempts = []
    for k in range(6):
        attempts.append({"score": {"items": [
            {"item_id": "SQL-001", "credit": 1.0},
            {"item_id": "SQL-002", "credit": 1.0 if k % 2 else 0.0},
            {"item_id": "SQL-003", "credit": 1.0 if k > 2 else 0.0},
        ]}})
    report = {row["item_id"]: row for row in item_analysis(store.question_items, attempts)}
    assert report["SQL-001"]["p_value"] == 1.0 and "Quá dễ" in report["SQL-001"]["flags"]
    assert report["SQL-003"]["exposures"] == 6
    assert report["SQL-009"]["exposures"] == 0


# --- API flow ---------------------------------------------------------------

def _answer_all(attempt, correct=True):
    for item in attempt["items"]:
        key = _item(item["item_id"])["answer"]
        value = key if correct else None
        resp = client.put(f"/api/v1/tests/attempts/{attempt['attempt_id']}/responses/{item['item_id']}",
                          json={"value": value, "time_spent_seconds": 12}, headers=STUDENT)
        assert resp.status_code == 200, resp.text


def test_full_attempt_lifecycle_hides_key_until_submit():
    resp = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT)
    assert resp.status_code == 201
    attempt = resp.json()
    assert attempt["total_items"] == 6 and attempt["remaining_seconds"] > 0
    assert all("answer" not in item and "explanation" not in item for item in attempt["items"])

    # Starting again resumes instead of opening a second attempt.
    again = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    assert again["resumed"] and again["attempt_id"] == attempt["attempt_id"]

    # Another learner cannot see it.
    assert client.get(f"/api/v1/tests/attempts/{attempt['attempt_id']}", headers=STUDENT_2).status_code == 404
    assert client.get(f"/api/v1/tests/attempts/{attempt['attempt_id']}/report", headers=STUDENT).status_code == 409

    _answer_all(attempt)
    client.post(f"/api/v1/tests/attempts/{attempt['attempt_id']}/events", json={"type": "focus_lost"}, headers=STUDENT)
    report = client.post(f"/api/v1/tests/attempts/{attempt['attempt_id']}/submit", headers=STUDENT).json()
    assert report["composite_score"] == 100.0 and report["passed"]
    assert report["certificate"]["certificate_id"].startswith("CA-")
    assert all("answer" in row for row in report["review"])
    assert report["integrity"]["focus_losses"] == 1

    late = client.put(f"/api/v1/tests/attempts/{attempt['attempt_id']}/responses/{attempt['items'][0]['item_id']}",
                      json={"value": None}, headers=STUDENT)
    assert late.status_code == 409

    history = client.get("/api/v1/tests/attempts", headers=STUDENT).json()["attempts"]
    assert history[0]["attempt_id"] == attempt["attempt_id"]


def test_invalid_option_rejected():
    attempt = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    single = next(i for i in attempt["items"] if i["type"] == "single")
    resp = client.put(f"/api/v1/tests/attempts/{attempt['attempt_id']}/responses/{single['item_id']}",
                      json={"value": "zzz"}, headers=STUDENT)
    assert resp.status_code == 422


def test_expired_attempt_auto_submits():
    attempt = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    stored = store.test_attempts[attempt["attempt_id"]]
    stored["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    state = client.get(f"/api/v1/tests/attempts/{attempt['attempt_id']}", headers=STUDENT).json()
    assert state["status"] == "SUBMITTED" and state["auto_submitted"]
    report = client.get(f"/api/v1/tests/attempts/{attempt['attempt_id']}/report", headers=STUDENT).json()
    assert report["composite_score"] == 0 and not report["passed"]


def test_attempt_limit_per_24h():
    for _ in range(5):
        attempt = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
        client.post(f"/api/v1/tests/attempts/{attempt['attempt_id']}/submit", headers=STUDENT)
    resp = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT)
    assert resp.status_code == 429


def test_practice_mode_gives_immediate_feedback_and_locks_item():
    attempt = client.post("/api/v1/tests/attempts", json={"blueprint_id": "DA_PRACTICE"}, headers=STUDENT).json()
    assert attempt["remaining_seconds"] is None
    item = attempt["items"][0]
    url = f"/api/v1/tests/attempts/{attempt['attempt_id']}/responses/{item['item_id']}"
    resp = client.put(url, json={"value": _item(item["item_id"])["answer"], "check": True}, headers=STUDENT).json()
    assert resp["feedback"]["correct"] and resp["feedback"]["explanation"]
    assert client.put(url, json={"value": None}, headers=STUDENT).status_code == 409


def test_second_attempt_reports_progress_comparison():
    first = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    client.post(f"/api/v1/tests/attempts/{first['attempt_id']}/submit", headers=STUDENT)
    second = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    _answer_all(second)
    report = client.post(f"/api/v1/tests/attempts/{second['attempt_id']}/submit", headers=STUDENT).json()
    assert report["evaluation"]["comparison"]["composite_delta"] == 100.0


def test_admin_item_crud_analysis_and_export():
    assert client.get("/api/v1/admin/tests/items", headers=STUDENT).status_code == 403
    new_item = {"item_id": "SQL-100", "skill_code": "SQL", "level": 1, "type": "single", "topic": "SELECT",
                "stem": "Lệnh nào lấy dữ liệu?", "options": [{"id": "a", "text": "SELECT"}, {"id": "b", "text": "DROP"}],
                "answer": "a", "explanation": "SELECT đọc dữ liệu."}
    assert client.post("/api/v1/admin/tests/items", json=new_item, headers=ADMIN).status_code == 201
    assert client.post("/api/v1/admin/tests/items", json=new_item, headers=ADMIN).status_code == 409
    bad = {**new_item, "item_id": "SQL-101", "answer": "z"}
    assert client.post("/api/v1/admin/tests/items", json=bad, headers=ADMIN).status_code == 422
    retired = {**new_item, "status": "RETIRED"}
    assert client.put("/api/v1/admin/tests/items/SQL-100", json=retired, headers=ADMIN).json()["status"] == "RETIRED"

    attempt = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    assert "SQL-100" not in [i["item_id"] for i in attempt["items"]]
    _answer_all(attempt)
    client.post(f"/api/v1/tests/attempts/{attempt['attempt_id']}/submit", headers=STUDENT)

    results = client.get("/api/v1/admin/tests/results", headers=ADMIN).json()
    assert results["statistics"]["count"] == 1 and results["statistics"]["pass_rate"] == 100.0
    analysis = client.get("/api/v1/admin/tests/item-analysis", headers=ADMIN).json()
    assert analysis["attempts_analyzed"] == 1
    csv_resp = client.get("/api/v1/admin/tests/results.csv", headers=ADMIN)
    assert csv_resp.status_code == 200 and "composite_score" in csv_resp.text


def test_gdpr_delete_removes_attempts():
    client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT)
    assert store.test_attempts
    client.delete("/me/data", headers=STUDENT)
    assert not store.user_test_attempts(__import__("uuid").UUID("11111111-1111-1111-1111-111111111111"))
