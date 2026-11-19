"""Learning Roadmap 2.0 API: overview, weeks, lessons, the study timer, practice, reviews and the final assessment.

Every route works on the signed-in learner's own records only; ids in the path are checked against them.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend import final_assessment, i18n, learning_journey, practice
from backend.auth import AuthenticatedUser, get_current_user
from backend.learning_cycle_service import create_checkin, get_preferences, local_today
from backend.store import store

router = APIRouter(tags=["Learning Roadmap 2.0"])


class StartStudy(BaseModel):
    activity_id: str = Field(min_length=1, max_length=60)
    review_cycle_days: Optional[int] = Field(default=None, ge=1, le=365)
    switch: bool = False


class StudyAction(BaseModel):
    action: Literal["pause", "resume", "end", "heartbeat"]


class CodeBody(BaseModel):
    code: str = Field(default="", max_length=20000)


class AnswerBody(BaseModel):
    answer: str = Field(default="", max_length=20000)


class FinalRun(BaseModel):
    question_id: str = Field(max_length=20)
    code: str = Field(default="", max_length=20000)


class FinalEvent(BaseModel):
    kind: Literal["focus_lost", "paste_blocked", "copy_blocked"]
    detail: str = Field(default="", max_length=200)


class TextBody(BaseModel):
    text: str = Field(default="", max_length=20000)
    base_saved_at: Optional[str] = Field(default=None, max_length=64)


@router.get("/me/journey")
def get_journey(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Tổng quan lộ trình: thời gian dự kiến, tiến độ, bài chờ kiểm tra, bài tiếp theo và các tuần."""
    return learning_journey.journey(current_user.user_id)


@router.get("/me/journey/weeks/{week_number}")
def get_week(week_number: int, current_user: AuthenticatedUser = Depends(get_current_user)):
    return learning_journey.week_detail(current_user.user_id, week_number)


# The failed checks on a lesson quote exam content: the question's topic and the check's own text. Their English
# lives in the reviewed server catalog (data/i18n/sensitive_en.json), which the browser never receives. Only those
# two fields are translated here; what the learner's answer produced ("answer_gave") stays exactly as recorded.
MISTAKE_FIELDS = ("topic", "check")


