"""Learning tasks of the roadmap: state, detail, the knowledge check after "completed", answer drafts,
skill mastery and AI feedback on a graded check.

The backend decides everything that counts: the state of a task, the questions, the grade and the
evidence. AI only explains a result that is already graded, and a failure of AI changes nothing.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend import config, i18n
from backend.ai_service import gateway, guardrails
from backend.ai_service.gateway import GatewayError
from backend.api.learning_cycle import _micro, _micro_view, clean_responses
from backend.api.roadmaps import ProgressUpdateRequest, _annotated, update_activity_progress
from backend.auth import AuthenticatedUser, get_current_user
from backend.catalog import get_resource, is_usable
from backend.clock import utcnow
from backend.database import dumps
from backend.lesson_checks import GRADED, check_summary, issue_lesson_check, latest_graded, learning_tasks, lesson_checks, level_confirmed, skill_mastery, task_state
from backend.store import store
from backend.targeting import evaluate_learner

router = APIRouter(tags=["Learning tasks & knowledge checks"])

FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}, "strengths": {"type": "array", "items": {"type": "string"}},
                   "to_review": {"type": "array", "items": {"type": "string"}}, "next_steps": {"type": "array", "items": {"type": "string"}}},
    "required": ["summary", "strengths", "to_review", "next_steps"], "additionalProperties": False,
}
FEEDBACK_INSTRUCTIONS = (
    "Bạn là trợ lý học tập của CareerAdapt AI. Bài kiểm tra đã được hệ thống chấm theo đáp án chuẩn; bạn chỉ giải thích kết quả trong 'facts'. "
    "Không chấm lại, không đổi điểm, không thêm con số nào ngoài facts. Điểm mạnh chỉ lấy từ strong_topics, phần cần ôn chỉ lấy từ weak_topics và câu sai. "
    "Gợi ý học liệu chỉ được nêu tên có trong review_resources. Viết ngắn gọn, tiếng Việt, xưng 'bạn'. "
    "summary tối đa 2 câu ngắn; mỗi phần tử trong các danh sách là một ý ngắn, không gộp nhiều ý vào một câu dài."
)


class KnowledgeCheckRequest(BaseModel):
    confirm: bool = False
    notes: Optional[str] = Field(default="", max_length=1000)
    actual_hours: Optional[float] = Field(default=None, ge=0, le=1000)


class DraftRequest(BaseModel):
    responses: dict[str, Any] = Field(default_factory=dict)


def _roadmap_activity(user_id: uuid.UUID, activity_id: str) -> tuple[dict, dict]:
    """A learning activity of the learner's own current roadmap, or 404."""
    roadmap = store.roadmaps.get(user_id) or {}
    planned = (roadmap.get("activity_plan") or {}).get(activity_id)
    activity = store.get_activity(activity_id)
    if not planned or planned.get("kind", "LEARNING") != "LEARNING" or not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Học phần này không có trong lộ trình hiện tại của bạn.")
    return roadmap, activity


def _resources(roadmap: dict, activity: dict) -> list[dict]:
    """The activity's resources as the roadmap shows them (with availability), else from the catalogue."""
    for week in (_annotated(roadmap).get("schedule") or {}).get("scheduled_weeks", []):
        for item in week.get("activities", []):
            if item.get("activity_id") == activity["activity_id"] and item.get("resources"):
                return item["resources"]
    found = [get_resource(store.db, resource_id) for resource_id in activity.get("resource_ids", [])]
    return [{**item, "available": is_usable(item)} for item in found if item]


