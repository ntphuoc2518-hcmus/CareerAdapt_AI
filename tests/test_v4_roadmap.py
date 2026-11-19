"""V4.0 acceptance: gap, readiness, roadmap and learning resources (RES-01, F05-F07, F19)."""
import uuid

import pytest

from backend.catalog import get_resource, list_resources, update_resource_state
from backend.engine.dag_scheduler import schedule_dag_roadmap, validate_prerequisite_graph
from backend.engine.gap_coverage import evaluate_competency_framework
from backend.engine.link_checker import check_url, validate_public_url
from backend.engine.roadmap_planner import plan_items
from backend.store import store
from backend.targeting import evaluate_learner
from v4_helpers import ADMIN, DA01_GOOD, DA02_GOOD, STUDENT, STUDENT_ID, client, submit
from sample_submissions import DA03A_LEVEL_2


@pytest.fixture(autouse=True)
def fresh():
    store.reset()


def set_levels(**levels):
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {code: {"level": level, "submission_id": "x", "assessed_at": "2026-01-01"} for code, level in levels.items()}
    return profile


def set_budget(weekly, weeks):
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["weekly_hours_budget"], profile["target_timeline_weeks"] = weekly, weeks


def roadmap():
    resp = client.post("/roadmaps", headers=STUDENT)
    assert resp.status_code == 200, resp.text
    return resp.json()


def scheduled(plan):
    return [activity for week in plan["schedule"]["scheduled_weeks"] for activity in week["activities"]]


SKILLS = [
    {"skill_code": "SQL", "target_level": 2, "weight": 0.30, "is_core": True},
    {"skill_code": "DATA_QUALITY", "target_level": 2, "weight": 0.20, "is_core": True},
    {"skill_code": "PYTHON", "target_level": 1, "weight": 0.15, "is_core": False},
    {"skill_code": "DATA_VIZ", "target_level": 2, "weight": 0.20, "is_core": False},
    {"skill_code": "WRITTEN_COMM", "target_level": 2, "weight": 0.15, "is_core": False},
]


# Gap and readiness
def test_unassessed_is_not_level_zero():
    result = evaluate_competency_framework(SKILLS, {"SQL": 0})
    by_code = {item["skill_code"]: item for item in result["skill_evaluations"]}
    assert by_code["SQL"]["current_level"] == 0 and by_code["SQL"]["gap"] == 2 and by_code["SQL"]["status"] == "ASSESSED"
    assert by_code["PYTHON"]["current_level"] is None and by_code["PYTHON"]["gap"] is None
    assert by_code["PYTHON"]["attainment"] is None and by_code["PYTHON"]["next_action"] == "ASSESS"


def test_readiness_is_exactly_at_the_80_percent_boundary():
    levels = {"SQL": 2, "DATA_QUALITY": 2, "PYTHON": 1, "WRITTEN_COMM": 2}  # 0.30 + 0.20 + 0.15 + 0.15
    result = evaluate_competency_framework(SKILLS, levels)
    assert result["coverage"] == 0.80 and result["is_readiness_locked"] is False and result["readiness"] == 100.0


