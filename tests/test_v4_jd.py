"""V4.0 acceptance: JD import, library, mapping, confirmation (JD-01..JD-04, F13-F15)."""
import io
import zipfile

import pytest

from backend.engine.jd_parser import build_target_requirements, extract_jd_text, parse_job_description, validate_jd_text
from backend.store import store
from backend.targeting import resolve_target
from v4_helpers import ADMIN, STUDENT, STUDENT_2, STUDENT_ID, client

JD_VALID = """Vị trí: Data Analyst Intern
Công ty: Công ty Mẫu
Mô tả công việc
- Hỗ trợ tổng hợp số liệu bán hàng hằng tuần.
Yêu cầu
- Thành thạo SQL queries để truy vấn dữ liệu.
- Biết dùng Power BI để xây dashboard.
- Có kinh nghiệm làm sạch dữ liệu.
Ưu tiên
- Biết Python là một lợi thế.
- Excel nâng cao.
Quyền lợi
- Được đào tạo Python miễn phí.
"""
JD_OTHER_ROLE = """Vị trí: Backend Developer
Công ty: Công ty Mẫu
Yêu cầu
- Có kinh nghiệm xây dựng API bằng Java và Spring Boot cho hệ thống lớn.
- Hiểu về microservices, message queue và triển khai dịch vụ trên nền tảng đám mây.
"""
JD_WEAK = """Vị trí: Data Analyst
Yêu cầu
- Làm báo cáo định kỳ cho các phòng ban và phối hợp giao tiếp tốt với đồng nghiệp trong công ty.
- Làm việc chăm chỉ, cẩn thận và chịu được áp lực công việc trong môi trường năng động.
"""


@pytest.fixture(autouse=True)
def fresh():
    store.reset()


def _import(text, **form):
    return client.post("/jds/import", data={"text": text, **form}, headers=STUDENT)


def _docx(*paragraphs):
    buffer = io.BytesIO()
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    return buffer.getvalue()


# JD-01: valid JD with SQL, Python, Power BI
def test_jd01_extracts_requirements_with_source_and_confidence():
    resp = _import(JD_VALID)
    assert resp.status_code == 201
    jd = resp.json()
    assert jd["title"] == "Data Analyst Intern" and jd["employer"] == "Công ty Mẫu" and jd["role_level"] == "INTERN"
    assert jd["review_status"] == "DRAFT" and jd["scope_status"] == "IN_SCOPE" and jd["jd_version"] == 1
    by_skill = {item["skill_code"]: item for item in jd["requirements"] if item["in_catalog"]}
    assert set(by_skill) == {"SQL", "DATA_VIZ", "DATA_QUALITY", "PYTHON"}
    assert by_skill["SQL"]["requirement_type"] == "REQUIRED"
    assert by_skill["PYTHON"]["requirement_type"] == "PREFERRED"
    assert by_skill["DATA_VIZ"]["mapping_rule"] == "TOOL_MAPPING"
    for item in by_skill.values():
        assert item["source_excerpt"] and 0 < item["confidence"] <= 1
    # A benefits line is not a requirement; the source sentence is the real one.
    assert "lợi thế" in by_skill["PYTHON"]["source_excerpt"]
    assert any(item.get("label") == "Excel / Google Sheets" for item in jd["requirements"] if not item["in_catalog"])
    assert jd["preview"].startswith("Vị trí")


def test_synonyms_map_to_one_skill_and_keep_sources():
    parsed = parse_job_description("Vị trí: Data Analyst\nYêu cầu\n- Truy vấn SQL hằng ngày\n- Viết SQL queries cho báo cáo tài chính")
    sql = [item for item in parsed["requirements"] if item["skill_code"] == "SQL"]
    assert len(sql) == 1 and len(sql[0]["source_excerpts"]) == 2


def test_no_level_or_experience_is_inferred():
    parsed = parse_job_description("Vị trí: Senior Data Analyst\nYêu cầu\n- Expert in SQL.\n- Có 5 năm kinh nghiệm.")
    sql = next(item for item in parsed["requirements"] if item["skill_code"] == "SQL")
    assert "target_level" not in sql
    assert parsed["experience_statements"] == ["Có 5 năm kinh nghiệm."]


def test_parenthetical_preference_does_not_downgrade_the_main_skill():
    parsed = parse_job_description("Vị trí: Data Analyst\nYêu cầu\n- Foundational knowledge of SQL and Excel (familiarity with Python is a plus).")
    types = {item["skill_code"]: item["requirement_type"] for item in parsed["requirements"] if item["in_catalog"]}
    assert types == {"SQL": "REQUIRED", "PYTHON": "PREFERRED"}


# JD-02: no upload shows the approved library, never a generated JD
def test_jd02_library_shows_only_approved_sourced_jds():
    data = client.get("/jds/catalog", headers=STUDENT).json()
    assert data["total"] >= 5
    assert all(item["review_status"] == "APPROVED" and item["source_url"] and item["last_checked_at"] for item in data["items"])
    assert "VN_BANKING_ANALYST" not in {item["jd_id"] for item in data["items"]}  # content not verified yet
    assert data["fallback"]["default_target_available"] is True


