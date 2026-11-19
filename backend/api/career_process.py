"""Career Adapt process API. Skills and JD are confirmed through /me/skill-report and /me/target-jd."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend import career_process, exam_service, insights
from backend.api.roadmaps import build_roadmap
from backend.auth import AuthenticatedUser, get_current_user, require_admin_user
from backend.career_process import STEP_LABELS, STEPS
from backend.store import store

router = APIRouter(prefix="/career-process", tags=["Quy trình Career Adapt"])
OPTIONS = json.loads((Path(__file__).resolve().parents[2] / "data" / "skill_level_options_v5.json").read_text(encoding="utf-8"))


class StartRequest(BaseModel):
    career_code: str = Field(max_length=40)


class ResponseBody(BaseModel):
    text: str = Field(default="", max_length=20000)
    # When the page last saw this answer saved ("" = never); a newer save from another tab is then not overwritten.
    base_saved_at: Optional[str] = Field(default=None, max_length=64)


class RunBody(BaseModel):
    question_id: str = Field(max_length=20)
    code: str = Field(min_length=1, max_length=20000)


class ExamEvent(BaseModel):
    kind: Literal["focus_lost", "focus_returned", "paste_blocked", "copy_blocked"]
    detail: str = Field(default="", max_length=200)


class SubmitBody(BaseModel):
    fault_injection: Optional[str] = None


class RoadmapBody(BaseModel):
    weekly_hours: float = Field(ge=0.5, le=40)
    timeline_weeks: int = Field(ge=1, le=52)


class VisibilityBody(BaseModel):
    visible: bool


class SalaryBand(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    value: float = Field(gt=0, le=1000)


class SalarySource(BaseModel):
    label: str = Field(min_length=3, max_length=200)
    url: str = Field(min_length=10, max_length=500, pattern=r"^https?://[^\s<>]+$")
    survey_period: str = Field(default="", max_length=120)
    sample_size: Optional[int] = Field(default=None, ge=1, le=10_000_000)
    checked_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class SalaryBody(BaseModel):
    """Lương tham khảo phải có nguồn công khai; không nguồn thì không được hiển thị."""
    role_label: str = Field(min_length=2, max_length=160)
    statistic: str = Field(min_length=2, max_length=60)
    unit: str = Field(min_length=1, max_length=40)
    bands: list[SalaryBand] = Field(min_length=1, max_length=8)
    overall: Optional[SalaryBand] = None
    missing_note: str = Field(default="", max_length=300)
    scope_note: str = Field(default="", max_length=400)
    source: SalarySource


class ResetBody(BaseModel):
    confirm: bool = False


@router.get("/state")
def state(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Trạng thái quy trình của chính tài khoản này, do máy chủ quyết định."""
    run = career_process.active_run(current_user.user_id)
    attempt = exam_service.current_attempt(current_user.user_id) if run else None
    run = career_process.active_run(current_user.user_id)
    profile = store.get_or_create_profile(current_user.user_id)
    return {
        "careers": list(career_process.CAREERS), "steps": [{"code": code, "label": STEP_LABELS[code]} for code in STEPS], "run": career_process.public_run(run),
        "exam_status": attempt["status"] if attempt else None, "archived_runs": len(career_process.run_history(current_user.user_id)),
        "weekly_hours": profile.get("weekly_hours_budget"), "timeline_weeks": profile.get("target_timeline_weeks"),
    }


@router.get("/skill-options")
def skill_options(current_user: AuthenticatedUser = Depends(get_current_user)):
    return {"skills": [{"skill_code": skill["skill_code"], "skill_name": skill["skill_name"], "options": OPTIONS["skills"].get(skill["skill_code"], [])} for skill in store.skills]}