def test_readiness_formula_uses_only_measured_skills():
    levels = {"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 1}
    result = evaluate_competency_framework(SKILLS, levels)
    expected = round(100 * (0.30 * 0.5 + 0.20 + 0.15 + 0.20 * 0.5) / 0.85, 2)
    assert result["readiness"] == expected


def test_missing_core_skill_keeps_readiness_locked_at_high_coverage():
    skills = [{"skill_code": "A", "target_level": 1, "weight": 0.9, "is_core": False}, {"skill_code": "B", "target_level": 1, "weight": 0.1, "is_core": True}]
    result = evaluate_competency_framework(skills, {"A": 1})
    assert result["coverage"] == 0.9 and result["readiness"] is None and result["missing_core_skills"] == ["B"]


def test_priority_ties_break_by_core_then_weight_then_code():
    skills = [
        {"skill_code": "Z", "target_level": 2, "weight": 0.2, "is_core": False},
        {"skill_code": "B", "target_level": 2, "weight": 0.2, "is_core": False},
        {"skill_code": "C", "target_level": 2, "weight": 0.2, "is_core": True},
    ]
    order = [item["skill_code"] for item in evaluate_competency_framework(skills, {"Z": 0, "B": 0, "C": 0})["skill_evaluations"]]
    assert order == ["C", "B", "Z"]


def test_self_report_is_shown_but_never_counted():
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["self_reported_skills"] = [{"skill_code": "SQL", "level": 3}]
    result = client.get("/me/gap", headers=STUDENT).json()
    sql = next(item for item in result["skill_evaluations"] if item["skill_code"] == "SQL")
    assert sql["self_reported_level"] == 3 and sql["current_level"] is None and sql["status"] == "UNASSESSED"
    assert result["coverage"] == 0 and "tự khai" in sql["explanation"]


def test_gap_explains_reasons_and_evidence():
    submit(DA01_GOOD)
    result = client.get("/me/gap", headers=STUDENT).json()
    sql = next(item for item in result["skill_evaluations"] if item["skill_code"] == "SQL")
    assert sql["evidence"]["task_id"] == "DA01A" and "đạt mục tiêu" in sql["explanation"]
    assert result["coverage"] == 0.5 and result["recommended_assessment"]["task_id"] in {"DA02A", "DA03A"}
    assert result["target"]["name"] and "không phải" in result["scope_notice"]


def test_gap_uses_the_confirmed_target_weights():
    client.post("/me/target-jd", json={"jd_id": "KYANON_INTERN_DA", "jd_version": 1}, headers=STUDENT)
    submit(DA01_GOOD)
    result = client.get("/me/gap", headers=STUDENT).json()
    assert result["coverage"] == 0.60 and result["target"]["jd_id"] == "KYANON_INTERN_DA"


def test_full_journey_reaches_readiness_with_real_submissions():
    submit(DA01_GOOD)
    assert client.get("/me/gap", headers=STUDENT).json()["is_readiness_locked"] is True
    submit(DA02_GOOD, task_id="DA02A")
    gap = client.get("/me/gap", headers=STUDENT).json()
    assert gap["coverage"] == 0.85 and gap["readiness"] is not None
    submit({"Q1_REPORT": DA03A_LEVEL_2}, task_id="DA03A")
    assert client.get("/me/gap", headers=STUDENT).json()["coverage"] == 1.0


# Roadmap selection
def test_new_learner_is_sent_to_assessments_first():
    plan = roadmap()
    kinds = {item["kind"] for item in scheduled(plan)}
    assert kinds == {"ASSESSMENT"}
    assert {item["task_id"] for item in scheduled(plan)} == {"DA01A", "DA02A", "DA03A"}
    assert plan["recommended_assessment"]["task_id"] == "DA01A"


def test_no_gap_means_no_learning_activity():
    set_levels(SQL=2, DATA_QUALITY=2, PYTHON=1, DATA_VIZ=2, WRITTEN_COMM=2)
    assert scheduled(roadmap()) == []


def test_activities_match_gap_and_stop_at_the_target():
    set_levels(SQL=1, DATA_QUALITY=2, PYTHON=1, DATA_VIZ=2, WRITTEN_COMM=2)
    ids = {item["activity_id"] for item in scheduled(roadmap())}
    assert ids == {"ACT_SQL_01"}  # ACT_SQL_02 is level 3, beyond the target of 2


def test_scheduled_activities_have_resources_outcome_and_dates():
    set_levels(SQL=0, DATA_QUALITY=0, PYTHON=0, DATA_VIZ=0, WRITTEN_COMM=0)
    set_budget(4, 8)
    plan = roadmap()
    items = scheduled(plan)
    assert items
    for item in items:
        assert item["resources"] and item["learning_outcome"] and item["estimated_hours"] and item["planned_end"] and item["review_due"]
        for resource in item["resources"]:
            assert resource["status"] == "APPROVED" and resource["last_checked_at"] and resource["url"]


def test_weekly_budget_is_never_exceeded():
    set_levels(SQL=0, DATA_QUALITY=0, PYTHON=0, DATA_VIZ=0, WRITTEN_COMM=0)
    for weekly in (1, 2.5, 4, 10):
        set_budget(weekly, 12)
        for week in roadmap()["schedule"]["scheduled_weeks"]:
            assert sum(item["allocated_hours"] for item in week["activities"]) <= weekly + 1e-9
            assert week["allocated_hours"] <= weekly + 1e-9


def test_prerequisites_finish_before_dependents_start():
    set_levels(SQL=0, DATA_QUALITY=0, PYTHON=0, DATA_VIZ=0, WRITTEN_COMM=0)
    set_budget(2, 12)
    plan = roadmap()
    first, last = {}, {}
    for week in plan["schedule"]["scheduled_weeks"]:
        for item in week["activities"]:
            first.setdefault(item["activity_id"], week["week_number"])
            last[item["activity_id"]] = week["week_number"]
    assert last["ACT_SQL_01"] <= first["ACT_DQ_01"]
    assert last["ACT_DQ_01"] <= first["ACT_COMM_01"]
    assert last["ACT_PY_01"] <= first["ACT_VIZ_01"]


def test_tight_budget_lists_unscheduled_with_reasons_and_options():
    set_levels(SQL=0, DATA_QUALITY=0, PYTHON=0, DATA_VIZ=0, WRITTEN_COMM=0)
    set_budget(1, 2)
    plan = roadmap()
    unscheduled = plan["schedule"]["unscheduled_activities"]
    assert unscheduled and all(item["reason"] and item["reason_code"] for item in unscheduled)
    assert plan["schedule"]["meets_deadline"] is False
    assert any(option["kind"] == "EXTEND_TIMELINE" for option in plan["recovery_options"])
    assert plan["weekly_hours_budget"] == 1  # hours are never raised to fit


def test_unsplittable_activity_longer_than_a_week_is_explained():
    activities = [{"activity_id": "A", "title": "A", "estimated_hours": 5, "prerequisites": [], "splittable": False}]
    result = schedule_dag_roadmap(activities, 4, 8)
    assert result["unscheduled_activities"][0]["reason_code"] == "EXCEEDS_WEEKLY_BUDGET"


def test_splittable_activity_spans_weeks_only_when_it_can_finish():
    activities = [{"activity_id": "A", "title": "A", "estimated_hours": 5, "prerequisites": [], "splittable": True}]
    result = schedule_dag_roadmap(activities, 2, 3)
    assert [week["allocated_hours"] for week in result["scheduled_weeks"]] == [2, 2, 1]
    assert result["unscheduled_activities"] == []
    too_long = schedule_dag_roadmap(activities, 2, 2)
    assert too_long["scheduled_weeks"] == [] and too_long["unscheduled_activities"][0]["reason_code"] == "INSUFFICIENT_HOURS"


def test_failed_prerequisite_blocks_dependents_with_reason():
    activities = [
        {"activity_id": "A", "title": "A", "estimated_hours": 9, "prerequisites": []},
        {"activity_id": "B", "title": "B", "estimated_hours": 1, "prerequisites": ["A"]},
    ]
    result = schedule_dag_roadmap(activities, 4, 8)
    assert {item["activity_id"]: item["reason_code"] for item in result["unscheduled_activities"]} == {"A": "EXCEEDS_WEEKLY_BUDGET", "B": "MISSING_PREREQUISITE"}


def test_unmeasured_prerequisite_waits_for_evidence():
    set_levels(SQL=2, DATA_QUALITY=2, PYTHON=1, WRITTEN_COMM=0)  # DATA_VIZ unmeasured
    plan = roadmap()
    assert "ACT_COMM_01" in {item["activity_id"] for item in scheduled(plan)}  # prerequisite met by evidence
    assert "ASSESS_DA02A" in {item["activity_id"] for item in scheduled(plan)}


def test_prerequisite_is_added_when_a_measured_skill_is_behind_it():
    set_levels(SQL=0, DATA_QUALITY=2, PYTHON=1, DATA_VIZ=2, WRITTEN_COMM=2)
    set_budget(4, 8)
    assert {item["activity_id"] for item in scheduled(roadmap())} == {"ACT_SQL_01"}


# Cycles
def test_cycle_in_catalog_blocks_roadmap_and_names_the_nodes():
    store.get_activity("ACT_SQL_01")["prerequisites"] = ["ACT_COMM_01"]
    resp = client.post("/roadmaps", headers=STUDENT)
    assert resp.status_code == 409
    message = resp.json()["error"]["message"]
    assert "ACT_SQL_01" in message and "ACT_COMM_01" in message


def test_missing_prerequisite_blocks_roadmap():
    store.get_activity("ACT_SQL_01")["prerequisites"] = ["ACT_GHOST"]
    resp = client.post("/roadmaps", headers=STUDENT)
    assert resp.status_code == 409 and "ACT_GHOST" in resp.json()["error"]["message"]


def test_scheduler_reports_cycle_path():
    activities = [{"activity_id": "A", "title": "A", "prerequisites": ["B"]}, {"activity_id": "B", "title": "B", "prerequisites": ["A"]}]
    result = schedule_dag_roadmap(activities, 4, 8)
    assert result["blocked"] and "A" in result["cycle_path"] and result["unscheduled_activities"][0]["reason_code"] == "PREREQUISITE_CYCLE"
    assert validate_prerequisite_graph(activities)["has_cycle"]


def test_admin_cannot_save_a_cycle():
    body = {"activity_id": "ACT_SQL_01", "title": "x", "target_skill": "SQL", "estimated_hours": 2, "prerequisites": ["ACT_COMM_01"]}
    resp = client.put("/admin/activities/ACT_SQL_01", json=body, headers=ADMIN)
    assert resp.status_code == 400 and "DAG Cycle" in resp.json()["error"]["message"]


# Versions
def test_changing_hours_creates_a_new_version_and_keeps_history():
    set_levels(SQL=0, DATA_QUALITY=0, PYTHON=0, DATA_VIZ=0, WRITTEN_COMM=0)
    first = roadmap()
    assert roadmap()["roadmap_version"] == first["roadmap_version"]  # same inputs, same version
    set_budget(2, 8)
    second = roadmap()
    assert second["roadmap_version"] == first["roadmap_version"] + 1 and "đổi số giờ" in second["change_reason"]
    history = client.get("/me/roadmaps/history", headers=STUDENT).json()
    assert [item["roadmap_version"] for item in history] == [1, 2]
    assert history[0]["weekly_hours_budget"] == 4


def test_new_target_creates_a_new_version_pointing_at_the_jd():
    first = roadmap()
    client.post("/me/target-jd", json={"jd_id": "TCDATA_INTERN_DA", "jd_version": 1}, headers=STUDENT)
    second = roadmap()
    assert second["roadmap_version"] == first["roadmap_version"] + 1
    assert second["target"]["jd_id"] == "TCDATA_INTERN_DA" and second["target"]["jd_version"] == 1 and second["target"]["mapping_version"]
    row = store.db.one("SELECT jd_id, jd_version, mapping_version, algorithm_version FROM roadmap_versions WHERE version = ?", (second["roadmap_version"],))
    assert row["jd_id"] == "TCDATA_INTERN_DA" and row["algorithm_version"]


def test_jd_requirements_outside_the_catalog_are_not_silently_dropped():
    client.post("/me/target-jd", json={"jd_id": "TCDATA_INTERN_DA", "jd_version": 1}, headers=STUDENT)
    unscheduled = roadmap()["schedule"]["unscheduled_activities"]
    assert any(item["reason_code"] == "OUTSIDE_CATALOG" and item["title"] == "DAX" for item in unscheduled)


def test_same_inputs_give_the_same_plan():
    set_levels(SQL=0, DATA_QUALITY=1, PYTHON=0, DATA_VIZ=1, WRITTEN_COMM=0)
    first = [item["activity_id"] for item in scheduled(roadmap())]
    store.roadmaps.pop(STUDENT_ID)
    assert first == [item["activity_id"] for item in scheduled(roadmap())]


def test_completing_an_activity_is_not_evidence():
    set_levels(SQL=0, DATA_QUALITY=2, PYTHON=1, DATA_VIZ=2, WRITTEN_COMM=2)
    roadmap()
    assert client.patch("/activities/ACT_SQL_01/progress", json={"status": "COMPLETED"}, headers=STUDENT).status_code == 200
    assert store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] == 0
    assert client.get("/me/progress-history", headers=STUDENT).json()[0]["to_status"] == "COMPLETED"


