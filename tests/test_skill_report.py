"""Skill report: analysis suggestions, file import, confirm-and-lock, description edits."""
import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.engine.skill_report import analyze_experience, extract_text_from_upload
from backend.main import app
from backend.store import store

client = TestClient(app)
STUDENT = {"Authorization": "Bearer token_student_1"}
EXPERIENCE = """Kinh nghiệm:
- Viết truy vấn SQL với JOIN và GROUP BY để tổng hợp doanh thu hằng tháng.
- Dùng window function ROW_NUMBER() OVER (PARTITION BY region) để xếp hạng cửa hàng.
- Làm sạch dữ liệu: xử lý trùng lặp và giá trị thiếu bằng pandas.
- Dự án: xây dựng dashboard Power BI theo dõi KPI bán hàng cho phòng kinh doanh.
"""
JD = "We are hiring a Data Analyst. Required: strong SQL, Power BI dashboards, data cleaning and stakeholder communication. Python is a plus."


@pytest.fixture(autouse=True)
def fresh_profile():
    store.reset()
    yield
    store.reset()


def test_experience_analysis_suggests_levels_with_evidence():
    result = analyze_experience(EXPERIENCE, store.skills)
    by_code = {item["skill_code"]: item for item in result["suggestions"]}
    assert by_code["SQL"]["suggested_level"] == 3          # select/join + window function
    assert by_code["DATA_VIZ"]["suggested_level"] == 2     # dashboard / Power BI
    assert by_code["WRITTEN_COMM"]["suggested_level"] == 0
    assert any("ROW_NUMBER" in sentence for sentence in by_code["SQL"]["evidence"])
    assert any("dashboard" in product.lower() for product in result["products"])


def test_single_buzzword_does_not_jump_to_level_3():
    result = analyze_experience("Tôi biết window function.", store.skills)
    sql = next(item for item in result["suggestions"] if item["skill_code"] == "SQL")
    assert sql["suggested_level"] == 0


def test_docx_and_txt_import():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml",
                         '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                         '<w:p><w:r><w:t>Dùng SQL JOIN</w:t></w:r></w:p><w:p><w:r><w:t>Power BI</w:t></w:r></w:p></w:body></w:document>')
    assert extract_text_from_upload("cv.docx", buffer.getvalue()) == "Dùng SQL JOIN\nPower BI"
    assert extract_text_from_upload("cv.txt", "Xin chào".encode("utf-8")) == "Xin chào"
    with pytest.raises(ValueError):
        extract_text_from_upload("cv.pdf", b"%PDF")


def test_docx_with_dtd_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", '<!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
    with pytest.raises(ValueError):
        extract_text_from_upload("cv.docx", buffer.getvalue())


def test_analyze_endpoint_merges_jd_and_experience():
    resp = client.post("/api/v1/me/skill-report/analyze", headers=STUDENT, json={"jd_text": JD, "experience_text": EXPERIENCE})
    assert resp.status_code == 200
    data = resp.json()
    sql = next(item for item in data["suggestions"] if item["skill_code"] == "SQL")
    assert sql["in_jd"] and sql["recommended"] and sql["jd_requirement_type"] == "REQUIRED"
    # A JD never sets a level on its own.
    assert "jd_target_level" not in sql
    assert client.post("/api/v1/me/skill-report/analyze", headers=STUDENT, json={"jd_text": "ngắn"}).status_code == 422


def test_upload_endpoint():
    resp = client.post("/api/v1/me/skill-report/extract-text", headers=STUDENT,
                       files={"file": ("cv.txt", "SQL và Power BI".encode("utf-8"), "text/plain")})
    assert resp.status_code == 200 and resp.json()["text"] == "SQL và Power BI"


def test_confirm_locks_levels_but_allows_description_edit():
    assert client.get("/api/v1/me/skill-report", headers=STUDENT).json()["confirmed"] is False
    body = {"skills": [{"skill_code": "SQL", "level": 2, "description": "JOIN, GROUP BY"},
                       {"skill_code": "DATA_VIZ", "level": 1}],
            "products": ["Dashboard Power BI bán hàng"]}
    resp = client.post("/api/v1/me/skill-report/confirm", headers=STUDENT, json=body)
    assert resp.status_code == 200 and resp.json()["confirmed"]

    # Asking for the same input again is refused.
    assert client.post("/api/v1/me/skill-report/confirm", headers=STUDENT, json=body).status_code == 409
    # The legacy profile form cannot change confirmed levels either.
    profile = client.get("/me/profile", headers=STUDENT).json()
    client.put("/me/profile", headers=STUDENT, json={**profile, "self_reported_skills": [{"skill_code": "SQL", "level": 3}]})
    levels = {s["skill_code"]: s["level"] for s in client.get("/api/v1/me/skill-report", headers=STUDENT).json()["skills"]}
    assert levels == {"SQL": 2, "DATA_VIZ": 1}

    edited = client.patch("/api/v1/me/skill-report/skills/SQL", headers=STUDENT, json={"description": "Thêm CTE và window function"})
    assert edited.status_code == 200
    sql = next(s for s in edited.json()["skills"] if s["skill_code"] == "SQL")
    assert sql["evidence_note"] == "Thêm CTE và window function" and sql["level"] == 2
    assert client.patch("/api/v1/me/skill-report/skills/PYTHON", headers=STUDENT, json={"description": "x"}).status_code == 404


def test_confirm_rejects_unknown_or_duplicate_skills():
    bad = {"skills": [{"skill_code": "SQL", "level": 1}, {"skill_code": "SQL", "level": 2}]}
    assert client.post("/api/v1/me/skill-report/confirm", headers=STUDENT, json=bad).status_code == 422
    bad = {"skills": [{"skill_code": "COOKING", "level": 1}]}
    assert client.post("/api/v1/me/skill-report/confirm", headers=STUDENT, json=bad).status_code == 422
