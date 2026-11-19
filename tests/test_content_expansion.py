"""Content added on 2026-11-11: more resources, questions, self-study links for unmeasured JD requirements, market knowledge."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from backend import supplementary
from backend.ai_service import knowledge
from backend.catalog import list_resources
from backend.engine.roadmap_planner import plan_items
from backend.store import store
from v5_helpers import P, STUDENT, answer_all, client, set_skills

DATA = Path(__file__).resolve().parents[1] / "data"
RESOURCES = json.loads((DATA / "learning_resources_v4.json").read_text(encoding="utf-8"))["resources"]
ACTIVITIES = json.loads((DATA / "activities_v1.json").read_text(encoding="utf-8"))
BANK = json.loads((DATA / "question_bank_v1.json").read_text(encoding="utf-8"))
TOPICS = json.loads((DATA / "supplementary_topics_v1.json").read_text(encoding="utf-8"))["topics"]


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    yield


def test_every_resource_is_complete_and_points_to_one_checked_link():
    assert len({item["resource_id"] for item in RESOURCES}) == len(RESOURCES)
    assert len({item["url"] for item in RESOURCES}) == len(RESOURCES)
    skills = {skill["skill_code"] for skill in store.skills}
    for item in RESOURCES:
        assert item["url"].startswith(("https://", "/guides/")), item["resource_id"]
        assert item["title"] and item["provider"] and item["learning_outcome"] and item["last_checked_at"], item["resource_id"]
        assert set(item["skill_ids"]) <= skills
        # A resource is tied to a measured skill or to a named self-study topic, never to nothing.
        assert item["skill_ids"] or item.get("topic"), item["resource_id"]


def test_every_learning_activity_has_at_least_two_usable_resources():
    usable = {item["resource_id"] for item in list_resources(store.db)}
    for activity in ACTIVITIES:
        attached = [rid for rid in activity["resource_ids"] if rid in usable]
        assert len(attached) >= 2, activity["activity_id"]
        assert len(attached) == len(activity["resource_ids"]), activity["activity_id"]


def test_no_activity_is_left_off_a_plan_for_lack_of_resources():
    evaluation = {"skill_evaluations": [
        {"skill_code": skill["skill_code"], "skill_name": skill["skill_name"], "status": "ASSESSED", "gap": 3, "current_level": 0, "target_level": 3, "weight": skill["weight"], "priority_score": 1, "is_core": skill.get("is_core")}
        for skill in store.skills]}
    plan = plan_items(evaluation, store.activities, store.tasks, list_resources(store.db), set(), [])
    assert {item["activity_id"] for item in plan["items"]} == {activity["activity_id"] for activity in ACTIVITIES}
    assert [item for item in plan["excluded"] if item["reason_code"] == "NO_APPROVED_RESOURCE"] == []


def test_the_question_bank_has_valid_answers_and_enough_items_per_level():
    items = BANK["items"]
    assert len({item["item_id"] for item in items}) == len(items) and len({item["stem"] for item in items}) == len(items)
    per_level = Counter((item["skill_code"], item["level"]) for item in items)
    assert all(per_level[(skill["skill_code"], level)] >= 6 for skill in store.skills for level in (1, 2, 3))
    for item in items:
        assert item["explanation"] and item["topic"], item["item_id"]
        if item["type"] == "numeric":
            assert isinstance(item["answer"], (int, float)) and item.get("tolerance") is not None, item["item_id"]
            continue
        keys = [option["id"] for option in item["options"]]
        assert len(set(keys)) == len(keys) >= 3, item["item_id"]
        answers = item["answer"] if isinstance(item["answer"], list) else [item["answer"]]
        assert set(answers) <= set(keys) and answers, item["item_id"]
        if item["type"] == "single":
            assert isinstance(item["answer"], str)
        if item["type"] == "multiple":
            assert 1 < len(answers) < len(keys), item["item_id"]
        if item["type"] == "ordering":
            assert sorted(answers) == sorted(keys), item["item_id"]


def test_new_questions_do_not_repeat_the_career_adapt_exam():
    for item in BANK["items"]:
        assert not knowledge.contains_exam_content("x") and item["stem"]
    exam = json.loads((DATA / "exam_items_v5.json").read_text(encoding="utf-8"))
    prompts = {entry.get("prompt") for entry in exam["items"]}
    assert not prompts & {item["stem"] for item in BANK["items"]}


def test_supplementary_topics_only_name_resources_that_exist():
    ids = {item["resource_id"] for item in RESOURCES}
    for topic in TOPICS:
        assert topic["resource_ids"] and set(topic["resource_ids"]) <= ids, topic["label"]


def test_an_unmeasured_jd_requirement_gets_self_study_links_and_others_get_none():
    usable = list_resources(store.db)
    excel = supplementary.resources_for_requirement("Excel hoặc Google Sheets", usable)
    assert excel and all(item["url"].startswith("https://") for item in excel) and len(excel) <= supplementary.MAX_LINKS
    assert supplementary.resources_for_requirement("Tiếng Anh đọc hiểu tài liệu là lợi thế", usable)
    assert supplementary.resources_for_requirement("Một số vị trí yêu cầu kinh nghiệm nhiều năm", usable) == []
    # A resource that is hidden or has a dead link is not offered.
    assert supplementary.resources_for_requirement("Excel", [item for item in usable if not item["resource_id"].startswith("RES_X_")]) == []


def test_the_roadmap_shows_self_study_links_only_on_jd_requirements_and_schedules_none_of_them():
    # A library JD that lists requirements the catalog cannot measure (Excel, Power BI, English).
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    assert set_skills().status_code == 200
    assert client.post("/me/target-jd", json={"jd_id": "VN_ENTRY_ANALYST", "jd_version": 1}, headers=STUDENT).status_code == 200
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    answer_all(exam, "wrong")
    assert client.post(f"{P}/exam/submit", json={}, headers=STUDENT).status_code == 200
    assert client.post(f"{P}/result/confirm", headers=STUDENT).status_code == 200
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 6, "timeline_weeks": 8}, headers=STUDENT).status_code == 200
    roadmap = client.get("/api/v1/me/roadmap", headers=STUDENT).json()
    unscheduled = roadmap["schedule"]["unscheduled_activities"]
    extra = [item for item in unscheduled if item["kind"] == "JD_REQUIREMENT"]
    assert extra and all("self_study" in item for item in extra)
    assert any(item["self_study"] for item in extra)
    assert all("self_study" not in item for item in unscheduled if item["kind"] != "JD_REQUIREMENT")
    scheduled = {activity["activity_id"] for week in roadmap["schedule"]["scheduled_weeks"] for activity in week["activities"]}
    assert not any(identifier.startswith("JD:") for identifier in scheduled)
    # Read at view time: the stored plan is not changed.
    assert all("self_study" not in item for item in store.roadmaps[next(iter(store.roadmaps))]["schedule"]["unscheduled_activities"])


def test_market_knowledge_is_built_from_the_sourced_files_and_industry_notes_wait_for_review():
    doc = knowledge._market_doc()[0]
    salary = json.loads((DATA / "salary_reference_v1.json").read_text(encoding="utf-8"))
    assert doc["url"] == salary["source"]["url"] and salary["source"]["label"] in doc["body"]
    assert all(str(band["value"]) in doc["body"] for band in salary["bands"])
    rows = {row["document_id"]: row["status"] for row in store.db.query("SELECT document_id, status FROM knowledge_documents WHERE is_current = 1")}
    assert rows["market-data-analyst"] == "APPROVED"
    assert rows["guide-industry-metrics"] == "DRAFT"