@router.get("/me/journey/lessons/{activity_id}")
def get_lesson(activity_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    detail = learning_journey.lesson_detail(current_user.user_id, activity_id)
    if i18n.is_english():
        detail["mistakes"] = [{**item, **{key: i18n.localize(item[key]) for key in MISTAKE_FIELDS if isinstance(item.get(key), str)}} for item in detail["mistakes"]]
    return detail


@router.get("/me/study/current")
def current_study(current_user: AuthenticatedUser = Depends(get_current_user)):
    return {"session": learning_journey.session_view(learning_journey.current_session(current_user.user_id))}


@router.post("/me/study/start")
def start_study(body: StartStudy, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Bắt đầu hoặc tiếp tục học một bài. Lần đầu phải chọn thời gian kiểm tra lại; sau đó không đổi được."""
    from backend.api.roadmaps import ProgressUpdateRequest, update_activity_progress

    user_id = current_user.user_id
    roadmap, activity = learning_journey.roadmap_activity(user_id, body.activity_id)
    if learning_journey.lesson_plan(user_id, body.activity_id) is None:
        learning_journey.validate_review_cycle(body.review_cycle_days)
    progress = (roadmap.get("activity_progress") or {}).get(body.activity_id) or {}
    if progress.get("status") in (None, "NOT_STARTED"):
        # Same prerequisite rule as a manual progress update: a locked lesson cannot start.
        update_activity_progress(body.activity_id, ProgressUpdateRequest(status="IN_PROGRESS", notes="Bắt đầu phiên học"), current_user)
    session = learning_journey.start_session(user_id, activity, roadmap.get("roadmap_version"), body.review_cycle_days, body.switch)
    return {"session": learning_journey.session_view(session), "review_cycle_days": learning_journey.lesson_plan(user_id, body.activity_id)["review_cycle_days"]}


@router.post("/me/study/{session_id}")
def study_action(session_id: str, body: StudyAction, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Tạm dừng, tiếp tục, kết thúc hoặc báo còn đang học. Thời gian luôn do máy chủ tính."""
    user_id = current_user.user_id
    handler = {"pause": learning_journey.pause_session, "resume": learning_journey.resume_session, "heartbeat": learning_journey.heartbeat, "end": learning_journey.end_session}[body.action]
    return {"session": learning_journey.session_view(handler(user_id, session_id))}


@router.post("/me/practice/{exercise_id}/run")
def run_practice(exercise_id: str, body: CodeBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    return practice.run(current_user.user_id, exercise_id, body.code)


@router.post("/me/practice/{exercise_id}/check")
def check_practice(exercise_id: str, body: AnswerBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Chấm bài thực hành để tự kiểm tra. Không phải bằng chứng năng lực."""
    return practice.check(current_user.user_id, exercise_id, body.answer)


@router.post("/activities/{activity_id}/review/reschedule")
def reschedule_review(activity_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Sau khi ôn tập chưa đạt và đã học lại: đặt lần ôn tập tiếp theo theo chu kỳ đã chốt."""
    user_id = current_user.user_id
    roadmap, activity = learning_journey.roadmap_activity(user_id, activity_id)
    state = learning_journey.lesson_states(user_id)[activity_id]
    if state["review_state"] != "RELEARN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chỉ đặt lại lịch ôn tập sau một lần ôn tập chưa đạt.")
    preferences = get_preferences(user_id)
    days = int(state["review_cycle_days"] or preferences["default_cycle_days"])
    checkin = create_checkin(user_id, activity, days, local_today(preferences), roadmap.get("roadmap_version"), preferences["timezone"])
    store.add_history_event(user_id, "REVIEW_SCHEDULED", f"Đặt lại lịch ôn tập {activity['title']}: sau {days} ngày", meta={"activity_id": activity_id, "checkin_id": checkin["checkin_id"]})
    return {"review_due_at": checkin["due_at"], "review_cycle_days": days}


@router.post("/me/journey/replan")
def replan_journey(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Xếp lại các bài còn lại theo mức đã xác thực hiện tại, bắt đầu từ hôm nay. Bài đã hoàn thành và lịch sử được giữ."""
    from backend.api.roadmaps import replan

    return replan(current_user.user_id, "Người học yêu cầu cập nhật lộ trình.", force=True)


@router.get("/me/final-assessment")
def final_status(current_user: AuthenticatedUser = Depends(get_current_user)):
    user_id = current_user.user_id
    attempt = final_assessment.current(user_id)
    return {**final_assessment.status_for(user_id), "attempt": final_assessment.public_state(attempt) if attempt and attempt["status"] == "IN_PROGRESS" else None}


@router.post("/me/final-assessment/start")
def final_start(current_user: AuthenticatedUser = Depends(get_current_user)):
    return final_assessment.public_state(final_assessment.start(current_user.user_id))


@router.put("/me/final-assessment/responses/{question_id}")
def final_save(question_id: str, body: TextBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    return final_assessment.save_response(current_user.user_id, question_id, body.text, body.base_saved_at)


@router.post("/me/final-assessment/run")
def final_run(body: FinalRun, current_user: AuthenticatedUser = Depends(get_current_user)):
    return final_assessment.run_code(current_user.user_id, body.question_id, body.code)


@router.post("/me/final-assessment/events")
def final_event(body: FinalEvent, current_user: AuthenticatedUser = Depends(get_current_user)):
    return final_assessment.record_event(current_user.user_id, body.kind, body.detail)


@router.post("/me/final-assessment/submit")
def final_submit(current_user: AuthenticatedUser = Depends(get_current_user)):
    return final_assessment.submit(current_user.user_id)


@router.get("/me/final-assessment/{attempt_id}/review")
def final_review(attempt_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    return final_assessment.review(current_user.user_id, attempt_id)