def test_overdue_is_not_a_competency_signal():
    gap_before = evaluate_learner(STUDENT_ID)["coverage"]
    roadmap()
    assert evaluate_learner(STUDENT_ID)["coverage"] == gap_before


# Resources
def test_learner_catalog_shows_only_approved_checked_resources():
    update_resource_state(store.db, "RES_KAGGLE_PANDAS", status="HIDDEN")
    update_resource_state(store.db, "RES_KAGGLE_PYTHON", last_checked_at=None)
    draft = client.post("/admin/resources", json={"title": "Bản nháp", "provider": "Nhà cung cấp", "resource_type": "COURSE", "url": "https://example.com/x", "skill_ids": ["SQL"], "estimated_minutes": 30, "learning_outcome": "Đầu ra học tập"}, headers=ADMIN)
    assert draft.status_code == 201
    items = client.get("/learning-resources", headers=STUDENT).json()["items"]
    ids = {item["resource_id"] for item in items}
    assert "RES_KAGGLE_PANDAS" not in ids and "RES_KAGGLE_PYTHON" not in ids and not any(item["title"] == "Bản nháp" for item in items)
    assert all(item["status"] == "APPROVED" and item["last_checked_at"] and item["provider"] and item["estimated_minutes"] for item in items)


def test_resource_filters():
    sql = client.get("/learning-resources", params={"skill_id": "SQL"}, headers=STUDENT).json()
    assert sql["total"] >= 3 and all("SQL" in item["skill_ids"] for item in sql["items"])
    assert all(item["level"] == 3 for item in client.get("/learning-resources", params={"level": 3}, headers=STUDENT).json()["items"])


