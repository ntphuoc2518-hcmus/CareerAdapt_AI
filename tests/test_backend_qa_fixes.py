"""Regression tests for the backend QA findings: durable saves, bank versioning, item coverage,
roadmap history persistence, progress normalisation and fairer DA01A grading."""
import json
import uuid
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from backend.api.roadmaps import normalize_progress, overall_progress_percent
from backend.catalog import seed_catalogs
from backend.database import Database
from backend.engine.deterministic_grader import verify_da01a_submission
from backend.engine.test_engine import assemble_form
from backend.main import app
from backend.store import InMemoryStore, store
from data.seed import load_question_bank
from sample_submissions import DA01A_LEVEL_2

client = TestClient(app)
STUDENT = {"Authorization": "Bearer token_student_1"}
ADMIN = {"Authorization": "Bearer token_admin"}


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()
    yield
    store._persistence_enabled = False
    store.reset()


@pytest.fixture
def persisted(tmp_path, monkeypatch):
    """Turn persistence on for the global store, writing only to tmp files."""
    monkeypatch.setattr(store, "_persistence_enabled", True)
    monkeypatch.setattr(store, "_runtime_path", tmp_path / "state.json")
    monkeypatch.setattr(store, "_question_bank_overrides_path", tmp_path / "bank_overrides.json")
    database = Database(tmp_path / "state.sqlite3")
    seed_catalogs(database)
    monkeypatch.setattr(store, "db", database)
    return tmp_path


def _reloaded(tmp_path, monkeypatch) -> InMemoryStore:
    """A fresh store instance reading the same tmp files (simulates a restart)."""
    fresh = InMemoryStore.__new__(InMemoryStore)
    fresh._persistence_enabled = True
    fresh._runtime_path = tmp_path / "state.json"
    fresh._question_bank_overrides_path = tmp_path / "bank_overrides.json"
    fresh.db = Database(tmp_path / "state.sqlite3")
    fresh.reset()
    fresh._load_persisted_user_state()
    return fresh


# --- 1. Saved answers and events are durable ---------------------------------

def test_saved_response_and_event_survive_restart(persisted, monkeypatch):
    started = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    item = started["items"][0]
    value = item["options"][0]["id"] if item.get("options") else "1"
    if item["type"] in ("multiple", "ordering"):
        value = [value]
    assert client.put(f"/api/v1/tests/attempts/{started['attempt_id']}/responses/{item['item_id']}",
                      json={"value": value, "time_spent_seconds": 5}, headers=STUDENT).status_code == 200
    assert client.post(f"/api/v1/tests/attempts/{started['attempt_id']}/events", json={"type": "focus_lost"}, headers=STUDENT).status_code == 200

    restarted = _reloaded(persisted, monkeypatch)
    attempt = restarted.test_attempts[started["attempt_id"]]
    assert attempt["responses"][item["item_id"]]["value"] == value
    assert attempt["events"][0]["type"] == "focus_lost"


# --- 2. Question-bank edits are durable and versioned --------------------------