@router.get("/me/learning-tasks")
def list_learning_tasks(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Trạng thái từng học phần: Chưa bắt đầu, Đang học, Chờ kiểm tra, Đã xác minh, Cần ôn tập."""
    return learning_tasks(current_user.user_id)


@router.get("/me/skill-mastery")
def get_skill_mastery(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Mức đã xác minh theo từng kỹ năng của mục tiêu, cùng lịch sử các bài kiểm tra đã chấm."""
    evaluation = evaluate_learner(current_user.user_id)
    return {"skills": skill_mastery(current_user.user_id, evaluation), "coverage": evaluation.get("coverage"), "readiness": evaluation.get("readiness"),
            "target": (evaluation.get("target") or {}).get("name")}


@router.get("/activities/{id}/detail")
def activity_detail(id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    user_id = current_user.user_id
    roadmap, activity = _roadmap_activity(user_id, id)
    progress = (roadmap.get("activity_progress") or {}).get(id)
    checks = lesson_checks(user_id, id)
    history = store.db.query(
        "SELECT from_status, to_status, progress_percent, note, created_at FROM progress_records WHERE user_id = ? AND activity_id = ? AND archived_by_run IS NULL ORDER BY created_at DESC",
        (str(user_id), id),
    )
    return {
        "activity": {key: activity.get(key) for key in ("activity_id", "title", "target_skill", "target_level", "estimated_hours", "learning_objectives", "learning_outcome", "prerequisites")},
        "plan": (roadmap.get("activity_plan") or {}).get(id), "resources": _resources(roadmap, activity),
        "progress": progress or {"status": "NOT_STARTED", "progress_percent": 0}, "state": task_state(progress, latest_graded(checks), level_confirmed(user_id, activity)),
        "progress_history": history, "checks": [check_summary(row) for row in checks if row["status"] in (*GRADED, "PENDING", "UNAVAILABLE")],
        "open_check_id": next((row["micro_id"] for row in checks if row["status"] == "PENDING"), None),
    }


@router.post("/activities/{id}/knowledge-check")
def start_knowledge_check(id: str, body: KnowledgeCheckRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Ghi nhận đã học xong rồi mở bài kiểm tra kiến thức. Đã học xong chưa phải là đã thành thạo."""
    user_id = current_user.user_id
    roadmap, activity = _roadmap_activity(user_id, id)
    if not body.confirm:
        raise HTTPException(status_code=422, detail="Hãy xác nhận để chuyển học phần sang bước kiểm tra kiến thức.")
    deciding = latest_graded(lesson_checks(user_id, id))
    if deciding and deciding["status"] == "PASSED" and level_confirmed(user_id, activity):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Học phần này đã được xác minh kiến thức.")
    if ((roadmap.get("activity_progress") or {}).get(id) or {}).get("status") != "COMPLETED":
        update_activity_progress(id, ProgressUpdateRequest(status="COMPLETED", progress_percent=100, notes=body.notes or "", actual_hours=body.actual_hours), current_user)
    from backend.learning_journey import end_open_session_for

    end_open_session_for(user_id, id, "CHECK")
    before = {row["micro_id"] for row in lesson_checks(user_id, id)}
    check = issue_lesson_check(user_id, activity, roadmap.get("roadmap_version"))
    if check["micro_id"] not in before:
        store.add_history_event(user_id, "LESSON_CHECK_ISSUED", f"Mở bài kiểm tra kiến thức: {activity['title']}", meta={"activity_id": id, "micro_id": check["micro_id"]})
    if check["status"] == "UNAVAILABLE":
        return {"state": "PENDING_ASSESSMENT", "lesson_check": _micro_view(check),
                "message": "Ngân hàng câu hỏi chưa đủ cho kỹ năng này nên chưa tạo được bài kiểm tra. Học phần giữ ở trạng thái Chờ kiểm tra."}
    return {"state": "PENDING_ASSESSMENT", "lesson_check": _micro_view(check), "message": "Học phần đã chuyển sang Chờ kiểm tra."}


@router.put("/micro-tests/{micro_id}/draft")
def save_draft(micro_id: str, body: DraftRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Lưu tạm câu trả lời để tải lại trang không mất bài. Bản nháp không bao giờ được chấm."""
    row = _micro(micro_id, current_user)
    if row["status"] != "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài kiểm tra này không còn mở.")
    draft = clean_responses(row["payload"]["items"], body.responses)
    saved_at = utcnow().isoformat()
    store.db.execute("UPDATE micro_assessments SET payload = json_set(payload, '$.draft', json(?), '$.draft_saved_at', ?) WHERE micro_id = ? AND status = 'PENDING'",
                     (dumps(draft), saved_at, micro_id))
    return {"saved_at": saved_at, "answered": len([value for value in draft.values() if value not in ("", [])])}


def _feedback_facts(payload: dict) -> dict:
    result = payload["result"]
    resources = result.get("review_resources") or []
    return {
        "activity_title": payload.get("activity_title"), "learning_objectives": payload.get("learning_objectives", []), "skill_code": result.get("skill_code"),
        "score": result.get("score"), "pass_threshold": result.get("pass_threshold"), "passed": result.get("passed"), "counts": result.get("counts"),
        "strong_topics": result.get("strong_topics", []), "weak_topics": result.get("weak_topics", []),
        "questions": [{"topic": item.get("topic"), "answered": item.get("answered"), "correct": item.get("credit", 0) >= 1} for item in result.get("item_results", [])],
        "review_resources": [item.get("title") for item in resources],
    }


@router.post("/micro-tests/{micro_id}/ai-feedback")
def ai_feedback(micro_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Nhận xét và gợi ý ôn tập bằng AI cho bài đã chấm. Không đổi điểm; lỗi AI thì báo lỗi để thử lại."""
    user_id = current_user.user_id
    row = _micro(micro_id, current_user)
    payload = row["payload"]
    if row["status"] not in GRADED or not payload.get("result"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chỉ có nhận xét cho bài đã được chấm.")
    key = "ai_feedback_en" if i18n.is_english() else "ai_feedback_vi"
    if payload.get(key):
        return payload[key]
    if not gateway.is_available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Chưa cấu hình dịch vụ AI. Kết quả chấm và gợi ý theo quy tắc vẫn đầy đủ.")
    guardrails.require_open(user_id)
    problem = guardrails.budget_problem(user_id)
    if problem:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=problem)
    facts = _feedback_facts(payload)
    instructions = f"{FEEDBACK_INSTRUCTIONS}\nWrite every field in English." if i18n.is_english() else FEEDBACK_INSTRUCTIONS
    try:
        answer = gateway.structured(instructions, {"facts": facts}, FEEDBACK_SCHEMA, task="lesson_feedback", user_id=user_id,
                                    deadline=time.monotonic() + config.AI_REQUEST_DEADLINE_SECONDS, max_output_tokens=900, temperature=0.2)
    except GatewayError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI chưa phản hồi. Hãy thử lại sau ít phút; kết quả bài làm không bị ảnh hưởng.")
    text = " ".join([answer["summary"], *answer["strengths"], *answer["to_review"], *answer["next_steps"]])
    if guardrails.leaked_prompt(text) or guardrails.unverified_numbers(text, [facts]):
        gateway.trace("lesson_feedback", "REJECTED", user_id=user_id, error="AI_UNVERIFIED")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Nhận xét AI chứa thông tin không khớp với kết quả nên đã bị loại. Hãy thử lại.")
    feedback = {**answer, "generated_at": utcnow().isoformat()}
    store.db.execute(f"UPDATE micro_assessments SET payload = json_set(payload, '$.{key}', json(?)) WHERE micro_id = ?", (dumps(feedback), micro_id))
    return feedback

