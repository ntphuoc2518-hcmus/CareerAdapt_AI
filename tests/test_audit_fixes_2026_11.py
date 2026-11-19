"""Regression tests for the fixes from the 2026-11-12 audit (AUDIT_REPORT.md): A-01 to A-05, B-01, B-06, C-03 and JD matching."""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timedelta, timezone

import pytest

from backend import config
from backend.api import auth_routes
from backend.clock import set_clock
from backend.engine.exam_grader import BANK, evaluate_question, plan_questions, verify_exam
from backend.lesson_checks import QUIZ_LEVEL_CEILING, RETRY_WAIT_HOURS
from backend.store import store
from backend.targeting import default_requirements
from v5_helpers import FACTS, GOOD, P, STUDENT, STUDENT_ID, answer_all, client, good_answer, questions_of, set_default_jd, set_skills, step


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    set_clock(None)
    yield
    set_clock(None)


def question(item_id: str, variant: str = "A", target_level: int = 2) -> dict:
    item = next(entry for entry in BANK["items"] if entry["item_id"] == item_id)
    return {**{key: item[key] for key in ("skill_code", "tier", "topic", "prompt", "answer_type", "minutes", "max_chars", "cases")},
            "question_id": "Q1", "label": "Bài 1", "item_id": f"{item_id}-{variant}", "dataset": BANK["datasets"][variant], "gates": item.get("gates", []),
            "placeholder": "", "declared_level": None, "weight": 1.0, "target_level": target_level}


def level_for(item_id: str, answer: str, variant: str = "A") -> int:
    q = question(item_id, variant)
    return verify_exam([q], {"Q1": answer})["skill_results"][q["skill_code"]]["level"]


# --- A-01: the JD level sets the difficulty, never the declared level ---

def test_declaring_nothing_and_answering_everything_right_proves_the_jd_level():
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    assert set_skills({"SQL": 0}).status_code == 200
    assert set_default_jd().status_code == 200
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    answer_all(exam)
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    skills = client.get(f"{P}/exam/review", headers=STUDENT).json()["conclusion"]["skills"]
    assert skills and all(item["verified_level"] >= item["target_level"] for item in skills)


def test_overclaiming_does_not_raise_the_difficulty():
    requirements = {code: {"weight": 0.2, "target_level": 1} for code in ("SQL", "PYTHON", "DATA_VIZ", "DATA_QUALITY", "WRITTEN_COMM")}
    assert all(item["tier"] == 1 for item in plan_questions(requirements, {code: 3 for code in requirements}, set(), 5))


# --- A-02: naming concepts without an explanation or computed data proves at most level 1 ---

@pytest.mark.parametrize("item_id,answer", [
    ("STAT-3", "{a1}. {a2}. Mẫu nhỏ. t-test. Ngẫu nhiên, nhóm đối chứng."),
    ("WC-3", "Tóm tắt. Phát hiện. Khuyến nghị: team phụ trách trong tuần. Giới hạn: mẫu nhỏ."),
    ("WC-2", "Đề xuất. Giới hạn. Chưa thể kết luận."),
    ("VIZ-3", "Biểu đồ đường. Biểu đồ cột. Cắt trục."),
    ("DQ-3", "unique. not null. check > 0. validation."),
])
def test_keyword_answers_cannot_prove_a_high_level(item_id, answer):
    assert level_for(item_id, answer.format(**FACTS["A"])) <= 1


def test_a_written_answer_without_any_correct_figure_is_capped_at_level_1():
    # Every concept explained in full sentences, but no figure computed: it shows no analysis.
    text = ("Tóm tắt: doanh thu tháng sau giảm so với tháng trước theo bảng dữ liệu đã làm sạch.\n"
            "Phát hiện: vùng có doanh thu cao nhất là vùng dẫn đầu trong bảng.\n"
            "Khuyến nghị: nhóm kinh doanh phụ trách rà soát đơn trong tuần tới.\n"
            "Giới hạn: dữ liệu chỉ có hai tháng nên chưa thể kết luận nguyên nhân.")
    q = question("WC-3")
    result = verify_exam([q], {"Q1": text})["skill_results"]["WRITTEN_COMM"]
    assert result["level"] <= 1 and result["capped_by_missing_data"] is True


@pytest.mark.parametrize("variant", sorted(BANK["datasets"]))
def test_reference_answers_still_prove_the_hard_tier(variant):
    for item_id in ("STAT-3", "WC-3", "VIZ-3", "DQ-3"):
        assert level_for(item_id, GOOD[item_id](FACTS[variant]), variant) == 3