def test_activity_without_approved_resource_is_unscheduled_with_reason():
    # Every resource of the activity is hidden, whatever the catalog holds today.
    for resource_id in store.get_activity("ACT_COMM_01")["resource_ids"]:
        update_resource_state(store.db, resource_id, status="HIDDEN")
    set_levels(SQL=2, DATA_QUALITY=2, PYTHON=1, DATA_VIZ=2, WRITTEN_COMM=0)
    plan = roadmap()
    assert "ACT_COMM_01" not in {item["activity_id"] for item in scheduled(plan)}
    reason = next(item for item in plan["schedule"]["unscheduled_activities"] if item["activity_id"] == "ACT_COMM_01")
    assert reason["reason_code"] == "NO_APPROVED_RESOURCE"


# RES-01
def test_res01_dead_link_hides_resource_keeps_history_offers_alternative(monkeypatch):
    set_levels(SQL=0, DATA_QUALITY=2, PYTHON=1, DATA_VIZ=2, WRITTEN_COMM=2)
    before = roadmap()
    version = before["roadmap_version"]
    monkeypatch.setattr("backend.api.resources.check_url", lambda url: {"link_status": "BROKEN", "http_status": 404, "detail": "Trang không còn tồn tại."})
    checked = client.post("/admin/resources/RES_KAGGLE_INTRO_SQL/check-link", headers=ADMIN).json()
    assert checked["resource"]["status"] == "HIDDEN" and checked["resource"]["link_status"] == "BROKEN"
    assert "RES_KAGGLE_INTRO_SQL" not in {item["resource_id"] for item in list_resources(store.db)}

    current = client.get("/me/roadmap", headers=STUDENT).json()
    assert current["roadmap_version"] == version  # history is untouched
    warning = next(item for item in current["resource_warnings"] if item["resource_id"] == "RES_KAGGLE_INTRO_SQL")
    assert warning["message"]
    resource = next(r for item in scheduled(current) for r in item["resources"] if r["resource_id"] == "RES_KAGGLE_INTRO_SQL")
    assert resource["available"] is False and resource["alternatives"]

    regenerated = roadmap()
    assert all(r["resource_id"] != "RES_KAGGLE_INTRO_SQL" for item in scheduled(regenerated) for r in item["resources"])
    assert regenerated["roadmap_version"] == version + 1
    assert any(r["resource_id"] == "RES_KAGGLE_INTRO_SQL" for item in scheduled(client.get("/me/roadmaps/history", headers=STUDENT).json()[0]) for r in item["resources"])