def test_library_filters():
    interns = client.get("/jds/catalog", params={"role_level": "INTERN"}, headers=STUDENT).json()["items"]
    assert interns and all(item["role_level"] == "INTERN" for item in interns)
    assert client.get("/jds/catalog", params={"q": "không có jd này"}, headers=STUDENT).json()["total"] == 0


def test_expired_or_dead_library_jd_is_hidden():
    store.db.execute("UPDATE jd_versions SET link_status = 'BROKEN' WHERE jd_id = 'TCDATA_INTERN_DA'")
    store.db.execute("UPDATE jd_versions SET next_review_at = '2020-01-01' WHERE jd_id = 'KYANON_INTERN_DA'")
    ids = {item["jd_id"] for item in client.get("/jds/catalog", headers=STUDENT).json()["items"]}
    assert "TCDATA_INTERN_DA" not in ids and "KYANON_INTERN_DA" not in ids


# JD-03: corrupt, empty and unrelated input
@pytest.mark.parametrize("name,data,message", [
    ("jd.exe", b"MZ", "Định dạng chưa hỗ trợ"),
    ("jd.txt", b"", "Tệp rỗng"),
    ("jd.pdf", b"not a pdf at all", "không phải PDF"),
    ("jd.pdf", b"%PDF-1.4 broken", "hỏng"),
    ("jd.docx", b"not a zip", "docx"),
    ("jd.txt", b"\x00\x01\x02binary", "nhị phân"),
])
def test_jd03_bad_files_get_a_clear_error_and_nothing_is_created(name, data, message):
    resp = client.post("/jds/import", files={"file": (name, data)}, headers=STUDENT)
    assert resp.status_code == 422
    assert message.lower() in resp.json()["error"]["message"].lower()
    assert client.get("/jds/mine", headers=STUDENT).json() == []


def test_too_short_or_garbled_text_is_refused():
    assert _import("ngắn quá").status_code == 422
    assert _import("12345 " * 40).status_code == 422


def test_jd03_out_of_scope_is_warned_and_cannot_be_confirmed():
    jd = _import(JD_OTHER_ROLE).json()
    assert jd["scope_status"] == "OUT_OF_SCOPE" and "Backend Developer" in jd["scope_reason"]
    resp = client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": 1, "decisions": []}, headers=STUDENT)
    assert resp.status_code == 409
    assert store.get_or_create_profile(STUDENT_ID).get("target_jd") is None


# JD-04: uncertain keywords need confirmation
def test_jd04_low_confidence_needs_explicit_decision():
    jd = _import(JD_WEAK).json()
    weak = [item for item in jd["requirements"] if item["needs_confirmation"]]
    assert weak and all(item["confidence"] < 0.7 for item in weak)
    resp = client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": 1, "decisions": []}, headers=STUDENT)
    assert resp.status_code == 422 and "độ tin cậy thấp" in resp.json()["error"]["message"]
    decisions = [{"requirement_id": item["requirement_id"], "decision": "CONFIRM", "requirement_type": "REQUIRED"} for item in weak]
    assert client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": 1, "decisions": decisions}, headers=STUDENT).status_code == 200


def test_pdf_docx_and_txt_all_import():
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match="ảnh quét"):
        extract_jd_text("jd.pdf", buffer.getvalue())
    assert "Data Analyst" in extract_jd_text("jd.docx", _docx("Data Analyst", "SQL"))["text"]
    assert extract_jd_text("jd.txt", "Data Analyst SQL".encode("utf-16"))["text"].startswith("Data")
    resp = client.post("/jds/import", files={"file": ("jd.docx", _docx(*JD_VALID.splitlines()))}, headers=STUDENT)
    assert resp.status_code == 201 and resp.json()["file"]["type"] == "docx" and resp.json()["skill_count"] == 4


def test_user_can_edit_results_before_confirming():
    jd = _import(JD_VALID).json()
    sql = next(item for item in jd["requirements"] if item["skill_code"] == "SQL")
    python = next(item for item in jd["requirements"] if item["skill_code"] == "PYTHON")
    decisions = [
        {"requirement_id": sql["requirement_id"], "decision": "REJECT"},
        {"requirement_id": python["requirement_id"], "decision": "CONFIRM", "requirement_type": "REQUIRED"},
        {"decision": "CONFIRM", "skill_code": "WRITTEN_COMM", "requirement_type": "PREFERRED", "source_excerpt": "Tôi muốn thêm"},
    ]
    target = client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": 1, "decisions": decisions}, headers=STUDENT).json()["target"]
    requirements = target["requirements_by_skill"]
    assert requirements["SQL"]["weight"] == 0
    assert requirements["PYTHON"]["requirement_type"] == "REQUIRED"
    assert requirements["WRITTEN_COMM"]["weight"] > 0
    assert sum(item["weight"] for item in requirements.values()) == pytest.approx(1.0)


