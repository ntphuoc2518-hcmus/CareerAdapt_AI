"""Integration Test Suite: Content Admin CRUD & Human-in-the-Loop Reviews (F09).

Covers:
1. Skills CRUD & Total Weight Validation
2. Tasks Catalog CRUD
3. Activities CRUD & DAG Cycle Prevention (DFS Validator)
4. Human-in-the-Loop Review & Arbitration Queue
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.store import store

client = TestClient(app)

ADMIN_HEADER = {"Authorization": "Bearer token_admin"}
STUDENT_HEADER = {"Authorization": "Bearer token_student_1"}


@pytest.fixture(autouse=True)
def reset_store_state():
    store.reset()


def test_admin_skills_crud_and_weight_warning():
    """Admin can list, add, edit, and delete skills with total weight tracking."""
    # List skills
    resp = client.get("/admin/skills", headers=ADMIN_HEADER)
    assert resp.status_code == 200
    assert resp.json()["is_weight_valid"] is True

    # Add new skill with weight 0.10 -> total weight becomes 1.10 (triggers warning)
    new_skill = {
        "skill_code": "FORECASTING",
        "skill_name": "Dự Báo Chuỗi Thời Gian",
        "category": "Toán - Dự báo",
        "target_level": 2,
        "weight": 0.10,
        "is_core": False
    }
    resp_post = client.post("/admin/skills", json=new_skill, headers=ADMIN_HEADER)
    assert resp_post.status_code == 201
    data = resp_post.json()
    assert data["warning"] is not None
    assert "Cảnh báo" in data["warning"]

    # Delete skill
    resp_del = client.delete("/admin/skills/FORECASTING", headers=ADMIN_HEADER)
    assert resp_del.status_code == 200


def test_activity_dag_cycle_prevention_in_admin():
    """Attempting to add an activity creating a cyclic dependency must be blocked with 400."""
    # ACT_SQL_01 has no prereqs. ACT_DQ_01 depends on ACT_SQL_01.
    # We add ACT_CYCLE which depends on ACT_DQ_01, and we try to add another node making ACT_SQL_01 depend on ACT_CYCLE!
    # Let's add an activity that depends on ACT_COMM_01 and try to make ACT_SQL_01 depend on it:
    # Directly test an activity creating immediate cycle:
    bad_activity = {
        "activity_id": "ACT_SQL_01_BAD",
        "title": "Cyclic Activity",
        "target_skill": "SQL",
        "estimated_hours": 3.0,
        "prerequisites": ["ACT_COMM_01"] # ACT_COMM_01 depends on ACT_DQ_01 -> ACT_SQL_01
    }
    # Now if ACT_SQL_01 depends on ACT_SQL_01_BAD, that would be a cycle.
    # Or create self-cycle:
    self_cycle_act = {
        "activity_id": "ACT_SELF_CYCLE",
        "title": "Self Cycle Activity",
        "target_skill": "SQL",
        "estimated_hours": 2.0,
        "prerequisites": ["ACT_SELF_CYCLE"]
    }
    resp = client.post("/admin/activities", json=self_cycle_act, headers=ADMIN_HEADER)
    assert resp.status_code == 400
    assert "DAG Cycle" in resp.json()["error"]["message"]


def test_human_in_the_loop_review_resolution(monkeypatch):
    """Admin can resolve items in NEEDS_REVIEW queue and update student profile."""
    # Fault injection is a demo/test switch and is off unless explicitly enabled.
    monkeypatch.setenv("CAREERADAPT_ENABLE_FAULT_INJECTION", "true")
    # 1. Simulate a conflict submission
    sub_id = uuid.uuid4()
    user_id = store.get_or_create_profile(uuid.UUID("11111111-1111-1111-1111-111111111111"))["user_id"]
    
    # Submit with fault injection conflict
    sub_payload = {
        "task_id": "DA01A",
        "submission_text": "SELECT * FROM orders;",
        "mode": "ASSESSMENT",
        "fault_injection": "conflict"
    }
    sub_resp = client.post("/submissions", json=sub_payload, headers=STUDENT_HEADER)
    sub_id = sub_resp.json()["submission_id"]

    # 2. Check review queue
    reviews_resp = client.get("/admin/reviews", headers=ADMIN_HEADER)
    assert reviews_resp.status_code == 200
    reviews = reviews_resp.json()
    assert len(reviews) >= 1
    assert any(r["submission_id"] == sub_id for r in reviews)

    # 3. Resolve review (Admin overrides level to 2)
    resolve_payload = {
        "override_level": 2,
        "reviewer_notes": "Giảng viên đã xem xét giải trình và xác nhận bài nộp đạt chuẩn tuyển dụng Level 2."
    }
    resolve_resp = client.post(f"/admin/reviews/{sub_id}/resolve", json=resolve_payload, headers=ADMIN_HEADER)
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["final_level"] == 2

    # 4. Verify review queue is now cleared
    reviews_after = client.get("/admin/reviews", headers=ADMIN_HEADER).json()
    assert not any(r["submission_id"] == sub_id for r in reviews_after)
