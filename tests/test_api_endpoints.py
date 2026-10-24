"""Integration and End-to-End API tests for CareerAdapt AI FastAPI Backend (TV3).

Verifies all F01 to F10 endpoints, security ownership, and idempotency.
"""
import pytest
import sys
import os
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

STUDENT_TOKEN = "Bearer token_student_1"
STUDENT_2_TOKEN = "Bearer token_student_2"
ADMIN_TOKEN = "Bearer token_admin"


class TestAPIEndpoints:

    def test_health_check(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "TV3" in data["tech_lead"]

    def test_auth_unauthorized_access(self):
        """Endpoints requiring authentication return 401 when no token is supplied."""
        resp = client.get("/api/v1/profiles/me")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "HTTP_401"

    def test_f01_profile_endpoints(self):
        """F01: Get and update user profile goals."""
        headers = {"Authorization": STUDENT_TOKEN}
        
        # 1. Get profile (initializes default)
        resp = client.get("/api/v1/profiles/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_career_id"] == "DATA_ANALYST"
        assert data["weekly_hours_budget"] == 10.0

        # 2. Update profile goals & self-reported skills
        update_payload = {
            "target_career_id": "DATA_ANALYST",
            "weekly_hours_budget": 12.0,
            "target_timeline_weeks": 10,
            "self_reported_skills": [
                {"skill_id": "SQL", "claimed_level": 2},
                {"skill_id": "PYTHON", "claimed_level": 1}
            ]
        }
        put_resp = client.put("/api/v1/profiles/me", json=update_payload, headers=headers)
        assert put_resp.status_code == 200
        put_data = put_resp.json()
        assert put_data["weekly_hours_budget"] == 12.0
        assert put_data["target_timeline_weeks"] == 10
        # Check self-reported flag (Principle 1.1)
        assert put_data["self_reported_skills"][0]["is_self_reported"] is True

    def test_f02_career_catalog(self):
        """F02: Catalog endpoints return skills framework and tasks."""
        resp = client.get("/api/v1/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["career_id"] == "DATA_ANALYST"
        assert len(data["skills"]) == 5
        assert len(data["tasks"]) == 3

        # Check total weights sum to 1.0
        weights_sum = sum(s["weight"] for s in data["skills"])
        assert pytest.approx(weights_sum, 0.001) == 1.0

        # Check core skills are marked
        core_skills = [s["skill_id"] for s in data["skills"] if s["is_core"]]
        assert "SQL" in core_skills
        assert "DATA_QUALITY" in core_skills

    def test_f03_submission_and_f04_assessment_flow(self):
        """F03 & F04: Submit solution, verify evidence quote and idempotency."""
        headers = {"Authorization": STUDENT_TOKEN}

        # 1. Text submission with SQL syntax
        sub_payload = {
            "task_version_id": "DA01",
            "submission_text": "SELECT region, sum(revenue) FROM sales WHERE status = 'completed' GROUP BY region;",
            "mode": "ASSESSMENT",
            "idempotency_key": "unique_key_test_001"
        }
        resp = client.post("/api/v1/submissions", json=sub_payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        sub_id = data["submission_id"]
        assert data["processing_status"] == "COMPLETED"

        # 2. Idempotency test: submit again with exact same key -> returns existing submission
        resp_idem = client.post("/api/v1/submissions", json=sub_payload, headers=headers)
        assert resp_idem.status_code == 201
        assert resp_idem.json()["submission_id"] == sub_id
        assert "Idempotency matched" in resp_idem.json()["message"]

        # 3. Retrieve Assessment (F04)
        ass_resp = client.get(f"/api/v1/assessments/by-submission/{sub_id}", headers=headers)
        assert ass_resp.status_code == 200
        ass_data = ass_resp.json()
        assert ass_data["status"] == "ACCEPTED"
        assert len(ass_data["scores"]) >= 2
        # Verify that evidence was verified
        for s in ass_data["scores"]:
            if s["has_valid_evidence"]:
                assert s["evidence_quote"] != ""

    def test_f03_file_upload_submission(self):
        """F03: Upload CSV/SQL file submission with security validation."""
        headers = {"Authorization": STUDENT_TOKEN}
        file_content = b"import pandas as pd\ndf = pd.read_csv('data.csv')\nimport matplotlib.pyplot as plt\nplt.plot(df['rev'])\n"
        
        files = {
            "file": ("solution.py.sql", io.BytesIO(file_content), "text/plain")
        }
        data = {
            "task_version_id": "DA02",
            "mode": "ASSESSMENT",
            "idempotency_key": "file_key_001"
        }
        resp = client.post("/api/v1/submissions/upload", data=data, files=files, headers=headers)
        assert resp.status_code == 201
        res = resp.json()
        assert res["file_metadata"]["file_type"] == "SQL"
        assert res["file_metadata"]["size_bytes"] == len(file_content)

    def test_security_ownership_check(self):
        """Student 2 cannot view Student 1's submission (Ownership check)."""
        headers_1 = {"Authorization": STUDENT_TOKEN}
        headers_2 = {"Authorization": STUDENT_2_TOKEN}

        # Create submission by Student 1
        sub_payload = {
            "task_version_id": "DA01",
            "submission_text": "SELECT * FROM sales WHERE amount > 0;",
            "mode": "ASSESSMENT"
        }
        resp1 = client.post("/api/v1/submissions", json=sub_payload, headers=headers_1)
        sub_id = resp1.json()["submission_id"]

        # Student 2 attempts to fetch status of Student 1's submission -> 403 Forbidden!
        resp2 = client.get(f"/api/v1/submissions/{sub_id}", headers=headers_2)
        assert resp2.status_code == 403
        assert "không có quyền" in resp2.json()["error"]["message"].lower()

    def test_f05_evaluation_summary(self):
        """F05: Calculate gap, coverage, priority, and readiness."""
        headers = {"Authorization": STUDENT_TOKEN}
        resp = client.get("/api/v1/evaluation/summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "coverage" in data
        assert "is_readiness_eligible" in data
        assert len(data["skills_analysis"]) == 5

    def test_f06_roadmap_dag_generation(self):
        """F06: Generate topological roadmap respecting weekly hours budget."""
        headers = {"Authorization": STUDENT_TOKEN}
        resp = client.post("/api/v1/roadmap/generate", headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["total_weeks"] > 0
        assert len(data["schedule"]) > 0

        # Retrieve latest roadmap
        latest_resp = client.get("/api/v1/roadmap/latest", headers=headers)
        assert latest_resp.status_code == 200
        assert latest_resp.json()["roadmap_version_id"] == data["roadmap_version_id"]

    def test_f07_progress_tracking(self):
        """F07: Update and retrieve progress without auto-increasing skill levels."""
        headers = {"Authorization": STUDENT_TOKEN}
        payload = {
            "activity_id": "ACT_SQL_01",
            "new_status": "COMPLETED",
            "hours_spent": 4.0
        }
        resp = client.put("/api/v1/progress", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed_count"] >= 1
        assert data["percentage"] > 0.0

    def test_f08_reassessment_comparison(self):
        """F08: Compare two assessments on the same task."""
        headers = {"Authorization": STUDENT_TOKEN}

        # Submission 1
        p1 = {"task_version_id": "DA01", "submission_text": "SELECT x FROM y;"}
        sub1_id = client.post("/api/v1/submissions", json=p1, headers=headers).json()["submission_id"]

        # Submission 2
        p2 = {"task_version_id": "DA01", "submission_text": "SELECT x, sum(z) FROM y WHERE z > 0 GROUP BY x;"}
        sub2_id = client.post("/api/v1/submissions", json=p2, headers=headers).json()["submission_id"]

        # Compare
        resp = client.get(
            f"/api/v1/reassessment/compare?previous_submission_id={sub1_id}&current_submission_id={sub2_id}",
            headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_comparable"] is True
        assert len(data["comparison"]) > 0

    def test_f09_content_admin_governance(self):
        """F09: Only Admin can publish content; duplicate version raises 409 Conflict."""
        # Non-admin student attempts to publish -> 403 Forbidden
        pub_payload = {
            "content_type": "RUBRIC",
            "content_id": "DA01_RUBRIC",
            "version": "v1.0",
            "comment": "Chốt rubric DA01"
        }
        student_resp = client.post("/api/v1/admin/content/publish", json=pub_payload, headers={"Authorization": STUDENT_TOKEN})
        assert student_resp.status_code == 403

        # Admin publishes -> 200 OK
        admin_resp = client.post("/api/v1/admin/content/publish", json=pub_payload, headers={"Authorization": ADMIN_TOKEN})
        assert admin_resp.status_code == 200
        assert admin_resp.json()["status"] == "PUBLISHED"

        # Admin publishes identical version again -> 409 Conflict (Immutability rule)
        conflict_resp = client.post("/api/v1/admin/content/publish", json=pub_payload, headers={"Authorization": ADMIN_TOKEN})
        assert conflict_resp.status_code == 409

    def test_f10_in_app_reminders_deduplication(self):
        """F10: In-app reminders prevent duplicate spamming."""
        headers = {"Authorization": STUDENT_TOKEN}
        rem_payload = {
            "reminder_type": "ACTIVITY_DUE",
            "message": "Đã đến hạn hoàn thành bài thực hành SQL tuần 1",
            "target_id": "ACT_SQL_01"
        }
        # 1. Create reminder
        r1 = client.post("/api/v1/reminders", json=rem_payload, headers=headers)
        assert r1.status_code == 201
        rem_id = r1.json()["reminder_id"]

        # 2. Duplicate create call with same type & target_id -> returns same reminder
        r2 = client.post("/api/v1/reminders", json=rem_payload, headers=headers)
        assert r2.status_code == 201
        assert r2.json()["reminder_id"] == rem_id

        # 3. List reminders
        list_resp = client.get("/api/v1/reminders", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["unread_count"] >= 1

        # 4. Mark as read
        patch_resp = client.patch(f"/api/v1/reminders/{rem_id}/read", headers=headers)
        assert patch_resp.status_code == 200
        assert patch_resp.json()["is_read"] is True
