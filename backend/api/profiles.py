"""Interactive Profile & Goal Environment Endpoints (F01).

Implements:
- PUT /me/profile: Profile & learning goals update
- GET /me/history: History log of assessments and roadmap events
- GET /me/export: GDPR personal data export (JSON/CSV)
- DELETE /me/data, DELETE /me/profile: GDPR right to erasure
"""
from __future__ import annotations
import re
import uuid
import math
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend import career_process
from backend.ai_service.assistant import list_conversations, messages_of
from backend.auth import AuthenticatedUser, get_current_user
from backend.store import store
from backend.targeting import resolve_target

router = APIRouter(tags=["F01 - Profile & Privacy"])


class ProfileUpdateRequest(BaseModel):
    target_career_id: str = "DATA_ANALYST"
    target_career_version: Optional[str] = Field(default="v4.0", description="Phiên bản khung năng lực mục tiêu")
    job_profile_id: str = Field(default="VN_ENTRY_ANALYST", description="Hồ sơ yêu cầu nghề nghiệp tham chiếu")
    weekly_hours_budget: float = Field(default=4.0, gt=0, le=40, description="Số giờ có thể học mỗi tuần")
    target_timeline_weeks: int = Field(default=8, ge=1, le=52, description="Thời hạn mong muốn (tuần)")
    major: Optional[str] = "Công nghệ thông tin / Toán tin"
    self_reported_skills: list[dict] = Field(
        default_factory=list,
        description="Danh sách kỹ năng tự khai (gắn nhãn 'Tự khai', không thay thế bằng chứng)"
    )
    custom_job_profile: Optional[dict] = Field(default=None, description="Chuẩn yêu cầu đã phân tích từ JD do người học cung cấp")


class ProfileResponse(BaseModel):
    user_id: uuid.UUID
    target_career_id: str
    target_career_version: str
    job_profile_id: str = "VN_ENTRY_ANALYST"
    job_profile_name: str = ""
    weekly_hours_budget: float
    target_timeline_weeks: int
    major: Optional[str]
    self_reported_skills: list[dict]
    assessed_skills: dict
    custom_job_profile: Optional[dict] = None
    updated_at: str
    message: str


