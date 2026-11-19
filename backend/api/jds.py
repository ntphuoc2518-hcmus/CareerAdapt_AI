"""JD management (F13-F15): import, library, immutable versions, review and target confirmation."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from backend import career_process
from backend.auth import AuthenticatedUser, get_current_user, require_admin_user
from backend.clock import utcnow
from backend.database import dumps
from backend.engine.jd_parser import (
    MAPPING, MAPPING_VERSION, MAX_JD_BYTES, build_target_requirements, extract_jd_text, parse_job_description,
    text_hash, validate_jd_text,
)
from backend.engine.link_checker import check_url, validate_public_url
from backend.store import store
from backend.targeting import default_requirements, resolve_target, save_target_version, target_summary

router = APIRouter(tags=["F13-F15 - JD"])
admin_router = APIRouter(prefix="/admin", tags=["F13-F15 - JD Admin"])

REVIEW_STATES = {"DRAFT", "NEEDS_REVIEW", "APPROVED", "EXPIRED"}
CONTENT_REVIEW_DAYS = 90


def _version_row(jd_id: str, version: int) -> dict:
    row = store.db.one("SELECT * FROM jd_versions WHERE jd_id = ? AND jd_version = ?", (jd_id, version))
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản JD.")
    return row


def _jd_row(jd_id: str) -> dict:
    row = store.db.one("SELECT * FROM job_descriptions WHERE jd_id = ?", (jd_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy JD.")
    return row


def _can_read(jd: dict, version: dict, user: AuthenticatedUser) -> bool:
    if user.role == "admin":
        return True
    if jd["origin"] == "USER":
        return jd["owner_user_id"] == str(user.user_id)
    return version["review_status"] == "APPROVED"


def _requirements(jd_id: str, version: int) -> list[dict]:
    rows = store.db.query("SELECT * FROM jd_requirements WHERE jd_id = ? AND jd_version = ? ORDER BY in_catalog DESC, weight DESC, confidence DESC", (jd_id, version))
    result = []
    for row in rows:
        extra = json.loads(row.pop("payload") or "{}")
        result.append({**extra, **row, "in_catalog": bool(row["in_catalog"]), "needs_confirmation": bool(row["needs_confirmation"])})
    return result


def _view(jd: dict, version: dict, include_text: bool = False) -> dict:
    payload = json.loads(version["payload"])
    requirements = _requirements(jd["jd_id"], version["jd_version"])
    data = {
        "jd_id": jd["jd_id"], "jd_version": version["jd_version"], "latest_version": jd["latest_version"], "origin": jd["origin"],
        "title": payload.get("title") or jd["title"], "employer": payload.get("employer") or jd["employer"],
        "role_level": payload.get("role_level") or jd["role_level"], "industry": jd["industry"], "language": jd["language"],
        "source_url": version["source_url"], "source_type": version["source_type"], "source_date": version["source_date"],
        "file_name": version["file_name"], "raw_text_hash": version["raw_text_hash"], "mapping_version": version["mapping_version"],
        "review_status": version["review_status"], "reviewer_id": version["reviewer_id"], "reviewed_at": version["reviewed_at"],
        "last_checked_at": version["last_checked_at"], "next_review_at": version["next_review_at"], "link_status": version["link_status"],
        "scope_status": version["scope_status"], "scope_reason": payload.get("scope_reason"), "warnings": payload.get("warnings", []),
        "responsibilities": payload.get("responsibilities", []), "education": payload.get("education", []),
        "experience_statements": payload.get("experience_statements", []), "description": payload.get("description"),
        "scope_note": payload.get("scope_note"), "sources": payload.get("sources", []), "review_note": payload.get("review_note"),
        "requirements": requirements, "created_at": version["created_at"],
        "skill_count": sum(1 for item in requirements if item["in_catalog"]),
        "unmeasured_count": sum(1 for item in requirements if not item["in_catalog"]),
        "needs_confirmation_count": sum(1 for item in requirements if item["needs_confirmation"]),
    }
    if include_text:
        data["raw_text"] = version["raw_text"]
        data["preview"] = (version["raw_text"] or "")[:1500]
    return data


def _store_requirements(jd_id: str, version: int, requirements: list[dict], config_id: str = "INTERN") -> None:
    config = MAPPING["target_configs"].get(config_id, {}).get("skills", {})
    for item in requirements:
        code = item.get("skill_code")
        extra = {key: item.get(key) for key in ("label", "source_excerpts", "matched_terms", "mentions", "confirmation_reasons", "type_reason")}
        store.db.execute(
            """INSERT INTO jd_requirements(requirement_id, jd_id, jd_version, source_excerpt, normalized_text, requirement_type, skill_code, in_catalog,
                   target_level, weight, confidence, mapping_rule, needs_confirmation, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.get("requirement_id") or f"REQ-{uuid.uuid4().hex[:10]}", jd_id, version, item.get("source_excerpt"), item.get("normalized_text"),
             item["requirement_type"], code, int(bool(item.get("in_catalog"))), (config.get(code) or {}).get("target_level"),
             (config.get(code) or {}).get("base_weight"), item.get("confidence", 0), item.get("mapping_rule"), int(bool(item.get("needs_confirmation"))), dumps(extra)),
        )


