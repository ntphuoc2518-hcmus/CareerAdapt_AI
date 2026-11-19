"""V4.0 acceptance: durability, migration from the JSON learner file, privacy, retention."""
import json
import uuid
from datetime import timedelta

import pytest

from backend.background import purge_expired_answers
from backend.catalog import seed_catalogs
from backend.clock import utcnow
from backend.database import Database
from backend.store import InMemoryStore, store
from v4_helpers import ADMIN, DA01_GOOD, STUDENT, STUDENT_ID, client, submit


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    yield
    store._persistence_enabled = False
    store.reset()


@pytest.fixture
def durable(tmp_path, monkeypatch):
    """Point the global store at a database file so a restart can be simulated."""
    monkeypatch.setattr(store, "_persistence_enabled", True)
    monkeypatch.setattr(store, "_runtime_path", tmp_path / "missing.json")
    monkeypatch.setattr(store, "_question_bank_overrides_path", tmp_path / "bank.json")
    database = Database(tmp_path / "app.sqlite3")
    seed_catalogs(database)
    monkeypatch.setattr(store, "db", database)
    return tmp_path


def restart(tmp_path, legacy=None) -> InMemoryStore:
    fresh_store = InMemoryStore.__new__(InMemoryStore)
    fresh_store._persistence_enabled = True
    fresh_store._runtime_path = legacy or tmp_path / "missing.json"
    fresh_store._question_bank_overrides_path = tmp_path / "bank.json"
    fresh_store.db = Database(tmp_path / "app.sqlite3")
    fresh_store.reset()
    fresh_store._load_persisted_user_state()
    return fresh_store


def test_submission_assessment_and_levels_survive_restart(durable):
    identifier = uuid.UUID(submit(DA01_GOOD).json()["submission_id"])
    after = restart(durable)
    assert after.assessments[identifier]["final_score"] == 100
    assert after.submissions[identifier]["status"] == "GRADED"
    assert after.profiles[STUDENT_ID]["assessed_skills"]["SQL"]["level"] == 2
    assert [row["skill_code"] for row in after.skill_evidence(STUDENT_ID)] == ["SQL", "DATA_QUALITY"]
    assert after.history_events(STUDENT_ID)


def test_review_queue_survives_restart(durable, monkeypatch):
    monkeypatch.setenv("CAREERADAPT_ENABLE_FAULT_INJECTION", "true")
    response = client.post("/submissions", json={"task_id": "DA01A", "answers": DA01_GOOD, "fault_injection": "conflict"}, headers=STUDENT)
    assert response.json()["status"] == "NEEDS_REVIEW"
    assert any(str(item["submission_id"]) == response.json()["submission_id"] for item in restart(durable).review_queue)


def test_pending_submission_survives_restart_with_its_answers(durable, monkeypatch):
    monkeypatch.setenv("CAREERADAPT_ENABLE_FAULT_INJECTION", "true")
    response = client.post("/submissions", json={"task_id": "DA01A", "answers": DA01_GOOD, "fault_injection": "timeout"}, headers=STUDENT)
    identifier = response.json()["submission_id"]
    after = restart(durable)
    assert after.submissions[uuid.UUID(identifier)]["status"] == "PENDING_RETRY"
    assert after.db.one("SELECT answer_text FROM submission_answers WHERE submission_id = ? AND question_id = 'Q1_CLEANING'", (identifier,))["answer_text"] == DA01_GOOD["Q1_CLEANING"]


def test_admin_content_edits_survive_restart(durable):
    body = {"activity_id": "ACT_NEW", "title": "Học phần mới", "target_skill": "SQL", "estimated_hours": 2, "prerequisites": [], "resource_ids": ["RES_KAGGLE_INTRO_SQL"], "learning_outcome": "Đầu ra"}
    assert client.post("/admin/activities", json=body, headers=ADMIN).status_code == 201
    assert restart(durable).get_activity("ACT_NEW")["title"] == "Học phần mới"