@router.put("/me/profile", response_model=ProfileResponse)
def update_profile(
    body: ProfileUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Cập nhật thông tin hồ sơ, mục tiêu nghề nghiệp và kỹ năng tự khai (UC-01)."""
    now = datetime.now(timezone.utc)
    profile = store.get_or_create_profile(current_user.user_id)
    if career_process.active_run(current_user.user_id):
        # Skills and target belong to the process; the profile form only keeps hours and major here.
        profile["weekly_hours_budget"] = body.weekly_hours_budget
        profile["target_timeline_weeks"] = body.target_timeline_weeks
        profile["major"] = body.major
        profile["updated_at"] = now.isoformat()
        store.persist_user_runtime(current_user.user_id)
        return {**{key: profile.get(key) for key in ("user_id", "target_career_id", "target_career_version", "job_profile_id", "weekly_hours_budget", "target_timeline_weeks", "major", "self_reported_skills", "assessed_skills", "custom_job_profile", "updated_at")}, "job_profile_name": "", "message": "Cập nhật hồ sơ học viên thành công."}

    custom_job_profile = body.custom_job_profile or profile.get("custom_job_profile")
    if body.job_profile_id == "CUSTOM_JOB_DESCRIPTION":
        if not isinstance(custom_job_profile, dict):
            raise HTTPException(status_code=422, detail="Hãy phân tích và áp dụng một JD trước khi chọn hồ sơ tùy chỉnh.")
        requirements = custom_job_profile.get("requirements_by_skill", {})
        known_codes = {skill["skill_code"] for skill in store.skills}
        if not isinstance(requirements, dict) or set(requirements) != known_codes:
            raise HTTPException(status_code=422, detail="Chuẩn JD phải có cấu hình cho toàn bộ kỹ năng trong khung hiện tại.")
        total_weight = 0.0
        for code, requirement in requirements.items():
            try:
                level = int(requirement["target_level"])
                weight = float(requirement["weight"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"Cấu hình kỹ năng {code} không hợp lệ.")
            if level < 1 or level > 3 or not math.isfinite(weight) or weight < 0 or weight > 1:
                raise HTTPException(status_code=422, detail=f"Mức hoặc trọng số kỹ năng {code} nằm ngoài giới hạn.")
            total_weight += weight
        if abs(total_weight - 1.0) > 0.001:
            raise HTTPException(status_code=422, detail="Tổng trọng số kỹ năng trong chuẩn JD phải bằng 100%.")
        custom_job_profile["profile_id"] = "CUSTOM_JOB_DESCRIPTION"
        profile["custom_job_profile"] = custom_job_profile
    elif not store.get_job_profile(body.job_profile_id):
        raise HTTPException(status_code=422, detail="Hồ sơ yêu cầu nghề nghiệp không hợp lệ.")
    elif body.custom_job_profile is not None:
        profile["custom_job_profile"] = body.custom_job_profile

    profile["target_career_id"] = body.target_career_id
    profile["target_career_version"] = body.target_career_version or "v4.0"
    profile["job_profile_id"] = body.job_profile_id
    profile["weekly_hours_budget"] = body.weekly_hours_budget
    profile["target_timeline_weeks"] = body.target_timeline_weeks
    profile["major"] = body.major
    # Once the skill report is confirmed, levels are locked; descriptions change via /me/skill-report.
    if not (profile.get("skill_report") or {}).get("confirmed_at"):
        profile["self_reported_skills"] = body.self_reported_skills
    profile["updated_at"] = now.isoformat()
    store.persist_user_runtime(current_user.user_id)

    store.add_history_event(
        current_user.user_id,
        "UPDATE_PROFILE",
        f"Cập nhật quỹ thời gian học: {body.weekly_hours_budget}h/tuần, thời hạn: {body.target_timeline_weeks} tuần",
        version=profile["target_career_version"]
    )

    return ProfileResponse(
        user_id=current_user.user_id,
        target_career_id=profile["target_career_id"],
        target_career_version=profile["target_career_version"],
        job_profile_id=profile.get("job_profile_id", "VN_ENTRY_ANALYST"),
        job_profile_name=(
            profile.get("custom_job_profile", {}).get("name", "")
            if profile.get("job_profile_id") == "CUSTOM_JOB_DESCRIPTION"
            else (store.get_job_profile(profile.get("job_profile_id", "VN_ENTRY_ANALYST")) or {}).get("name", "")
        ),
        weekly_hours_budget=profile["weekly_hours_budget"],
        target_timeline_weeks=profile["target_timeline_weeks"],
        major=profile["major"],
        self_reported_skills=profile["self_reported_skills"],
        assessed_skills=profile.get("assessed_skills", {}),
        custom_job_profile=profile.get("custom_job_profile"),
        updated_at=profile["updated_at"],
        message="Cập nhật hồ sơ học viên thành công."
    )


@router.get("/me/profile")
def get_profile(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Lấy thông tin hồ sơ học viên hiện tại."""
    profile = store.get_or_create_profile(current_user.user_id)
    return profile


@router.post("/me/diagnostics")
@router.get("/me/diagnostics")
def run_profile_diagnostics(current_user: AuthenticatedUser = Depends(get_current_user)):
    """AI chẩn đoán hồ sơ ban đầu & đề xuất bài test thực tế (User Journey Step 2)."""
    profile = store.get_or_create_profile(current_user.user_id)
    self_skills = {s["skill_code"]: s.get("level", 1) for s in profile.get("self_reported_skills", [])}
    assessed_skills = profile.get("assessed_skills", {})
    
    # Analyze strengths & gaps
    strengths = []
    unverified = []
    target = resolve_target(profile)
    job_profile = target
    role_requirements = target.get("requirements_by_skill", {})
    for s in store.skills:
        code = s["skill_code"]
        if float(role_requirements.get(code, {}).get("weight", 0.0)) <= 0:
            continue
        if code in assessed_skills:
            strengths.append(f"{s['skill_name']} (Đã có bằng chứng Thực chứng Level {assessed_skills[code]['level']})")
        elif code in self_skills:
            unverified.append(f"{s['skill_name']} (Tự khai Level {self_skills[code]} - Chưa được kiểm chứng qua bài test)")
        else:
            unverified.append(f"{s['skill_name']} (Chưa khai báo & Chưa đánh giá)")

    # Rank published assessments by the weighted requirement gap of this role.
    skill_need: dict[str, float] = {}
    for skill in store.skills:
        code = skill["skill_code"]
        requirement = role_requirements.get(code, {})
        weight = float(requirement.get("weight", skill.get("weight", 0.0)))
        target_level = int(requirement.get("target_level", skill.get("target_level", 1)))
        if weight <= 0 or target_level <= 0:
            continue
        # An unmeasured skill needs evidence most; that is a reason to test it, not a measured gap.
        current = assessed_skills.get(code, {}).get("level")
        need = 1.0 if current is None else max(0, target_level - int(current)) / target_level
        if need:
            skill_need[code] = weight * need

    task_scores = []
    for task in store.tasks:
        if task.get("status", "PUBLISHED").upper() != "PUBLISHED":
            continue
        if task.get("is_reassessment_variant") and task.get("comparability_status") != "APPROVED":
            continue
        score = sum(skill_need.get(item.get("skill_code"), 0.0) for item in task.get("skills_evaluated", []))
        if score > 0:
            task_scores.append((score, task))
    recommended_task = max(task_scores, key=lambda item: (item[0], item[1].get("task_id", "")))[1] if task_scores else None
    recommendation = None
    if recommended_task:
        recommended_codes = [item.get("skill_code") for item in recommended_task.get("skills_evaluated", [])]
        recommendation = {
            "task_id": recommended_task["task_id"],
            "title": recommended_task["title"],
            "skills": recommended_codes,
            "estimated_minutes": recommended_task.get("estimated_duration_minutes", 35),
            "reason": f"Bài đánh giá này đo các kỹ năng còn thiếu có trọng số cao nhất cho mục tiêu '{job_profile.get('name', 'Data Analyst')}'."
        }

    return {
        "user_id": current_user.user_id,
        "major": profile.get("major"),
        "weekly_hours_budget": profile.get("weekly_hours_budget", 4.0),
        "job_profile_id": profile.get("job_profile_id", "VN_ENTRY_ANALYST"),
        "job_profile_name": job_profile.get("name", ""),
        "target_timeline_weeks": profile.get("target_timeline_weeks", 8),
        "ai_diagnosis_summary": f"Mục tiêu: {job_profile.get('name', 'Data Analyst')}. Học viên ngành '{profile.get('major')}' có quỹ thời gian {profile.get('weekly_hours_budget')}h/tuần. Yêu cầu kỹ năng được đối chiếu theo hồ sơ đã chọn; kỹ năng tự khai cần bài kiểm tra thực chứng để trở thành bằng chứng.",
        "strengths_identified": strengths,
        "unverified_skills": unverified,
        "recommended_task": recommendation
    }


@router.get("/me/history")
def get_user_history(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Lấy nhật ký hoạt động và lịch sử đánh giá của học viên."""
    return list(reversed(store.history_events(current_user.user_id)))


@router.get("/me/skill-history")
def get_skill_history(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Thay đổi mức kỹ năng theo thời gian, kèm nguồn bằng chứng và phiên bản JD."""
    return store.skill_evidence(current_user.user_id)


# Activity log groups: every event belongs to exactly one, so the filter counts add up to the total.
LOG_GROUPS = {
    "PROCESS": ("PROCESS_STARTED", "PROCESS_COMPLETED", "PROCESS_RESET", "GOAL_CHANGE_STARTED", "GOAL_CHANGED", "TARGET_CONFIRMED", "JD_IMPORTED", "JD_DELETED",
                "SKILL_REPORT_CONFIRMED", "UPDATE_PROFILE"),
    "ASSESS": ("EXAM_STARTED", "SUBMIT_ASSESSMENT", "SUBMIT_PRACTICE", "TEST_STARTED", "TEST_SUBMITTED", "MINI_TEST_SUBMITTED", "LESSON_CHECK_ISSUED", "LESSON_CHECK_SUBMITTED",
               "FINAL_STARTED", "FINAL_GRADED", "GRADING_FAILED", "ADMIN_REVIEW_RESOLVED", "LEVEL_RECONFIRMED"),
    "LEARN": ("STUDY_STARTED", "STUDY_ENDED", "UPDATE_PROGRESS", "GENERATE_ROADMAP", "ROADMAP_REPLANNED"),
    "REMIND": ("CYCLE_SET", "CYCLE_POSTPONED", "CYCLE_CANCELLED", "REMINDER_SNOOZED", "REVIEW_SCHEDULED"),
}
_GROUP_OF = {event: group for group, events in LOG_GROUPS.items() for event in events}
_STATUS_WORDS = {"NOT_STARTED": "chưa bắt đầu", "IN_PROGRESS": "đang học", "COMPLETED": "hoàn thành"}


def _readable_detail(detail: str) -> str:
    """Older log lines hold a lesson id and a status code; show the lesson name and plain words instead."""
    text = re.sub(r"\bACT_[A-Z0-9_]+\b", lambda match: (store.get_activity(match.group(0)) or {}).get("title") or match.group(0), detail or "")
    return re.sub(r"\b(NOT_STARTED|IN_PROGRESS|COMPLETED)\b", lambda match: _STATUS_WORDS[match.group(0)], text)


@router.get("/me/activity-log")
def get_activity_log(group: Optional[str] = Query(default=None, max_length=20), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0, le=100000),
                     current_user: AuthenticatedUser = Depends(get_current_user)):
    """Nhật ký hoạt động: mới nhất trước, lọc theo nhóm, tải từng trang."""
    if group is not None and group not in LOG_GROUPS and group != "OTHER":
        raise HTTPException(status_code=422, detail="Nhóm nhật ký không hợp lệ.")
    events = list(reversed(store.history_events(current_user.user_id)))
    counts = {name: 0 for name in (*LOG_GROUPS, "OTHER")}
    for item in events:
        counts[_GROUP_OF.get(item["event"], "OTHER")] += 1
    chosen = [item for item in events if group is None or _GROUP_OF.get(item["event"], "OTHER") == group]
    page = chosen[offset:offset + limit]
    return {
        "items": [{"event_id": item["event_id"], "event": item["event"], "group": _GROUP_OF.get(item["event"], "OTHER"), "time": item["time"], "detail": _readable_detail(item["detail"])} for item in page],
        "total": len(chosen), "all_total": len(events), "counts": counts, "offset": offset, "limit": limit, "has_more": offset + len(page) < len(chosen),
    }


@router.get("/me/skill-progress")
def get_skill_progress(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Mức từng kỹ năng theo bằng chứng: mức hiện tại, mức đầu, thay đổi và từng lần ghi nhận."""
    evidence = store.skill_evidence(current_user.user_id)
    requirements = resolve_target(store.get_or_create_profile(current_user.user_id)).get("requirements_by_skill", {})
    skills: dict[str, dict] = {}
    for row in evidence:
        code = row["skill_code"]
        skill = skills.setdefault(code, {"skill_code": code, "skill_name": (store.get_skill(code) or {}).get("skill_name") or code, "entries": []})
        previous = skill["entries"][-1]["level"] if skill["entries"] else None
        skill["entries"].append({"evidence_id": row["evidence_id"], "created_at": row["created_at"], "level": int(row["level"]), "previous_level": previous,
                                 "delta": None if previous is None else int(row["level"]) - previous, "score": row["score"], "source_type": row["source_type"]})
    out = []
    for code, skill in skills.items():
        entries = skill["entries"]
        target = (requirements.get(code) or {}).get("target_level")
        current, first = entries[-1]["level"], entries[0]["level"]
        out.append({**skill, "current_level": current, "first_level": first, "change": current - first, "target_level": target,
                    "meets_target": None if target is None else current >= int(target), "last_at": entries[-1]["created_at"], "entries": list(reversed(entries))})
    # Skills the target asks for come first, in the order of the target; the rest follow by name.
    order = {code: index for index, code in enumerate(requirements)}
    out.sort(key=lambda item: (order.get(item["skill_code"], len(order)), item["skill_name"]))
    return {"skills": out, "total_entries": len(evidence), "raised": sum(1 for item in out if item["change"] > 0), "lowered": sum(1 for item in out if item["change"] < 0),
            "met": sum(1 for item in out if item["meets_target"]), "with_target": sum(1 for item in out if item["target_level"] is not None), "max_level": 3}


@router.get("/me/assessment-reliability")
def get_assessment_reliability(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Độ tin cậy của mức từng kỹ năng: bao nhiêu bài làm và loại kiểm tra nào đứng sau mức hiện tại. Không đổi mức."""
    from backend.assessment_reliability import reliability

    return reliability(current_user.user_id)


@router.get("/me/assessment-policy")
def get_assessment_policy(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Mọi ngưỡng đạt và thời gian chờ của quy tắc đánh giá, đúng số máy chủ đang áp dụng."""
    from backend.assessment_policy import describe

    return {"rules": describe()}


@router.get("/me/export")
def export_user_data(current_user: AuthenticatedUser = Depends(get_current_user)):
    """GDPR Data Portability: Tải về toàn bộ hồ sơ, bài nộp, đánh giá và lộ trình học tập."""
    user_id = current_user.user_id
    profile = store.get_or_create_profile(user_id)
    history = store.history_events(user_id)

    user_submissions = [s for s in store.submissions.values() if s.get("user_id") == user_id]
    answers = store.db.query(
        "SELECT a.submission_id, a.question_id, a.answer_text FROM submission_answers a "
        "JOIN assessment_attempts t ON t.submission_id = a.submission_id WHERE t.user_id = ?", (str(user_id),)
    )
    user_assessments = [a for a in store.assessments.values() if a.get("user_id") == user_id]
    user_roadmap = store.roadmaps.get(user_id)
    user_roadmap_history = store.roadmap_history(user_id)

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_info": {
            "user_id": str(user_id),
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role
        },
        "profile": profile,
        "submissions": user_submissions,
        "submission_answers": answers,
        "assessments": user_assessments,
        "skill_evidence": store.skill_evidence(user_id),
        "roadmap": user_roadmap,
        "roadmap_history": user_roadmap_history,
        "career_runs": store.db.query("SELECT run_id, career_code, status, step, created_at, completed_at, archived_at, payload FROM career_runs WHERE user_id = ?", (str(user_id),)),
        "assistant_conversations": [messages_of(user_id, item["conversation_id"]) for item in list_conversations(user_id)],
        "audit_history": history
    }


@router.delete("/me/data", status_code=status.HTTP_200_OK)
@router.delete("/me/profile", status_code=status.HTTP_200_OK)
def delete_user_data(current_user: AuthenticatedUser = Depends(get_current_user)):
    """GDPR Right to Erasure: Xóa vĩnh viễn toàn bộ dữ liệu cá nhân, bài làm và lịch sử."""
    count = store.purge_user_data(current_user.user_id)
    return {
        "status": "success",
        "message": f"Toàn bộ dữ liệu cá nhân của người dùng ({current_user.email}) đã được xóa vĩnh viễn.",
        "records_purged": count
    }