def _item_payload(item_id="SQL-901"):
    return {"item_id": item_id, "skill_code": "SQL", "level": 2, "type": "single", "topic": "Kiểm thử",
            "stem": "Câu hỏi kiểm thử phiên bản ngân hàng?", "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            "answer": "a", "explanation": "A đúng."}


def test_admin_item_edits_bump_version_and_survive_restart(persisted, monkeypatch):
    real_bank_before = load_question_bank()
    assert store.question_bank_version == "QB-DA-1.0"
    created = client.post("/api/v1/admin/tests/items", json=_item_payload(), headers=ADMIN)
    assert created.status_code == 201
    assert created.json()["bank_version"] == "QB-DA-1.1"
    updated = client.put("/api/v1/admin/tests/items/SQL-901", json={**_item_payload(), "answer": "b"}, headers=ADMIN)
    assert updated.status_code == 200 and updated.json()["bank_version"] == "QB-DA-1.2"
    edited = client.put("/api/v1/admin/tests/items/SQL-001", json={**_item_payload("SQL-001"), "level": 1}, headers=ADMIN)
    assert edited.json()["bank_version"] == "QB-DA-1.3"

    restarted = _reloaded(persisted, monkeypatch)
    assert restarted.question_bank_version == "QB-DA-1.3"
    assert restarted.get_question_item("SQL-901")["answer"] == "b"
    assert restarted.get_question_item("SQL-001")["stem"] == _item_payload()["stem"]
    assert len(restarted.question_items) == len(real_bank_before["items"]) + 1
    # The curated seed file is never rewritten.
    assert load_question_bank() == real_bank_before


def test_attempt_keeps_bank_version_after_edit():
    started = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=STUDENT).json()
    client.post("/api/v1/admin/tests/items", json=_item_payload(), headers=ADMIN)
    attempt = store.test_attempts[started["attempt_id"]]
    assert attempt["bank_version"] == "QB-DA-1.0"
    assert store.question_bank_version == "QB-DA-1.1"


def test_next_bank_version():
    assert InMemoryStore.next_bank_version("QB-DA-1.9") == "QB-DA-1.10"
    assert InMemoryStore.next_bank_version("v2") == "v2.1"


# --- 3. Item coverage and answer-key validity ----------------------------------

def test_every_skill_has_four_items_per_level():
    counts = Counter((i["skill_code"], i["level"]) for i in store.question_items if i.get("status", "ACTIVE") == "ACTIVE")
    for skill in store.skills:
        for level in (1, 2, 3):
            assert counts[(skill["skill_code"], level)] >= 4, (skill["skill_code"], level)


def test_answer_keys_are_valid():
    ids = [i["item_id"] for i in store.question_items]
    assert len(ids) == len(set(ids))
    for item in store.question_items:
        assert item["type"] in {"single", "multiple", "numeric", "ordering"}
        assert item.get("explanation") and item.get("topic") and item.get("stem")
        if item["type"] == "numeric":
            assert isinstance(item["answer"], (int, float)) and not isinstance(item["answer"], bool), item["item_id"]
            continue
        option_ids = [o["id"] for o in item["options"]]
        assert len(option_ids) == len(set(option_ids)) >= 2, item["item_id"]
        if item["type"] == "single":
            assert item["answer"] in option_ids, item["item_id"]
        elif item["type"] == "multiple":
            assert item["answer"] and set(item["answer"]) <= set(option_ids), item["item_id"]
        else:
            assert sorted(item["answer"]) == sorted(option_ids), item["item_id"]


@pytest.mark.parametrize("blueprint_id", [bp["blueprint_id"] for bp in load_question_bank()["blueprints"]])
def test_every_blueprint_can_be_assembled(blueprint_id):
    blueprint = store.get_blueprint(blueprint_id)
    for seed in range(5):
        form = assemble_form(blueprint, store.question_items, seed=seed)
        assert len(form) == sum(sum(levels.values()) for levels in blueprint["matrix"].values())


# --- 4. Roadmap history persistence ---------------------------------------------

def test_roadmap_history_is_kept_in_full_and_purged(persisted, monkeypatch):
    user_id = uuid.uuid4()
    store.roadmaps[user_id] = {"user_id": user_id, "activity_progress": {}, "activity_week_assignments": {}}
    for version in range(1, 26):
        store.save_roadmap_version(user_id, {"roadmap_version": version})
    store.persist_user_runtime(user_id)

    restarted = _reloaded(persisted, monkeypatch)
    versions = restarted.roadmap_history(user_id)
    assert [v["roadmap_version"] for v in versions] == list(range(1, 26))

    store.purge_user_data(user_id)
    assert store.roadmap_history(user_id) == []
    assert store.db.one("SELECT 1 FROM learner_state WHERE user_id = ?", (str(user_id),)) is None


