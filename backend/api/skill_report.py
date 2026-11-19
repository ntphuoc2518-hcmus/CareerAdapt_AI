"""Skill report: the first stage of the learner journey.

- POST /me/skill-report/extract-text   upload .pdf/.txt/.md/.csv/.docx -> plain text (nothing stored)
- POST /me/skill-report/analyze        JD and/or experience text -> suggested skills, levels, products
- GET  /me/skill-report                current report (confirmed or not)
- POST /me/skill-report/confirm        save chosen skills + confidence levels; locks the report
- PATCH /me/skill-report/skills/{code} after confirmation only the description can change

Raw JD/CV text is never persisted; only the learner's confirmed choices are.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from backend import career_process
from backend.auth import AuthenticatedUser, get_current_user
from backend.engine.jd_parser import parse_job_description
from backend.engine.skill_report import MAX_UPLOAD_BYTES, analyze_experience, extract_text_from_upload
from backend.store import store

router = APIRouter(tags=["Skill report - Báo cáo kỹ năng"])


class AnalyzeRequest(BaseModel):
    jd_title: str = Field(default="Data Analyst", max_length=180)
    jd_text: str = Field(default="", max_length=30000)
    experience_text: str = Field(default="", max_length=30000)


class ConfirmedSkill(BaseModel):
    skill_code: str = Field(min_length=1, max_length=40)
    level: int = Field(ge=0, le=3)
    description: str = Field(default="", max_length=600)


class ConfirmRequest(BaseModel):
    skills: list[ConfirmedSkill] = Field(min_length=1, max_length=20)
    products: list[str] = Field(default_factory=list, max_length=10)
    method: str = Field(default="FORM", pattern="^(FORM|IMPORT|PICK)$")


class DescriptionUpdate(BaseModel):
    description: str = Field(max_length=600)


def _report(profile: dict) -> dict:
    report = profile.get("skill_report") or {}
    return {
        "confirmed": bool(report.get("confirmed_at")),
        "confirmed_at": report.get("confirmed_at"),
        "skills": profile.get("self_reported_skills", []),
        "products": report.get("products", []),
        "job_profile_id": profile.get("job_profile_id"),
    }


@router.post("/me/skill-report/extract-text")
async def extract_text(file: UploadFile = File(...), current_user: AuthenticatedUser = Depends(get_current_user)):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        text = extract_text_from_upload(file.filename or "", data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if not text.strip():
        raise HTTPException(status_code=422, detail="Tệp không có nội dung văn bản.")
    return {"text": text, "characters": len(text)}


@router.post("/me/skill-report/analyze")
def analyze(body: AnalyzeRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    if len(body.jd_text.strip()) < 40 and len(body.experience_text.strip()) < 20:
        raise HTTPException(status_code=422, detail="Hãy dán JD (ít nhất 40 ký tự) hoặc mô tả kinh nghiệm (ít nhất 20 ký tự).")
    experience = analyze_experience(body.experience_text, store.skills)
    jd_requirements: dict[str, str] = {}
    additional: list[str] = []
    if len(body.jd_text.strip()) >= 40:
        parsed = parse_job_description(body.jd_text, title_hint=body.jd_title)
        jd_requirements = {item["skill_code"]: item["requirement_type"] for item in parsed["requirements"] if item["in_catalog"]}
        additional = [item["label"] for item in parsed["requirements"] if not item["in_catalog"]]
        if not jd_requirements and not body.experience_text.strip():
            raise HTTPException(status_code=422, detail="Chưa nhận diện được kỹ năng Data Analyst trong JD.")
    for suggestion in experience["suggestions"]:
        suggestion["in_jd"] = suggestion["skill_code"] in jd_requirements
        suggestion["jd_requirement_type"] = jd_requirements.get(suggestion["skill_code"])
        # Recommend reviewing every skill the JD asks for or the experience mentions.
        suggestion["recommended"] = suggestion["in_jd"] or suggestion["detected"]
    experience["suggestions"].sort(key=lambda item: (not item["recommended"], not item["in_jd"], -item["suggested_level"]))
    return {
        **experience,
        "additional_requirements": additional,
        "notice": "Gợi ý dựa trên từ khóa trong văn bản bạn cung cấp. Hãy kiểm tra và tự chọn mức độ phù hợp; mức tự khai không thay thế bài đánh giá.",
    }


@router.get("/me/skill-report")
def get_report(current_user: AuthenticatedUser = Depends(get_current_user)):
    return _report(store.get_or_create_profile(current_user.user_id))


@router.post("/me/skill-report/confirm")
def confirm(body: ConfirmRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    career_process.guard_step(current_user.user_id, "SKILLS", "sửa kỹ năng đã khai báo")
    profile = store.get_or_create_profile(current_user.user_id)
    if (profile.get("skill_report") or {}).get("confirmed_at"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Báo cáo kỹ năng đã được xác nhận. Bạn chỉ có thể sửa phần mô tả.")
    known = {skill["skill_code"] for skill in store.skills}
    codes = [item.skill_code for item in body.skills]
    if len(set(codes)) != len(codes) or not set(codes) <= known:
        raise HTTPException(status_code=422, detail="Danh sách kỹ năng không hợp lệ.")
    now = datetime.now(timezone.utc).isoformat()
    profile["self_reported_skills"] = [
        {"skill_code": item.skill_code, "level": item.level, "evidence_note": item.description.strip()} for item in body.skills
    ]
    profile["skill_report"] = {"confirmed_at": now, "products": [p.strip()[:220] for p in body.products if p.strip()]}
    profile["updated_at"] = now
    store.add_history_event(current_user.user_id, "SKILL_REPORT_CONFIRMED", f"Xác nhận báo cáo {len(codes)} kỹ năng")
    store.persist_user_runtime(current_user.user_id)
    career_process.on_skills_confirmed(current_user.user_id, body.method)
    return _report(profile)


@router.patch("/me/skill-report/skills/{skill_code}")
def update_description(skill_code: str, body: DescriptionUpdate, current_user: AuthenticatedUser = Depends(get_current_user)):
    career_process.guard_step(current_user.user_id, "SKILLS", "sửa kỹ năng đã khai báo")
    profile = store.get_or_create_profile(current_user.user_id)
    if not (profile.get("skill_report") or {}).get("confirmed_at"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Hãy xác nhận báo cáo kỹ năng trước.")
    skill = next((item for item in profile.get("self_reported_skills", []) if item["skill_code"] == skill_code), None)
    if not skill:
        raise HTTPException(status_code=404, detail="Kỹ năng không có trong báo cáo.")
    skill["evidence_note"] = body.description.strip()
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    store.persist_user_runtime(current_user.user_id)
    return _report(profile)