def _create_version(jd_id: str, version: int, text: str, parsed: dict, source_url: str, source_type: str, file_name: Optional[str], review_status: str, source_date: str) -> None:
    payload = {key: parsed.get(key) for key in ("title", "employer", "role_level", "scope_reason", "warnings", "responsibilities", "education", "experience_statements")}
    store.db.execute(
        """INSERT INTO jd_versions(jd_id, jd_version, raw_text, raw_text_hash, source_url, source_type, source_date, file_name, mapping_version,
               review_status, link_status, scope_status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (jd_id, version, text, text_hash(text), source_url, source_type, source_date, file_name, MAPPING_VERSION, review_status,
         "UNCHECKED" if source_url else None, parsed["scope_status"], dumps(payload), utcnow().isoformat()),
    )
    _store_requirements(jd_id, version, parsed["requirements"])


async def _read_input(file: Optional[UploadFile], text: Optional[str]) -> tuple[str, Optional[str], Optional[dict]]:
    """Return validated text. Any problem is a 422 with a specific message; nothing is guessed."""
    file_info = None
    file_name = None
    if file is not None and file.filename:
        data = await file.read(MAX_JD_BYTES + 1)
        try:
            extracted = extract_jd_text(file.filename, data)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        raw, file_name = extracted["text"], file.filename[:180]
        file_info = {"name": file_name, "type": extracted["file_type"], "pages": extracted["pages"], "bytes": len(data)}
    elif text and text.strip():
        raw = text
    else:
        raise HTTPException(status_code=422, detail="Hãy tải lên tệp JD hoặc dán nội dung JD.")
    try:
        return validate_jd_text(raw), file_name, file_info
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/jds/import", status_code=status.HTTP_201_CREATED)
async def import_jd(
    file: Optional[UploadFile] = File(default=None),
    text: Optional[str] = Form(default=None),
    title: str = Form(default="", max_length=180),
    employer: str = Form(default="", max_length=180),
    source_url: str = Form(default="", max_length=500),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Tải lên hoặc dán JD; tạo bản nháp kèm kết quả trích xuất để người học xem lại."""
    cleaned, file_name, file_info = await _read_input(file, text)
    parsed = parse_job_description(cleaned, title_hint=title, employer_hint=employer, source_url=source_url)
    digest = text_hash(cleaned)
    existing = store.db.one(
        """SELECT v.jd_id, v.jd_version FROM jd_versions v JOIN job_descriptions j ON j.jd_id = v.jd_id
           WHERE j.owner_user_id = ? AND v.raw_text_hash = ? ORDER BY v.created_at DESC LIMIT 1""",
        (str(current_user.user_id), digest),
    )
    if existing:
        jd = _jd_row(existing["jd_id"])
        return {**_view(jd, _version_row(jd["jd_id"], existing["jd_version"]), include_text=True), "file": file_info, "is_duplicate": True}
    jd_id = f"JD-{uuid.uuid4().hex[:12]}"
    display_title = parsed["title"] or "JD chưa có chức danh"
    today = utcnow().date().isoformat()
    with store.db.transaction():
        store.db.execute(
            "INSERT INTO job_descriptions(jd_id, origin, owner_user_id, title, employer, role_level, language, latest_version, created_at) VALUES (?, 'USER', ?, ?, ?, ?, ?, 1, ?)",
            (jd_id, str(current_user.user_id), display_title, parsed["employer"], parsed["role_level"], None, utcnow().isoformat()),
        )
        _create_version(jd_id, 1, cleaned, parsed, parsed["source_url"], "USER_PROVIDED", file_name, "DRAFT", today)
    store.add_history_event(current_user.user_id, "JD_IMPORTED", f"Nhập JD: {display_title}", meta={"jd_id": jd_id, "jd_version": 1})
    jd = _jd_row(jd_id)
    return {**_view(jd, _version_row(jd_id, 1), include_text=True), "file": file_info, "is_duplicate": False}


@router.get("/jds/catalog")
def jd_catalog(
    role_level: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    sort: Literal["updated", "title"] = "updated",
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Thư viện JD đã duyệt. Nguồn hỏng hoặc quá hạn rà soát bị ẩn khỏi lựa chọn mặc định."""
    now = utcnow().isoformat()
    rows = store.db.query(
        """SELECT j.*, v.jd_version AS version_number FROM job_descriptions j
           JOIN jd_versions v ON v.jd_id = j.jd_id
           WHERE j.origin = 'LIBRARY' AND v.review_status = 'APPROVED' AND COALESCE(v.link_status, 'OK') != 'BROKEN'
             AND (v.next_review_at IS NULL OR v.next_review_at >= ?)""",
        (now[:10],),
    )
    latest: dict[str, dict] = {}
    for row in rows:
        if row["jd_id"] not in latest or row["version_number"] > latest[row["jd_id"]]["version_number"]:
            latest[row["jd_id"]] = row
    items = [_view(row, _version_row(row["jd_id"], row["version_number"])) for row in latest.values()]
    filters = {"role_level": role_level, "industry": industry, "language": language}
    for key, value in filters.items():
        if value:
            items = [item for item in items if (item.get(key) or "").casefold() == value.casefold()]
    if q:
        needle = q.casefold()
        items = [item for item in items if needle in f"{item['title']} {item.get('employer') or ''} {item.get('industry') or ''}".casefold()]
    items.sort(key=(lambda item: item["title"].casefold()) if sort == "title" else (lambda item: item.get("last_checked_at") or ""), reverse=sort == "updated")
    return {
        "items": items,
        "total": len(items),
        "filters": {
            "role_levels": sorted({row["role_level"] for row in latest.values() if row["role_level"]}),
            "industries": sorted({row["industry"] for row in latest.values() if row["industry"]}),
            "languages": sorted({row["language"] for row in latest.values() if row["language"]}),
        },
        "fallback": {"default_target_available": True, "message": "Nếu thư viện không có JD phù hợp, bạn có thể nhập JD của mình hoặc dùng bộ mục tiêu mặc định đã duyệt."},
    }


@router.get("/jds/mine")
def my_jds(current_user: AuthenticatedUser = Depends(get_current_user)):
    rows = store.db.query("SELECT * FROM job_descriptions WHERE owner_user_id = ? ORDER BY created_at DESC", (str(current_user.user_id),))
    return [_view(row, _version_row(row["jd_id"], row["latest_version"])) for row in rows]


@router.get("/jds/config")
def jd_config(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Danh mục kỹ năng và các cấu hình mức mục tiêu đã duyệt để chọn khi xác nhận JD."""
    measurable = _measurable_skills()
    return {
        "mapping_version": MAPPING_VERSION,
        "low_confidence_threshold": MAPPING["low_confidence_threshold"],
        "target_configs": [{"config_id": key, "label": value["label"], "description": value["description"], "skills": value["skills"]} for key, value in MAPPING["target_configs"].items()],
        "skills": [{"skill_code": skill["skill_code"], "skill_name": skill["skill_name"], "has_rubric": skill["skill_code"] in measurable, "is_core": bool(skill.get("is_core"))} for skill in store.skills],
    }


@router.get("/jds/{jd_id}/versions")
def jd_versions(jd_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    jd = _jd_row(jd_id)
    rows = store.db.query("SELECT * FROM jd_versions WHERE jd_id = ? ORDER BY jd_version DESC", (jd_id,))
    visible = [row for row in rows if _can_read(jd, row, current_user)]
    if not visible:
        raise HTTPException(status_code=404, detail="Không tìm thấy JD.")
    return [_view(jd, row) for row in visible]


@router.get("/jds/{jd_id}/versions/{version}")
def jd_version(jd_id: str, version: int, current_user: AuthenticatedUser = Depends(get_current_user)):
    jd = _jd_row(jd_id)
    row = _version_row(jd_id, version)
    if not _can_read(jd, row, current_user):
        if jd["origin"] == "USER":
            store.log_security_event(current_user.user_id, "JD_ACCESS_DENIED", jd_id)
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản JD.")
    return _view(jd, row, include_text=jd["origin"] == "USER" or current_user.role == "admin")


@router.delete("/jds/{jd_id}")
def delete_my_jd(jd_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Xóa JD đã nhập. Mục tiêu đã xác nhận vẫn giữ bản sao yêu cầu đã chuẩn hóa."""
    jd = _jd_row(jd_id)
    if jd["origin"] != "USER" or jd["owner_user_id"] != str(current_user.user_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy JD.")
    with store.db.transaction():
        for table in ("jd_requirements", "jd_versions", "job_descriptions"):
            store.db.execute(f"DELETE FROM {table} WHERE jd_id = ?", (jd_id,))
    store.add_history_event(current_user.user_id, "JD_DELETED", f"Xóa JD đã nhập: {jd['title']}")
    return {"message": "Đã xóa JD.", "jd_id": jd_id}


def _measurable_skills() -> set[str]:
    """Skills with a published assessment: only these can become verified target criteria.

    A skill marked ``assessed_by: EXAM`` has no task of its own; its rubric is its questions in the Career Adapt exam bank."""
    from backend.engine.exam_grader import BANK

    by_task = {
        item.get("skill_code") for task in store.tasks if task.get("status", "PUBLISHED").upper() == "PUBLISHED"
        for item in task.get("skills_evaluated", [])
    }
    in_exam = {item["skill_code"] for item in BANK["items"]}
    return by_task | {skill["skill_code"] for skill in store.skills if skill.get("assessed_by") == "EXAM" and skill["skill_code"] in in_exam}


class RequirementDecision(BaseModel):
    requirement_id: Optional[str] = Field(default=None, max_length=60)
    decision: Literal["CONFIRM", "REJECT"] = "CONFIRM"
    skill_code: Optional[str] = Field(default=None, max_length=40)
    requirement_type: Optional[Literal["REQUIRED", "PREFERRED", "UNSPECIFIED"]] = None
    source_excerpt: Optional[str] = Field(default=None, max_length=300)


class TargetRequest(BaseModel):
    jd_id: Optional[str] = Field(default=None, max_length=60)
    jd_version: Optional[int] = None
    use_default: bool = False
    config_id: str = Field(default="INTERN", max_length=20)
    decisions: list[RequirementDecision] = Field(default_factory=list, max_length=60)
    confirm_scope: bool = False


def _confirm_user_jd(jd: dict, version: dict, body: TargetRequest) -> dict:
    if version["scope_status"] == "OUT_OF_SCOPE":
        raise HTTPException(status_code=409, detail="JD này không thuộc nhóm Data Analyst nên không thể dùng làm mục tiêu. Hãy chọn JD khác.")
    if version["scope_status"] == "UNCERTAIN" and not body.confirm_scope:
        raise HTTPException(status_code=409, detail="Hãy xác nhận đây là JD Data Analyst trước khi lưu mục tiêu.")
    requirements = _requirements(jd["jd_id"], version["jd_version"])
    by_id = {item["requirement_id"]: item for item in requirements}
    decisions = {item.requirement_id: item for item in body.decisions if item.requirement_id}
    unknown = set(decisions) - set(by_id)
    if unknown:
        raise HTTPException(status_code=422, detail="Có yêu cầu không thuộc phiên bản JD này.")
    measurable = _measurable_skills()
    missing = [item for item in requirements if item["needs_confirmation"] and item["in_catalog"] and item["requirement_id"] not in decisions]
    if missing:
        names = ", ".join(item["skill_code"] for item in missing)
        raise HTTPException(status_code=422, detail=f"Hãy xác nhận hoặc loại bỏ các yêu cầu độ tin cậy thấp: {names}.")
    confirmed: list[dict] = []
    unmeasured: list[str] = []
    for item in requirements:
        decision = decisions.get(item["requirement_id"])
        if decision and decision.decision == "REJECT":
            continue
        if not item["in_catalog"]:
            unmeasured.append(item.get("label") or item.get("normalized_text") or "")
            continue
        code = (decision.skill_code if decision and decision.skill_code else item["skill_code"])
        requirement_type = (decision.requirement_type if decision and decision.requirement_type else item["requirement_type"])
        confirmed.append({"skill_code": code, "requirement_type": requirement_type, "source_excerpt": item.get("source_excerpt"), "requirement_id": item["requirement_id"]})
    for extra in body.decisions:
        if extra.requirement_id or extra.decision != "CONFIRM":
            continue
        if not extra.skill_code:
            raise HTTPException(status_code=422, detail="Yêu cầu thêm thủ công phải chọn kỹ năng.")
        confirmed.append({"skill_code": extra.skill_code, "requirement_type": extra.requirement_type or "REQUIRED", "source_excerpt": extra.source_excerpt or "Do người học thêm.", "requirement_id": None})
    catalog = {skill["skill_code"] for skill in store.skills}
    for item in confirmed:
        if item["skill_code"] not in catalog:
            raise HTTPException(status_code=422, detail=f"Kỹ năng {item['skill_code']} không có trong danh mục.")
        if item["skill_code"] not in measurable:
            raise HTTPException(status_code=422, detail=f"Kỹ năng {item['skill_code']} chưa có rubric nên không thể đặt làm tiêu chí đã kiểm chứng.")
    if not confirmed:
        raise HTTPException(status_code=422, detail="Cần xác nhận ít nhất một kỹ năng trong danh mục để lập mục tiêu.")
    try:
        requirements_by_skill = build_target_requirements(confirmed, body.config_id, store.skills)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {
        "requirements_by_skill": requirements_by_skill,
        "additional_requirements": [label for label in unmeasured if label],
        "confirmed_requirements": confirmed,
    }


@router.post("/me/target-jd")
def confirm_target(body: TargetRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Xác nhận JD/mục tiêu. JD chỉ mô tả yêu cầu, không phải bằng chứng năng lực."""
    career_process.guard_step(current_user.user_id, "JD", "đổi JD")
    profile = store.get_or_create_profile(current_user.user_id)
    if body.use_default:
        target = {
            "source_type": "DEFAULT", "name": f"Bộ mục tiêu {store.career_metadata['career_title']} mặc định", "jd_id": "DEFAULT_DATA_ANALYST",
            "jd_version": store.career_metadata["version_tag"], "mapping_version": MAPPING_VERSION, "config_id": "DEFAULT",
            "requirements_by_skill": default_requirements(), "additional_requirements": [],
        }
    else:
        if not body.jd_id or body.jd_version is None:
            raise HTTPException(status_code=422, detail="Hãy chọn JD và phiên bản, hoặc dùng bộ mục tiêu mặc định.")
        jd = _jd_row(body.jd_id)
        version = _version_row(body.jd_id, body.jd_version)
        if not _can_read(jd, version, current_user):
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản JD.")
        if jd["origin"] == "LIBRARY":
            if version["review_status"] != "APPROVED":
                raise HTTPException(status_code=409, detail="JD này chưa được duyệt nên không thể dùng làm mục tiêu.")
            payload = json.loads(version["payload"])
            built = {"requirements_by_skill": payload.get("requirements_by_skill") or {}, "additional_requirements": payload.get("additional_requirements", [])}
            if not built["requirements_by_skill"]:
                built = _confirm_user_jd(jd, version, body)
        else:
            built = _confirm_user_jd(jd, version, body)
        view = _view(jd, version)
        target = {
            "source_type": "JD_LIBRARY" if jd["origin"] == "LIBRARY" else "JD_USER",
            "name": " — ".join(part for part in (view["title"], view.get("employer")) if part),
            "jd_id": jd["jd_id"], "jd_version": version["jd_version"], "mapping_version": version["mapping_version"],
            "config_id": "LIBRARY" if jd["origin"] == "LIBRARY" else body.config_id, "employer": view.get("employer"), "role_level": view.get("role_level"),
            **built,
        }
    saved = save_target_version(current_user.user_id, target)
    profile["target_jd"] = saved
    profile["updated_at"] = utcnow().isoformat()
    store.persist_user_runtime(current_user.user_id)
    store.add_history_event(
        current_user.user_id, "TARGET_CONFIRMED", f"Xác nhận mục tiêu: {saved['name']} (phiên bản mục tiêu {saved['target_version']})",
        version=str(saved.get("mapping_version")), meta={"jd_id": saved.get("jd_id"), "jd_version": saved.get("jd_version"), "target_version": saved["target_version"]},
    )
    career_process.on_target_confirmed(current_user.user_id, saved)
    return {"target": saved, "summary": target_summary(saved), "notice": "JD chỉ mô tả yêu cầu mục tiêu; hệ thống chưa coi bạn đã có các kỹ năng này. Hãy làm bài đánh giá để có bằng chứng."}


@router.get("/me/jd-matches")
def jd_matches(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Mức đáp ứng của năng lực đã xác thực với từng JD đã duyệt trong thư viện."""
    from backend.jd_matching import matches

    return matches(current_user.user_id)


@router.get("/me/target-jd")
def get_target(current_user: AuthenticatedUser = Depends(get_current_user)):
    profile = store.get_or_create_profile(current_user.user_id)
    target = resolve_target(profile)
    rows = store.db.query("SELECT payload FROM target_versions WHERE user_id = ? AND archived_by_run IS NULL ORDER BY version DESC", (str(current_user.user_id),))
    return {"target": target, "summary": target_summary(target), "versions": [json.loads(row["payload"]) for row in rows]}


# ---------------------------------------------------------------------------
# Administrator: library review
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    review_status: Literal["DRAFT", "NEEDS_REVIEW", "APPROVED", "EXPIRED"]
    note: str = Field(default="", max_length=1000)


class LibraryRequirement(BaseModel):
    skill_code: str = Field(max_length=40)
    requirement_type: Literal["REQUIRED", "PREFERRED"]
    target_level: int = Field(ge=1, le=3)
    weight: float = Field(gt=0, le=1)
    is_core: bool = False
    rationale: str = Field(default="", max_length=400)


class RevisionRequest(BaseModel):
    requirements: list[LibraryRequirement] = Field(min_length=1, max_length=20)
    additional_requirements: list[str] = Field(default_factory=list, max_length=30)
    note: str = Field(default="", max_length=1000)


@admin_router.get("/jds")
def admin_list_jds(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    rows = store.db.query("SELECT * FROM job_descriptions WHERE origin = 'LIBRARY' ORDER BY title")
    return [_view(row, _version_row(row["jd_id"], row["latest_version"])) for row in rows]


@admin_router.post("/jds", status_code=status.HTTP_201_CREATED)
async def admin_import_jd(
    file: Optional[UploadFile] = File(default=None),
    text: Optional[str] = Form(default=None),
    title: str = Form(default="", max_length=180),
    employer: str = Form(default="", max_length=180),
    source_url: str = Form(default="", max_length=500),
    source_type: str = Form(default="PUBLIC_LISTING", max_length=40),
    industry: str = Form(default="", max_length=80),
    language: str = Form(default="vi", max_length=10),
    admin_user: AuthenticatedUser = Depends(require_admin_user),
):
    """Thêm JD vào thư viện ở trạng thái nháp; chỉ JD đã duyệt mới hiện với người học."""
    cleaned, file_name, _ = await _read_input(file, text)
    parsed = parse_job_description(cleaned, title_hint=title, employer_hint=employer, source_url=source_url)
    jd_id = f"LIB-{uuid.uuid4().hex[:10]}"
    with store.db.transaction():
        store.db.execute(
            "INSERT INTO job_descriptions(jd_id, origin, title, employer, role_level, industry, language, latest_version, created_at) VALUES (?, 'LIBRARY', ?, ?, ?, ?, ?, 1, ?)",
            (jd_id, parsed["title"] or "JD chưa có chức danh", parsed["employer"], parsed["role_level"], industry or None, language, utcnow().isoformat()),
        )
        _create_version(jd_id, 1, cleaned, parsed, parsed["source_url"], source_type, file_name, "DRAFT", utcnow().date().isoformat())
    return _view(_jd_row(jd_id), _version_row(jd_id, 1), include_text=True)


@admin_router.post("/jds/{jd_id}/versions/{version}/review")
def admin_review_jd(jd_id: str, version: int, body: ReviewRequest, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    jd = _jd_row(jd_id)
    row = _version_row(jd_id, version)
    if jd["origin"] != "LIBRARY":
        raise HTTPException(status_code=409, detail="JD do người học nhập không đi qua luồng duyệt thư viện.")
    payload = json.loads(row["payload"])
    if body.review_status == "APPROVED":
        if not row["source_url"] and row["source_type"] != "CERTIFICATION_STANDARD":
            raise HTTPException(status_code=409, detail="JD cần có nguồn đối chiếu trước khi duyệt.")
        if row["scope_status"] == "OUT_OF_SCOPE":
            raise HTTPException(status_code=409, detail="JD ngoài phạm vi Data Analyst không thể đưa vào thư viện.")
        requirements = payload.get("requirements_by_skill") or {}
        weights = [float(item.get("weight", 0)) for item in requirements.values()]
        if not requirements or abs(sum(weights) - 1.0) > 0.001:
            raise HTTPException(status_code=409, detail="Cần chuẩn hóa yêu cầu (tổng trọng số bằng 100%) trước khi duyệt. Hãy tạo phiên bản đã chuẩn hóa.")
    now = utcnow()
    next_review = (now + timedelta(days=CONTENT_REVIEW_DAYS)).date().isoformat() if body.review_status == "APPROVED" else row["next_review_at"]
    payload["review_note"] = body.note
    store.db.execute(
        "UPDATE jd_versions SET review_status = ?, reviewer_id = ?, reviewed_at = ?, next_review_at = ?, payload = ? WHERE jd_id = ? AND jd_version = ?",
        (body.review_status, admin_user.email, now.isoformat(), next_review, dumps(payload), jd_id, version),
    )
    return _view(jd, _version_row(jd_id, version))


@admin_router.post("/jds/{jd_id}/versions", status_code=status.HTTP_201_CREATED)
def admin_revise_jd(jd_id: str, body: RevisionRequest, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Chuẩn hóa yêu cầu tạo phiên bản mới; phiên bản đã dùng trong đánh giá không bị sửa đè."""
    jd = _jd_row(jd_id)
    if jd["origin"] != "LIBRARY":
        raise HTTPException(status_code=409, detail="Chỉ JD trong thư viện mới dùng luồng này.")
    catalog = {skill["skill_code"] for skill in store.skills}
    if {item.skill_code for item in body.requirements} - catalog:
        raise HTTPException(status_code=422, detail="Có kỹ năng không thuộc danh mục.")
    if abs(sum(item.weight for item in body.requirements) - 1.0) > 0.001:
        raise HTTPException(status_code=422, detail="Tổng trọng số phải bằng 100%.")
    previous = _version_row(jd_id, jd["latest_version"])
    payload = json.loads(previous["payload"])
    payload["requirements_by_skill"] = {item.skill_code: item.model_dump(exclude={"skill_code"}) for item in body.requirements}
    payload["additional_requirements"] = body.additional_requirements
    payload["review_note"] = body.note
    version = jd["latest_version"] + 1
    with store.db.transaction():
        store.db.execute(
            """INSERT INTO jd_versions(jd_id, jd_version, raw_text, raw_text_hash, source_url, source_type, source_date, file_name, mapping_version,
                   review_status, link_status, scope_status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?)""",
            (jd_id, version, previous["raw_text"], previous["raw_text_hash"], previous["source_url"], previous["source_type"], previous["source_date"],
             previous["file_name"], MAPPING_VERSION, previous["link_status"], previous["scope_status"], dumps(payload), utcnow().isoformat()),
        )
        for item in body.requirements:
            store.db.execute(
                """INSERT INTO jd_requirements(requirement_id, jd_id, jd_version, source_excerpt, normalized_text, requirement_type, skill_code, in_catalog,
                       target_level, weight, confidence, mapping_rule, needs_confirmation, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 1.0, 'CURATED', 0, '{}')""",
                (f"REQ-{uuid.uuid4().hex[:10]}", jd_id, version, item.rationale, item.rationale, item.requirement_type, item.skill_code, item.target_level, item.weight),
            )
        store.db.execute("UPDATE job_descriptions SET latest_version = ? WHERE jd_id = ?", (version, jd_id))
    return _view(_jd_row(jd_id), _version_row(jd_id, version))


@admin_router.post("/jds/{jd_id}/check-link")
def admin_check_jd_link(jd_id: str, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    jd = _jd_row(jd_id)
    row = _version_row(jd_id, jd["latest_version"])
    if not row["source_url"]:
        raise HTTPException(status_code=409, detail="JD này không có URL nguồn.")
    result = check_url(row["source_url"])
    store.db.execute(
        "UPDATE jd_versions SET link_status = ?, last_checked_at = ? WHERE jd_id = ? AND jd_version = ?",
        (result["link_status"], utcnow().isoformat(), jd_id, jd["latest_version"]),
    )
    return {**result, "jd": _view(jd, _version_row(jd_id, jd["latest_version"]))}