# --- 5. Progress normalisation ---------------------------------------------------

@pytest.mark.parametrize("given,expected", [
    (("COMPLETED", 40), ("COMPLETED", 100)),
    (("NOT_STARTED", 0), ("NOT_STARTED", 0)),
    (("NOT_STARTED", 30), ("IN_PROGRESS", 30)),
    (("IN_PROGRESS", 0), ("IN_PROGRESS", 1)),
    (("IN_PROGRESS", 100), ("COMPLETED", 100)),
    (("IN_PROGRESS", 55), ("IN_PROGRESS", 55)),
    (("PAUSED", 100), ("PAUSED", 99)),
    (("PAUSED", 0), ("PAUSED", 0)),
    (("PAUSED", 40), ("PAUSED", 40)),
])
def test_normalize_progress(given, expected):
    assert normalize_progress(*given) == expected


def test_progress_patch_returns_normalised_values_and_overall_percent():
    client.delete("/me/data", headers=STUDENT)
    # Learning activities are planned from measured gaps, so give this learner two valid low results.
    profile = store.get_or_create_profile(uuid.UUID("11111111-1111-1111-1111-111111111111"))
    profile["assessed_skills"] = {code: {"level": 0} for code in ("SQL", "DATA_QUALITY", "PYTHON", "DATA_VIZ", "WRITTEN_COMM")}
    roadmap = client.post("/roadmaps", json={}, headers=STUDENT).json()
    assert roadmap["overall_progress_percent"] == 0.0

    resp = client.patch("/activities/ACT_SQL_01/progress", json={"status": "IN_PROGRESS", "progress_percent": 100}, headers=STUDENT)
    assert resp.status_code == 200
    body = resp.json()
    assert (body["status"], body["progress_percent"]) == ("COMPLETED", 100)
    assert 0 < body["overall_progress_percent"] < 100

    partial = client.patch("/activities/ACT_PY_01/progress", json={"status": "NOT_STARTED", "progress_percent": 50}, headers=STUDENT).json()
    assert (partial["status"], partial["progress_percent"]) == ("IN_PROGRESS", 50)
    assert partial["overall_progress_percent"] > body["overall_progress_percent"]

    # Prerequisite checks still apply after normalisation: ACT_VIZ_01 needs ACT_PY_01 completed.
    blocked = client.patch("/activities/ACT_VIZ_01/progress", json={"status": "NOT_STARTED", "progress_percent": 10}, headers=STUDENT)
    assert blocked.status_code == 409


def test_overall_progress_is_hours_weighted():
    progress = {"ACT_SQL_01": {"progress_percent": 100}}  # 4h done, ACT_PY_01 3h untouched
    assert overall_progress_percent(progress, {"ACT_SQL_01", "ACT_PY_01"}) == pytest.approx(400 / 7, abs=0.1)


# --- 6. Fairer DA01A grading -------------------------------------------------------

def test_non_executing_sql_with_sound_logic_is_capped_at_level_1():
    broken = DA01A_LEVEL_2.replace("FROM orders_raw", "FROM orders_missing_table")
    assert broken != DA01A_LEVEL_2
    res = verify_da01a_submission(broken)
    assert res["execution"]["executed"] is False
    sql = res["skill_results"]["SQL"]
    assert sql["level"] == 1
    assert "chưa chạy được" in sql["feedback"]
    assert all(skill["level"] <= 1 for skill in res["skill_results"].values())


def test_non_executing_sql_without_key_logic_stays_level_0():
    res = verify_da01a_submission("SELECT SUM(x) FROM nowhere GROUP BY y;")
    assert res["skill_results"]["SQL"]["level"] == 0


def test_failed_checks_come_with_next_steps():
    res = verify_da01a_submission("SELECT * FROM orders;")
    sql = res["skill_results"]["SQL"]
    assert sql["next_steps"] and "Việc nên làm tiếp" in sql["feedback"]