def test_skill_without_rubric_cannot_become_a_verified_criterion():
    for task in store.tasks:
        task["skills_evaluated"] = [item for item in task["skills_evaluated"] if item["skill_code"] != "DATA_VIZ"]
    jd = _import(JD_VALID).json()
    resp = client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": 1, "decisions": []}, headers=STUDENT)
    assert resp.status_code == 422 and "chưa có rubric" in resp.json()["error"]["message"]


def test_weights_come_from_the_approved_config_and_sum_to_one():
    decisions = [{"skill_code": "SQL", "requirement_type": "REQUIRED"}, {"skill_code": "PYTHON", "requirement_type": "PREFERRED"}]
    result = build_target_requirements(decisions, "INTERN", store.skills)
    assert result["SQL"]["target_level"] == 2 and result["PYTHON"]["target_level"] == 1
    assert result["SQL"]["weight"] == pytest.approx(0.30 / (0.30 + 0.075), abs=1e-3)
    assert sum(item["weight"] for item in result.values()) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        build_target_requirements(decisions, "NOPE", store.skills)


def test_target_is_versioned_and_not_evidence():
    jd = _import(JD_VALID).json()
    first = client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": 1}, headers=STUDENT).json()["target"]
    assert first["target_version"] == 1 and first["jd_id"] == jd["jd_id"] and first["mapping_version"]
    assert store.get_or_create_profile(STUDENT_ID)["assessed_skills"] == {}  # a JD is never evidence
    second = client.post("/me/target-jd", json={"use_default": True}, headers=STUDENT).json()["target"]
    assert second["target_version"] == 2 and second["source_type"] == "DEFAULT"
    data = client.get("/me/target-jd", headers=STUDENT).json()
    assert [item["target_version"] for item in data["versions"]] == [2, 1]
    assert resolve_target(store.get_or_create_profile(STUDENT_ID))["source_type"] == "DEFAULT"


def test_library_jd_can_be_confirmed_and_keeps_approved_levels():
    target = client.post("/me/target-jd", json={"jd_id": "MICROSOFT_PL300_ANALYST", "jd_version": 1}, headers=STUDENT).json()["target"]
    assert target["source_type"] == "JD_LIBRARY" and target["requirements_by_skill"]["DATA_VIZ"]["target_level"] == 3


def test_unapproved_library_jd_cannot_be_read_or_used():
    assert client.get("/jds/VN_BANKING_ANALYST/versions/1", headers=STUDENT).status_code == 404
    assert client.post("/me/target-jd", json={"jd_id": "VN_BANKING_ANALYST", "jd_version": 1}, headers=STUDENT).status_code == 404


def test_another_learners_jd_is_private():
    jd = _import(JD_VALID).json()
    assert client.get(f"/jds/{jd['jd_id']}/versions/1", headers=STUDENT_2).status_code == 404
    assert client.delete(f"/jds/{jd['jd_id']}", headers=STUDENT_2).status_code == 404
    assert client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": 1}, headers=STUDENT_2).status_code == 404
    assert client.delete(f"/jds/{jd['jd_id']}", headers=STUDENT).status_code == 200


def test_same_text_reuses_the_stored_jd():
    first = _import(JD_VALID).json()
    second = _import(JD_VALID).json()
    assert second["is_duplicate"] and second["jd_id"] == first["jd_id"]


def test_admin_review_flow_and_immutable_versions():
    imported = client.post("/admin/jds", data={"text": JD_VALID, "source_url": "https://example.com/jd"}, headers=ADMIN).json()
    jd_id = imported["jd_id"]
    assert jd_id not in {item["jd_id"] for item in client.get("/jds/catalog", headers=STUDENT).json()["items"]}
    # A raw draft has no approved weights yet, so it cannot be approved directly.
    assert client.post(f"/admin/jds/{jd_id}/versions/1/review", json={"review_status": "APPROVED"}, headers=ADMIN).status_code == 409
    revised = client.post(f"/admin/jds/{jd_id}/versions", json={"requirements": [
        {"skill_code": "SQL", "requirement_type": "REQUIRED", "target_level": 2, "weight": 0.7, "is_core": True, "rationale": "SQL"},
        {"skill_code": "DATA_VIZ", "requirement_type": "PREFERRED", "target_level": 2, "weight": 0.3, "rationale": "BI"},
    ]}, headers=ADMIN).json()
    assert revised["jd_version"] == 2 and revised["review_status"] == "DRAFT"
    assert client.post(f"/admin/jds/{jd_id}/versions/2/review", json={"review_status": "APPROVED"}, headers=ADMIN).status_code == 200
    assert jd_id in {item["jd_id"] for item in client.get("/jds/catalog", headers=STUDENT).json()["items"]}
    assert client.get(f"/jds/{jd_id}/versions/1", headers=ADMIN).json()["review_status"] == "DRAFT"
    assert client.get("/admin/jds", headers=STUDENT).status_code == 403


def test_validate_rejects_empty_text():
    with pytest.raises(ValueError):
        validate_jd_text("   ")