def test_legacy_json_is_imported_once_and_left_untouched(tmp_path):
    user_id = "425cbaf1-0000-4000-8000-000000000001"
    legacy = tmp_path / "learner_state_v1.json"
    content = json.dumps({
        user_id: {
            "profile": {"weekly_hours_budget": 6, "target_timeline_weeks": 10, "assessed_skills": {"SQL": {"level": 2}}, "self_reported_skills": [], "job_profile_id": "VN_ENTRY_ANALYST"},
            "activity_progress": {"ACT_SQL_01": {"status": "COMPLETED", "progress_percent": 100}},
            "activity_week_assignments": {"ACT_SQL_01": 1},
            "assessment_history": [{"submission_id": "a", "task_id": "DA01A"}],
            "test_attempts": [],
            # Real older files repeat version numbers; every entry must survive.
            "roadmap_history": [{"roadmap_version": 1, "created_at": "2026-10-01"}, {"roadmap_version": 1, "created_at": "2026-10-02"}, {"roadmap_version": 2, "created_at": "2026-10-03"}],
            "updated_at": "2026-10-30",
        },
        "not-a-uuid": {"profile": {}},
    }, ensure_ascii=False)
    legacy.write_text(content, encoding="utf-8")

    first = restart(tmp_path, legacy)
    key = uuid.UUID(user_id)
    assert first.profiles[key]["weekly_hours_budget"] == 6
    assert first.profiles[key]["assessed_skills"]["SQL"]["level"] == 2
    assert first.roadmaps[key]["activity_progress"]["ACT_SQL_01"]["status"] == "COMPLETED"
    assert [item["roadmap_version"] for item in first.roadmap_history(key)] == [1, 2, 3]
    assert [item["legacy_roadmap_version"] for item in first.roadmap_history(key)] == [1, 1, 2]
    assert first.latest_roadmap_version(key) == 3
    assert legacy.read_text(encoding="utf-8") == content

    first.profiles[key]["weekly_hours_budget"] = 9
    first.persist_user_runtime(key)
    second = restart(tmp_path, legacy)  # a later start must not overwrite newer data
    assert second.profiles[key]["weekly_hours_budget"] == 9


def test_corrupt_legacy_file_does_not_stop_the_app(tmp_path):
    legacy = tmp_path / "learner_state_v1.json"
    legacy.write_text("{not json", encoding="utf-8")
    assert restart(tmp_path, legacy).profiles == {}
    assert legacy.read_text(encoding="utf-8") == "{not json"


def test_erasure_removes_every_trace_of_the_learner():
    client.post("/jds/import", data={"text": "Vị trí: Data Analyst\nYêu cầu\n- Thành thạo SQL để truy vấn dữ liệu cho các báo cáo kinh doanh hằng tuần của công ty."}, headers=STUDENT)
    submit(DA01_GOOD)
    client.post("/roadmaps", headers=STUDENT)
    client.patch("/activities/ACT_PY_01/schedule", json={"cycle_days": 3}, headers=STUDENT)
    assert client.delete("/me/data", headers=STUDENT).status_code == 200
    owner = str(STUDENT_ID)
    for table, column in (("assessment_attempts", "user_id"), ("final_assessments", "user_id"), ("skill_evidence", "user_id"), ("history_events", "user_id"),
                          ("learner_state", "user_id"), ("learning_checkins", "user_id"), ("job_descriptions", "owner_user_id"), ("roadmap_versions", "user_id")):
        assert store.db.one(f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?", (owner,))["n"] == 0, table
    assert store.db.one("SELECT COUNT(*) AS n FROM submission_answers")["n"] == 0
    assert store.db.one("SELECT COUNT(*) AS n FROM security_events WHERE event = 'DATA_ERASED'")["n"] == 1


def test_export_includes_answers_and_evidence():
    submit(DA01_GOOD)
    data = client.get("/me/export", headers=STUDENT).json()
    assert data["submission_answers"] and data["skill_evidence"] and data["assessments"]


def test_answer_text_expires_but_the_result_stays():
    identifier = submit(DA01_GOOD).json()["submission_id"]
    old = (utcnow() - timedelta(days=91)).isoformat()
    store.db.execute("UPDATE submission_answers SET submitted_at = ?", (old,))
    assert purge_expired_answers() == 4
    assert store.db.one("SELECT answer_text FROM submission_answers WHERE submission_id = ? LIMIT 1", (identifier,))["answer_text"] is None
    assert store.db.one("SELECT final_score FROM final_assessments WHERE submission_id = ?", (identifier,))["final_score"] == 100


def test_transaction_rolls_back_as_one_unit():
    with pytest.raises(RuntimeError):
        with store.db.transaction():
            store.db.execute("INSERT INTO meta(key, value) VALUES ('a', '1')")
            with store.db.transaction():
                store.db.execute("INSERT INTO meta(key, value) VALUES ('b', '2')")
            raise RuntimeError("stop")
    assert store.db.get_meta("a") is None and store.db.get_meta("b") is None


def test_calibration_samples_are_anonymized_and_holdout_is_reported_separately():
    identifier = submit({**DA01_GOOD, "Q4_LIMITS": DA01_GOOD["Q4_LIMITS"] + " Email: an@student.hcmus.edu.vn"}).json()["submission_id"]
    body = {"submission_id": identifier, "skill_code": "SQL", "reference_level": 1, "split": "HOLDOUT", "consent_basis": "Người học đồng ý"}
    created = client.post("/admin/calibration-samples", json=body, headers=ADMIN)
    assert created.status_code == 201 and created.json()["system_level"] == 2
    assert "an@student" not in store.db.one("SELECT anonymized_text FROM calibration_samples")["anonymized_text"]
    report = client.get("/admin/calibration-samples", headers=ADMIN).json()["report"]
    assert report["HOLDOUT"] == {"count": 1, "mae": 1.0} and report["CALIBRATION"]["count"] == 0
    assert client.get("/admin/calibration-samples", headers=STUDENT).status_code == 403