def test_bot_blocking_site_is_not_marked_broken(monkeypatch):
    monkeypatch.setattr("backend.api.resources.check_url", lambda url: {"link_status": "UNKNOWN", "http_status": 403, "detail": "x"})
    checked = client.post("/admin/resources/RES_KAGGLE_PYTHON/check-link", headers=ADMIN).json()
    assert checked["resource"]["status"] == "APPROVED" and checked["resource"]["link_status"] == "UNKNOWN"


def test_new_resource_cannot_be_approved_before_a_link_check(monkeypatch):
    body = {"title": "Khóa mới", "provider": "Nhà cung cấp", "resource_type": "COURSE", "url": "https://example.com/khoa", "skill_ids": ["SQL"], "estimated_minutes": 60, "learning_outcome": "Đầu ra học tập"}
    created = client.post("/admin/resources", json=body, headers=ADMIN).json()
    assert created["status"] == "DRAFT" and created["link_status"] == "UNCHECKED"
    url = f"/admin/resources/{created['resource_id']}/review?decision=APPROVED"
    assert client.post(url, headers=ADMIN).status_code == 409
    monkeypatch.setattr("backend.api.resources.check_url", lambda link: {"link_status": "OK", "http_status": 200, "detail": "x"})
    client.post(f"/admin/resources/{created['resource_id']}/check-link", headers=ADMIN)
    assert client.post(url, headers=ADMIN).json()["status"] == "APPROVED"