# --- A-04: four datasets, so two attempts rarely share the same numbers ---

def test_the_bank_has_four_datasets_with_different_answers():
    assert sorted(BANK["datasets"]) == ["A", "B", "C", "D"]
    assert len({FACTS[variant]["clean"] for variant in BANK["datasets"]}) == 4
    seen: set[str] = set()
    requirements = {"SQL": {"weight": 1, "target_level": 2}}
    for seed in range(4):
        picked = plan_questions(requirements, {}, seen, seed)[0]["item_id"]
        assert picked not in seen
        seen.add(picked)


def test_an_answer_from_one_dataset_fails_on_another():
    outcomes, _ = evaluate_question(question("DQ-3", "C"), GOOD["DQ-3"](FACTS["A"]))
    assert not all(item["passed"] for item in outcomes.values())


# --- A-03: closed questions confirm at most level 2, and a failed check waits before a retake ---

def _roadmap_with_target(levels: dict, sql_target: int):
    requirements = default_requirements()
    requirements["SQL"] = {**requirements["SQL"], "target_level": sql_target}
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["target_jd"] = {"source_type": "DEFAULT", "name": "Kiểm thử", "jd_id": "TEST", "jd_version": 1, "config_id": "DEFAULT", "requirements_by_skill": requirements, "additional_requirements": []}
    profile["assessed_skills"] = {code: {"level": level} for code, level in levels.items()}
    assert client.post("/roadmaps", headers=STUDENT).status_code in (200, 201)


def _take(activity: str, correct: bool, key: str) -> dict:
    response = client.post(f"/activities/{activity}/knowledge-check", json={"confirm": True}, headers=STUDENT)
    assert response.status_code == 200, response.text
    micro = response.json()["lesson_check"]["micro_id"]
    items = json.loads(store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (micro,))["payload"])["items"]
    wrong = {"single": "zz", "multiple": ["zz"], "numeric": -987654}
    answers = {item["item_id"]: item["answer"] if correct else (list(reversed(item["answer"])) if item["type"] == "ordering" else wrong[item["type"]]) for item in items}
    return client.post(f"/micro-tests/{micro}/submissions", json={"responses": answers, "idempotency_key": key}, headers=STUDENT).json()


def test_a_quiz_cannot_confirm_level_3_but_completes_the_lesson():
    _roadmap_with_target({"SQL": 2, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2}, sql_target=3)
    result = _take("ACT_SQL_02", True, "q3")
    assert result["status"] == "PASSED" and result["current_level"] == QUIZ_LEVEL_CEILING
    state = client.get("/me/journey/lessons/ACT_SQL_02", headers=STUDENT).json()["state"]
    assert state["learning_state"] == "COMPLETED" and state["confirm_level"] == 2
    sql = next(item for item in client.get("/me/gap", headers=STUDENT).json()["skill_evaluations"] if item["skill_code"] == "SQL")
    assert sql["current_level"] == 2 and sql["gap"] == 1  # level 3 waits for practical evidence


def test_a_failed_check_cannot_be_retaken_at_once():
    _roadmap_with_target({"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2}, sql_target=2)
    now = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)
    set_clock(lambda: now)
    assert _take("ACT_SQL_01", False, "f1")["status"] == "FAILED"
    refused = client.post("/activities/ACT_SQL_01/knowledge-check", json={"confirm": True}, headers=STUDENT)
    assert refused.status_code == 409 and "giờ" in refused.json()["error"]["message"]
    assert client.get("/me/journey/lessons/ACT_SQL_01", headers=STUDENT).json()["state"]["retry_at"]
    later = now + timedelta(hours=RETRY_WAIT_HOURS, minutes=1)
    set_clock(lambda: later)
    assert _take("ACT_SQL_01", True, "f2")["status"] == "PASSED"


# --- A-05: changing the goal keeps verified levels ---

def _completed_process():
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    set_skills()
    set_default_jd()
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    for q in questions_of(exam["attempt_id"]):
        text = good_answer(q["item_id"]) if q["skill_code"] != "SQL" else "SELECT 1;"
        client.put(f"{P}/exam/responses/{q['question_id']}", json={"text": text}, headers=STUDENT)
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    client.post(f"{P}/result/confirm", headers=STUDENT)
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 6, "timeline_weeks": 8}, headers=STUDENT).status_code == 200


