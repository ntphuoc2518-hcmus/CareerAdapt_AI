"""Skill progress and activity log (5.30): views computed on the server for the redesigned sections."""
import pytest

from backend.api.profiles import LOG_GROUPS
from backend.store import store
from v5_helpers import STUDENT, STUDENT_2, STUDENT_ID, client, complete_process


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield
    store.reset()


def log(query="", headers=STUDENT):
    response = client.get(f"/me/activity-log{query}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def progress(headers=STUDENT):
    return client.get("/me/skill-progress", headers=headers).json()


# --- Activity log ---

def test_the_log_is_newest_first_and_matches_the_stored_history():
    complete_process()
    stored = list(reversed(store.history_events(STUDENT_ID)))
    data = log("?limit=100")
    assert [item["event_id"] for item in data["items"]] == [item["event_id"] for item in stored]
    assert data["total"] == data["all_total"] == len(stored) and data["has_more"] is False


def test_group_counts_add_up_and_the_filter_returns_only_that_group():
    complete_process()
    data = log("?limit=100")
    assert sum(data["counts"].values()) == data["all_total"]
    for group, count in data["counts"].items():
        part = log(f"?group={group}&limit=100")
        assert part["total"] == count == len(part["items"]) and {item["group"] for item in part["items"]} <= {group}
        assert part["all_total"] == data["all_total"] and part["counts"] == data["counts"]


def test_the_log_loads_in_pages_without_gaps_or_repeats():
    complete_process()
    everything = [item["event_id"] for item in log("?limit=100")["items"]]
    assert len(everything) > 4
    seen, offset = [], 0
    while True:
        page = log(f"?limit=3&offset={offset}")
        seen += [item["event_id"] for item in page["items"]]
        offset += 3
        if not page["has_more"]:
            break
    assert seen == everything


def test_every_event_the_backend_writes_has_exactly_one_group():
    events = [event for group in LOG_GROUPS.values() for event in group]
    assert len(events) == len(set(events))
    complete_process()
    assert log("?limit=100")["counts"]["OTHER"] == 0


def test_an_unknown_event_lands_in_other_instead_of_vanishing():
    store.add_history_event(STUDENT_ID, "SOMETHING_NEW", "Sự kiện mới")
    data = log()
    assert data["counts"]["OTHER"] == 1 and log("?group=OTHER")["items"][0]["event"] == "SOMETHING_NEW"


def test_old_lines_show_the_lesson_name_and_status_in_words():
    store.add_history_event(STUDENT_ID, "UPDATE_PROGRESS", "Cập nhật học phần ACT_SQL_01: IN_PROGRESS (1%)")
    detail = log()["items"][0]["detail"]
    title = store.get_activity("ACT_SQL_01")["title"]
    assert detail == f"Cập nhật học phần {title}: đang học (1%)"


@pytest.mark.parametrize("query", ["?group=NOPE", "?limit=0", "?limit=101", "?offset=-1", "?limit=abc"])
def test_bad_log_queries_are_refused(query):
    assert client.get(f"/me/activity-log{query}", headers=STUDENT).status_code == 422


def test_the_log_and_progress_need_a_session_and_belong_to_one_account():
    complete_process()
    assert client.get("/me/activity-log").status_code == 401 and client.get("/me/skill-progress").status_code == 401
    assert log(headers=STUDENT_2)["all_total"] == 0
    assert progress(STUDENT_2) == {"skills": [], "total_entries": 0, "raised": 0, "lowered": 0, "met": 0, "with_target": 0, "max_level": 3}


# --- Skill progress ---

def test_progress_matches_the_evidence_and_the_gap_page():
    complete_process()
    evidence = client.get("/me/skill-history", headers=STUDENT).json()
    gap = {item["skill_code"]: item for item in client.get("/me/gap", headers=STUDENT).json()["skill_evaluations"]}
    data = progress()
    assert data["total_entries"] == len(evidence) == sum(len(skill["entries"]) for skill in data["skills"])
    for skill in data["skills"]:
        rows = [row for row in evidence if row["skill_code"] == skill["skill_code"]]
        assert skill["current_level"] == rows[-1]["level"] == gap[skill["skill_code"]]["current_level"]
        assert skill["first_level"] == rows[0]["level"] and skill["target_level"] == gap[skill["skill_code"]]["target_level"]
        assert skill["meets_target"] == (skill["current_level"] >= skill["target_level"])


def test_each_entry_carries_the_step_from_the_one_before():
    for level, source, at in ((1, "ASSESSMENT", "2026-11-01T03:00:00+00:00"), (2, "MINI_TEST", "2026-11-05T03:00:00+00:00"), (1, "FINAL_ASSESSMENT", "2026-11-09T03:00:00+00:00")):
        store.add_skill_evidence(STUDENT_ID, "SQL", level, source, f"src-{at}", created_at=at)
    data = progress()
    skill = data["skills"][0]
    assert [(entry["level"], entry["previous_level"], entry["delta"], entry["source_type"]) for entry in skill["entries"]] == [
        (1, 2, -1, "FINAL_ASSESSMENT"), (2, 1, 1, "MINI_TEST"), (1, None, None, "ASSESSMENT")]
    assert (skill["first_level"], skill["current_level"], skill["change"]) == (1, 1, 0)
    assert (data["raised"], data["lowered"]) == (0, 0)


def test_a_new_progress_event_names_the_lesson():
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"] = {code: {"level": 1} for code in ("SQL", "DATA_QUALITY", "PYTHON", "DATA_VIZ", "WRITTEN_COMM")}
    client.post("/roadmaps", headers=STUDENT)
    activity = next(iter(store.roadmaps[STUDENT_ID]["activity_plan"]))
    assert client.patch(f"/activities/{activity}/progress", json={"status": "IN_PROGRESS", "progress_percent": 10}, headers=STUDENT).status_code == 200
    line = next(item for item in store.history_events(STUDENT_ID) if item["event"] == "UPDATE_PROGRESS")
    assert store.get_activity(activity)["title"] in line["detail"] and "đang học" in line["detail"] and "IN_PROGRESS" not in line["detail"]