def test_editing_a_resource_creates_a_new_version_back_in_draft():
    current = get_resource(store.db, "RES_KAGGLE_PYTHON")
    body = {key: current[key] for key in ("title", "provider", "resource_type", "url", "language", "cost_access", "skill_ids", "level", "estimated_minutes", "learning_outcome")}
    updated = client.put("/admin/resources/RES_KAGGLE_PYTHON", json={**body, "title": "Python mới"}, headers=ADMIN).json()
    assert updated["resource_version"] == 2 and updated["status"] == "DRAFT"
    assert store.db.one("SELECT COUNT(*) AS n FROM learning_resources WHERE resource_id = 'RES_KAGGLE_PYTHON'")["n"] == 2


def test_invalid_resource_url_is_refused():
    body = {"title": "x x", "provider": "Nhà cung cấp", "resource_type": "COURSE", "url": "ftp://example.com/x", "skill_ids": ["SQL"], "estimated_minutes": 60, "learning_outcome": "Đầu ra"}
    resp = client.post("/admin/resources", json=body, headers=ADMIN)
    assert resp.status_code == 422 and "URL" in resp.json()["error"]["message"]


@pytest.mark.parametrize("url", ["http://127.0.0.1/admin", "http://localhost/x", "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd"])
def test_link_checker_refuses_internal_targets(url):
    assert validate_public_url(url)
    assert check_url(url)["link_status"] == "BROKEN"


def test_every_activity_points_at_catalog_resources():
    known = {item["resource_id"] for item in list_resources(store.db, approved_only=False)}
    for activity in store.activities:
        assert set(activity["resource_ids"]) <= known and activity["learning_outcome"]


def test_every_seed_resource_has_the_required_fields():
    for item in list_resources(store.db, approved_only=False):
        for field in ("title", "provider", "resource_type", "url", "language", "cost_access", "skill_ids", "level", "estimated_minutes", "learning_outcome", "source_note", "status", "last_checked_at", "next_review_at", "link_status"):
            assert item.get(field) not in (None, ""), (item["resource_id"], field)


def test_plan_is_pure_and_reports_activity_without_resources():
    evaluation = evaluate_competency_framework(SKILLS, {"DATA_QUALITY": 2, "SQL": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2})
    skill = next(item for item in evaluation["skill_evaluations"] if item["skill_code"] == "DATA_QUALITY")
    skill["target_level"], skill["gap"] = 3, 1
    # None of the activity's resources is usable, whatever the catalog holds today.
    own = set(store.get_activity("ACT_DQ_02")["resource_ids"])
    usable = [item for item in list_resources(store.db) if item["resource_id"] not in own]
    plan = plan_items(evaluation, store.activities, store.tasks, usable, set())
    assert any(item["activity_id"] == "ACT_DQ_02" and item["reason_code"] == "NO_APPROVED_RESOURCE" for item in plan["excluded"])


def test_unknown_user_cannot_read_other_roadmap():
    assert client.get("/me/roadmap", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert uuid.UUID(str(STUDENT_ID))


def test_new_version_continues_after_imported_history():
    for version in (1, 2, 3):
        store.save_roadmap_version(STUDENT_ID, {"roadmap_version": version})
    assert roadmap()["roadmap_version"] == 4
    assert [item["roadmap_version"] for item in client.get("/me/roadmaps/history", headers=STUDENT).json()] == [1, 2, 3, 4]
