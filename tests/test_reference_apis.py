"""Integration Test Suite: 8 Standard Reference REST APIs & Security.

Covers:
1. GET /careers
2. PUT /me/profile
3. GET /careers/data-analyst/requirements
4. POST /submissions (with Idempotency Key deduplication)
5. GET /assessments/{id} (Access control: owner vs unauthorized student)
6. POST /roadmaps
7. PATCH /activities/{id}/progress
8. GET /me/history
9. GET /me/export & DELETE /me/data (GDPR Right to Erasure)
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.store import store

client = TestClient(app)

STUDENT_1_HEADER = {"Authorization": "Bearer token_student_1"}
STUDENT_2_HEADER = {"Authorization": "Bearer token_student_2"}
ADMIN_HEADER = {"Authorization": "Bearer token_admin"}


@pytest.fixture(autouse=True)
def reset_store_state():
    store.reset()


def test_1_get_careers():
    """1. GET /careers returns published Data Analyst career."""
    resp = client.get("/careers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["career_code"] == "DATA_ANALYST"


def test_2_put_me_profile():
    """2. PUT /me/profile updates profile and goals."""
    payload = {
        "target_career_id": "DATA_ANALYST",
        "target_career_version": "v1.0",
        "weekly_hours_budget": 6.0,
        "target_timeline_weeks": 10,
        "major": "Hệ thống Thông tin - HCMUS",
        "self_reported_skills": [{"skill_code": "SQL", "level": 2}]
    }
    resp = client.put("/me/profile", json=payload, headers=STUDENT_1_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["weekly_hours_budget"] == 6.0
    assert data["target_timeline_weeks"] == 10
    assert data["major"] == "Hệ thống Thông tin - HCMUS"


def test_3_get_career_requirements():
    """3. GET /careers/data-analyst/requirements returns 5 skills."""
    resp = client.get("/careers/data-analyst/requirements")
    assert resp.status_code == 200
    data = resp.json()
    assert data["career_code"] == "DATA_ANALYST"
    assert len(data["skills"]) == 5
    assert abs(data["total_weight"] - 1.0) < 1e-4


def test_4_post_submission_and_idempotency():
    """4. POST /submissions with idempotency key deduplication."""
    idemp_key = f"test-idemp-{uuid.uuid4()}"
    payload = {
        "task_id": "DA01A",
        "submission_text": "SELECT * FROM orders; 10 9 8 7 dòng 630.000 540.000 1.170.000 -14.29% Nam 700k Bac 370k Unknown 100k",
        "mode": "ASSESSMENT",
        "idempotency_key": idemp_key
    }

    # First submission -> 201 Created
    resp1 = client.post("/submissions", json=payload, headers=STUDENT_1_HEADER)
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["is_duplicate"] is False
    sub_id = data1["submission_id"]

    # Duplicate submission with same key -> returns cached result with is_duplicate = True
    resp2 = client.post("/submissions", json=payload, headers=STUDENT_1_HEADER)
    assert resp2.status_code == 201 or resp2.status_code == 200
    data2 = resp2.json()
    assert data2["submission_id"] == sub_id
    assert data2["is_duplicate"] is True


def test_5_assessment_authorization_boundary():
    """5. GET /assessments/{id}: unauthorized student cannot access another's assessment."""
    # Student 1 submits
    payload = {
        "task_id": "DA01A",
        "submission_text": "Test submission for student 1",
        "mode": "PRACTICE"
    }
    resp1 = client.post("/submissions", json=payload, headers=STUDENT_1_HEADER)
    sub_id = resp1.json()["submission_id"]

    # Student 1 can view
    resp_owner = client.get(f"/assessments/{sub_id}", headers=STUDENT_1_HEADER)
    assert resp_owner.status_code == 200

    # Student 2 tries to view Student 1's assessment -> 403 Forbidden
    resp_unauth = client.get(f"/assessments/{sub_id}", headers=STUDENT_2_HEADER)
    assert resp_unauth.status_code == 403


def test_6_post_roadmaps():
    """6. POST /roadmaps generates adaptive roadmap."""
    resp = client.post("/roadmaps", headers=STUDENT_1_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "schedule" in data
    assert "evaluation" in data
    assert "scheduled_weeks" in data["schedule"]


def test_7_patch_activity_progress():
    """7. PATCH /activities/{id}/progress updates completion."""
    payload = {
        "status": "COMPLETED",
        "progress_percent": 100,
        "notes": "Hoàn thành toàn bộ bài tập"
    }
    resp = client.patch("/activities/ACT_SQL_01/progress", json=payload, headers=STUDENT_1_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["progress_percent"] == 100


def test_8_get_me_history():
    """8. GET /me/history returns student audit trail."""
    resp = client.get("/me/history", headers=STUDENT_1_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_9_gdpr_export_and_purge():
    """9. GDPR export data and right to erasure."""
    # Export
    resp_exp = client.get("/me/export", headers=STUDENT_1_HEADER)
    assert resp_exp.status_code == 200
    assert "profile" in resp_exp.json()

    # Delete
    resp_del = client.delete("/me/data", headers=STUDENT_1_HEADER)
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "success"