@router.post("/runs", status_code=201)
def start_run(body: StartRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Bắt đầu quy trình. Nghề mô phỏng và tài khoản đã có quy trình đều bị từ chối."""
    return career_process.public_run(career_process.start_run(current_user.user_id, body.career_code))


@router.post("/exam/start")
def start_exam(current_user: AuthenticatedUser = Depends(get_current_user)):
    return exam_service.public_state(exam_service.start(current_user.user_id))


@router.get("/exam")
def read_exam(current_user: AuthenticatedUser = Depends(get_current_user)):
    attempt = exam_service.current_attempt(current_user.user_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Chưa có bài kiểm tra.")
    return exam_service.public_state(attempt)


@router.put("/exam/responses/{question_id}")
def save_response(question_id: str, body: ResponseBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Lưu câu trả lời trên máy chủ khi chuyển câu hoặc khi đang gõ."""
    return exam_service.save_response(current_user.user_id, question_id, body.text, body.base_saved_at)


@router.post("/exam/run")
def run_code(body: RunBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Chạy thử SQL hoặc Python trên dữ liệu của đề, trong tiến trình cách ly. Không chấm điểm."""
    return exam_service.run_code(current_user.user_id, body.question_id, body.code)


@router.post("/exam/events")
def exam_event(body: ExamEvent, current_user: AuthenticatedUser = Depends(get_current_user)):
    return exam_service.record_event(current_user.user_id, body.kind, body.detail)


@router.post("/exam/submit")
def submit_exam(body: SubmitBody = SubmitBody(), current_user: AuthenticatedUser = Depends(get_current_user)):
    """Nộp bài một lần duy nhất. Lần gọi lặp lại không chấm lại, chỉ báo trùng."""
    from backend.api.submissions import fault_injection_allowed

    return exam_service.submit(current_user.user_id, fault_injection=body.fault_injection if fault_injection_allowed() else None)


@router.get("/exam/review")
def exam_review(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Xem lại bài đã khóa, kèm giải thích từng câu và kết luận trình độ."""
    return exam_service.review(current_user.user_id)


@router.post("/result/confirm")
def confirm_result(current_user: AuthenticatedUser = Depends(get_current_user)):
    run = career_process.guard_step(current_user.user_id, "RESULT", "xác nhận kết quả")
    if run is None:
        raise HTTPException(status_code=404, detail="Chưa có quy trình.")
    return career_process.public_run(career_process.advance(run, "RESULT"))


@router.post("/roadmap")
def create_roadmap(body: RoadmapBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Bước cuối: tạo lộ trình theo kết quả đã xác thực rồi hoàn tất quy trình."""
    user_id = current_user.user_id
    run = career_process.guard_step(user_id, "ROADMAP", "tạo lộ trình")
    if run is None:
        raise HTTPException(status_code=404, detail="Chưa có quy trình.")
    profile = store.get_or_create_profile(user_id)
    profile["weekly_hours_budget"] = body.weekly_hours
    profile["target_timeline_weeks"] = body.timeline_weeks
    existing = store.roadmaps.get(user_id) or {}
    if run["payload"].get("goal_history") and existing.get("schedule"):
        # A changed goal: lessons already passed and confirmed stay done; only what the new JD still needs is planned.
        from backend.api.roadmaps import verified_lessons
        roadmap = build_roadmap(user_id, completed_override=verified_lessons(user_id, existing.get("activity_plan") or {}), reason="Đổi JD mục tiêu")
    else:
        roadmap = build_roadmap(user_id)
    finished = career_process.advance(run, "ROADMAP", roadmap={"roadmap_id": str(roadmap["roadmap_id"]), "roadmap_version": roadmap["roadmap_version"], "weekly_hours": body.weekly_hours, "timeline_weeks": body.timeline_weeks})
    store.add_history_event(user_id, "PROCESS_COMPLETED", "Hoàn tất Quy trình Career Adapt.")
    return career_process.public_run(finished)


@router.get("/insights")
def read_insights(rank_basis: Literal["exam", "current"] = "exam", skill: Optional[str] = Query(default=None, max_length=30),
                  current_user: AuthenticatedUser = Depends(get_current_user)):
    """Cách phân bậc, vị trí xếp hạng (theo bài đầu vào hoặc năng lực hiện tại, toàn bộ hay một kỹ năng), lương tham khảo và nguồn."""
    try:
        return insights.overview(current_user.user_id, rank_basis, skill or None)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.put("/leaderboard-visibility")
def set_leaderboard_visibility(body: VisibilityBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Người học tự chọn có hiện tên trên bảng xếp hạng hay không; mặc định là ẩn danh."""
    return {"visible": insights.set_visible(current_user.user_id, body.visible)}


@router.get("/admin/salary-reference")
def read_salary_reference(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    return {"salary": insights.salary_reference()}


@router.put("/admin/salary-reference")
def write_salary_reference(body: SalaryBody, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    data = {"version": "SALARY-ADMIN", "career_code": "DATA_ANALYST", **body.model_dump()}
    return {"salary": insights.save_salary_reference(data)}


@router.post("/change-goal")
def change_goal(body: ResetBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Đổi JD mục tiêu mà vẫn giữ mức kỹ năng đã xác thực, bài kiểm tra và lịch sử học."""
    if not body.confirm:
        raise HTTPException(status_code=422, detail="Cần xác nhận trước khi đổi mục tiêu.")
    return {"run": career_process.public_run(career_process.change_goal(current_user.user_id)),
            "message": "Hãy chọn JD mới. Mức kỹ năng đã xác thực được giữ; lộ trình sẽ được lập lại theo JD mới."}


@router.post("/change-goal/cancel")
def cancel_goal_change(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Hủy lần đổi JD mục tiêu đang mở (chưa chọn JD mới); quy trình trở lại đúng bước trước đó."""
    return {"run": career_process.public_run(career_process.cancel_goal_change(current_user.user_id)),
            "message": "Đã hủy đổi mục tiêu. JD và lộ trình đang dùng được giữ nguyên."}


@router.get("/reset-preview")
def reset_preview(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Liệt kê chính xác dữ liệu sẽ bị reset trước khi người dùng xác nhận."""
    return career_process.reset_preview(current_user.user_id)


@router.post("/reset")
def reset(body: ResetBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    if not body.confirm:
        raise HTTPException(status_code=422, detail="Cần xác nhận trước khi reset.")
    career_process.reset_run(current_user.user_id)
    return {"message": "Đã reset. Bạn có thể bắt đầu lại Quy trình Career Adapt từ đầu."}


@router.get("/admin/ai-flags")
def ai_flags(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Bài có nhận xét AI bị loại. Điểm vẫn do máy chấm; mục này để người phụ trách xem lại."""
    rows = store.db.query("SELECT submission_id, user_id, status, payload FROM final_assessments WHERE task_id LIKE 'EXAM-%' ORDER BY created_at DESC")
    flagged = []
    for row in rows:
        flag = json.loads(row["payload"]).get("ai_flag")
        if flag:
            flagged.append({"submission_id": row["submission_id"], "user_id": row["user_id"], "code": flag["code"], "message": flag["message"]})
    return flagged

