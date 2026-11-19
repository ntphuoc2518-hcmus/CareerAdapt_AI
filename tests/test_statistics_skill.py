"""The optional Statistics skill (v5.14): measured only when a JD asks for it."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.api.jds import _measurable_skills
from backend.catalog import list_resources
from backend.engine.exam_grader import BANK, plan_questions
from backend.engine.jd_parser import MAPPING, parse_job_description
from backend.lesson_checks import select_lesson_items
from backend.store import store
from backend.targeting import default_requirements, resolve_target, skills_for_target
from v5_helpers import FACTS, GOOD, P, STUDENT, client, questions_of, set_skills

CODE = "STATISTICS"
DATA = Path(__file__).resolve().parents[1] / "data"
JD_WITH_STATISTICS = """Data Analyst Intern
Mô tả: phân tích dữ liệu bán hàng và hỗ trợ ra quyết định.
Yêu cầu:
- Thành thạo SQL để truy vấn dữ liệu
- Làm sạch dữ liệu và kiểm tra chất lượng dữ liệu
- Có kiến thức thống kê và A/B testing
- Trực quan hóa bằng biểu đồ, dashboard
- Viết báo cáo kết quả phân tích
"""


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    yield


def skill():
    return store.get_skill(CODE)


def test_the_skill_has_a_full_rubric_and_is_optional():
    assert skill()["weight"] == 0 and skill()["assessed_by"] == "EXAM" and skill()["source_reference"]
    assert set(skill()["rubric_summary"]) == {"0", "1", "2", "3"} and all(skill()["rubric_summary"].values())
    # The default framework still weighs five skills that sum to 1.
    weighted = [item for item in store.skills if item["weight"] > 0]
    assert len(weighted) == 5 and abs(sum(item["weight"] for item in weighted) - 1.0) < 1e-9


def test_the_default_target_does_not_ask_for_statistics():
    target = resolve_target(store.get_or_create_profile(next(iter(store.profiles), None) or __import__("uuid").uuid4()))
    assert CODE not in {item["skill_code"] for item in skills_for_target(target)}
    questions = plan_questions(default_requirements(), {}, set(), seed=1)
    assert len(questions) == 5 and CODE not in {question["skill_code"] for question in questions}


def test_a_jd_that_mentions_statistics_maps_to_the_skill_not_to_the_unmeasured_list():
    parsed = parse_job_description(JD_WITH_STATISTICS)
    assert CODE in {item["skill_code"] for item in parsed["requirements"] if item.get("in_catalog")}
    assert not any("thống kê" in (item.get("label") or "").lower() for item in parsed["requirements"] if not item.get("in_catalog"))
    assert all("statistics" not in group["terms"] for group in MAPPING["unmeasured"])
    assert CODE in _measurable_skills()


def test_without_the_exam_flag_the_skill_is_not_a_verified_criterion():
    skill().pop("assessed_by")
    assert CODE not in _measurable_skills()


def test_the_exam_asks_one_statistics_question_when_the_jd_requires_it():
    requirements = {**default_requirements(), CODE: {"target_level": 2, "weight": 0.15, "requirement_type": "REQUIRED"}}
    # Audit A-01: whatever the learner declares, the question is at the JD's level (2).
    for declared in (None, 2, 3):
        questions = plan_questions(requirements, {CODE: declared} if declared is not None else {}, set(), seed=3)
        mine = [question for question in questions if question["skill_code"] == CODE]
        assert len(questions) == 6 and len(mine) == 1 and mine[0]["tier"] == 2
        assert abs(sum(question["weight"] for question in questions) - 1.0) < 1e-9


def test_the_whole_process_measures_statistics_from_a_jd_and_plans_its_modules():
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    assert set_skills({"SQL": 2, "DATA_QUALITY": 1, "PYTHON": 0, "DATA_VIZ": 2, "WRITTEN_COMM": 2, CODE: 1}).status_code == 200
    imported = client.post("/jds/import", data={"text": JD_WITH_STATISTICS, "title": "Data Analyst Intern"}, headers=STUDENT)
    assert imported.status_code in (200, 201), imported.text
    jd = imported.json()
    confirmed = client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": jd.get("jd_version", 1), "decisions": []}, headers=STUDENT)
    assert confirmed.status_code == 200, confirmed.text
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    questions = questions_of(exam["attempt_id"])
    mine = next(question for question in questions if question["skill_code"] == CODE)
    assert mine["item_id"].startswith("STAT-1-")
    # A correct Statistics answer, everything else blank.
    variant = mine["item_id"].rsplit("-", 1)[1]
    assert client.put(f"{P}/exam/responses/{mine['question_id']}", json={"text": GOOD["STAT-1"](FACTS[variant])}, headers=STUDENT).status_code == 200
    assert client.post(f"{P}/exam/submit", json={}, headers=STUDENT).status_code == 200
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    verdict = next(item for item in review["conclusion"]["skills"] if item["skill_code"] == CODE)
    assert verdict["percent"] == 100 and verdict["verified_level"] == 1
    assert all(item["verified_level"] == 0 for item in review["conclusion"]["skills"] if item["skill_code"] != CODE)
    assert client.post(f"{P}/result/confirm", headers=STUDENT).status_code == 200
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 8, "timeline_weeks": 12}, headers=STUDENT).status_code == 200
    gap = client.get("/api/v1/me/gap", headers=STUDENT).json()
    assert CODE in {item["skill_code"] for item in gap["skill_evaluations"]}
    roadmap = client.get("/api/v1/me/roadmap", headers=STUDENT).json()
    unscheduled = roadmap["schedule"]["unscheduled_activities"]
    assert not any("thống kê" in item["title"].lower() and item["kind"] == "JD_REQUIREMENT" for item in unscheduled)


def test_learning_modules_and_knowledge_checks_exist_for_every_level():
    usable = {item["resource_id"] for item in list_resources(store.db)}
    modules = [activity for activity in store.activities if activity["target_skill"] == CODE]
    assert sorted(activity["target_level"] for activity in modules) == [1, 2, 3]
    for activity in modules:
        assert len([rid for rid in activity["resource_ids"] if rid in usable]) >= 2, activity["activity_id"]
        items = select_lesson_items(activity, set(), seed=1)
        assert items and {item["skill_code"] for item in items} == {CODE}
        assert max(int(item["level"]) for item in items) == activity["target_level"]
    bank = json.loads((DATA / "question_bank_v1.json").read_text(encoding="utf-8"))
    assert any(blueprint["blueprint_id"] == f"SKILL_CHECK_{CODE}" for blueprint in bank["blueprints"])


def test_the_quick_check_blueprint_can_be_taken():
    started = client.post("/api/v1/tests/attempts", json={"blueprint_id": f"SKILL_CHECK_{CODE}"}, headers=STUDENT)
    assert started.status_code in (200, 201), started.text
    assert len(started.json()["items"]) == 6


def test_every_statistics_exam_tier_has_both_variants():
    tiers = sorted(item["tier"] for item in BANK["items"] if item["skill_code"] == CODE)
    # Audit A-04: four datasets (A-D) since bank EX-DA-1.3.
    assert tiers == [1, 2, 3] and len(BANK["datasets"]) == 4