def test_changing_the_goal_keeps_levels_and_skips_the_exam():
    _completed_process()
    before = {code: item["level"] for code, item in store.get_or_create_profile(STUDENT_ID)["assessed_skills"].items()}
    assert client.post(f"{P}/change-goal", json={"confirm": False}, headers=STUDENT).status_code == 422
    changed = client.post(f"{P}/change-goal", json={"confirm": True}, headers=STUDENT)
    assert changed.status_code == 200 and step() == "JD" and changed.json()["run"]["goal_change"] is True
    requirements = default_requirements()
    requirements["SQL"] = {**requirements["SQL"], "target_level": 3}
    from tests_jd import confirm_two_skill_jd
    assert confirm_two_skill_jd(STUDENT) == 200
    assert step() == "ROADMAP"
    after = {code: item["level"] for code, item in store.get_or_create_profile(STUDENT_ID)["assessed_skills"].items()}
    assert after == before
    assert client.get(f"{P}/exam/review", headers=STUDENT).status_code == 200  # the old exam stays
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 6, "timeline_weeks": 8}, headers=STUDENT).status_code == 200
    state = client.get(f"{P}/state", headers=STUDENT).json()
    assert state["run"]["status"] == "COMPLETED" and state["run"]["goal_changes"] == 1 and state["archived_runs"] == 0
    events = [row["event"] for row in store.db.query("SELECT event FROM history_events WHERE user_id = ?", (str(STUDENT_ID),))]
    assert "GOAL_CHANGED" in events


def test_the_goal_cannot_change_before_the_exam_result():
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    assert client.post(f"{P}/change-goal", json={"confirm": True}, headers=STUDENT).status_code == 409


# --- B-01: late weeks ---

def test_a_week_past_its_end_with_open_lessons_is_reported_late():
    _roadmap_with_target({"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2}, sql_target=2)
    journey = client.get("/me/journey", headers=STUDENT).json()
    assert journey["behind"] is None and all(week["overdue_days"] == 0 for week in journey["weeks"])
    end = datetime.fromisoformat(journey["weeks"][0]["end_date"]).replace(tzinfo=timezone.utc)
    later = end + timedelta(days=4, hours=12)
    set_clock(lambda: later)
    journey = client.get("/me/journey", headers=STUDENT).json()
    assert journey["weeks"][0]["overdue_days"] >= 3 and journey["behind"]["weeks"] >= 1
    replanned = client.post("/me/journey/replan", headers=STUDENT).json()
    assert replanned["changed"] is True
    assert client.get("/me/journey", headers=STUDENT).json()["behind"] is None


# --- JD matching ---

def test_jd_matching_agrees_with_the_gap_page_for_the_current_target():
    assert client.get("/api/v1/me/jd-matches", headers=STUDENT).json()["has_evidence"] is False
    _completed_process()
    data = client.get("/api/v1/me/jd-matches", headers=STUDENT).json()
    assert data["has_evidence"] and len(data["items"]) >= 2
    current = next(item for item in data["items"] if item["is_current"])
    gap = client.get("/me/gap", headers=STUDENT).json()
    assert current["readiness"] == gap["readiness"] and current["coverage"] == gap["coverage"]
    assert "user_id" not in json.dumps(data)


# --- B-06 and C-03 ---

def _forgot(monkeypatch, host: str):
    from v4_helpers import client as plain
    sent = []
    monkeypatch.setattr(auth_routes, "send_password_reset", lambda email, name, link, language="vi": sent.append(link))
    email = "reset-audit@example.com"
    plain.get("/api/v1/auth/csrf")
    csrf = plain.cookies.get("careeradapt_csrf")
    headers = {"origin": f"http://{host}", "x-csrf-token": csrf, "host": host}
    plain.post("/api/v1/auth/register", json={"email": email, "full_name": "Reset Audit", "password": "Lantern#Pass2026", "confirm_password": "Lantern#Pass2026"}, headers=headers)
    plain.post("/api/v1/auth/password/forgot", json={"email": email}, headers=headers)
    return sent


def test_reset_links_use_the_configured_address_not_the_host_header(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "https://careeradapt.example.vn")
    sent = _forgot(monkeypatch, "evil.example")
    assert sent and all(link.startswith("https://careeradapt.example.vn/login#reset=") for link in sent)


def test_production_without_a_public_address_sends_no_link(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "")
    monkeypatch.setenv("CAREERADAPT_ENV", "production")
    assert auth_routes.public_base_url(type("R", (), {"base_url": "http://evil.example/"})()) is None


def test_every_operation_is_documented_once():
    from backend.main import app
    app.openapi_schema = None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        spec = app.openapi()
    assert all(path.startswith(("/api/", "/health", "/app", "/index.html", "/gioi-thieu", "/login", "/")) for path in spec["paths"])
    assert not any(path.startswith(("/me/", "/jds/")) for path in spec["paths"])
