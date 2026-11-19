"""Content Admin CRUD & Version Approval Endpoints (F09).

Implements:
1. Competency Framework CRUD: Manage skills, weights (warning if sum != 1.0), target levels.
2. Task Catalog CRUD: Manage tasks, rubrics, reference values, DRAFT <-> PUBLISHED.
3. Activity Catalog & DAG Cycle Prevention: DFS Cycle Detection blocking cyclical dependencies.
4. Human-in-the-Loop Review: List and resolve submissions in NEEDS_REVIEW queue.
"""
from __future__ import annotations
import uuid
import copy
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.auth import AuthenticatedUser, require_admin_user
from backend.store import store
from backend.ai_service.llm_grader import apply_skill_update
from backend.ai_service.security import anonymize_submission
from backend.catalog import get_resource
from backend.clock import utcnow
from backend.database import dumps
from backend.engine.dag_scheduler import detect_cycle_dfs
from backend.engine.rubric_engine import get_blueprint

router = APIRouter(prefix="/admin", tags=["F09 - Content Admin CRUD"])


# ==============================================================================
# 1. Competency Framework CRUD
# ==============================================================================
class SkillCreateUpdateRequest(BaseModel):
    skill_code: str
    skill_name: str
    category: str = "Kỹ thuật dữ liệu"
    target_level: int = Field(default=2, ge=1, le=3)
    weight: float = Field(default=0.20, ge=0, le=1.0, description="0 = kỹ năng tùy chọn, chỉ đo khi JD yêu cầu")
    is_core: bool = False
    source_reference: Optional[str] = "Chuẩn năng lực đào tạo v1.0"
    description: Optional[str] = ""
    rubric_summary: Optional[dict[str, str]] = Field(default_factory=dict)


@router.get("/skills")
def list_skills(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Xem danh sách toàn bộ kỹ năng chuẩn nghề nghiệp."""
    total_weight = sum(s["weight"] for s in store.skills)
    return {
        "career_code": store.career_metadata["career_code"],
        "career_title": store.career_metadata["career_title"],
        "version_tag": store.career_metadata["version_tag"],
        "total_weight": round(total_weight, 4),
        "is_weight_valid": abs(total_weight - 1.0) < 1e-4,
        "skills": store.skills
    }


@router.post("/skills", status_code=status.HTTP_201_CREATED)
def create_skill(
    body: SkillCreateUpdateRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Thêm mới kỹ năng vào khung năng lực."""
    code = body.skill_code.upper().strip()
    if store.get_skill(code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Kỹ năng có mã '{code}' đã tồn tại trong hệ thống."
        )

    new_skill = {
        "skill_code": code,
        "skill_name": body.skill_name,
        "category": body.category,
        "target_level": body.target_level,
        "weight": body.weight,
        "is_core": body.is_core,
        "source_reference": body.source_reference or "",
        "description": body.description or "",
        "rubric_summary": body.rubric_summary or {}
    }
    store.skills.append(new_skill)
    store.persist_content("skills")

    total_weight = sum(s["weight"] for s in store.skills)
    warning = None if abs(total_weight - 1.0) < 1e-4 else f"Cảnh báo: Tổng trọng số các kỹ năng hiện là {round(total_weight, 4)} != 1.0"

    return {
        "message": f"Thêm kỹ năng '{code}' thành công.",
        "skill": new_skill,
        "total_weight": round(total_weight, 4),
        "warning": warning
    }


@router.put("/skills/{code}")
def update_skill(
    code: str,
    body: SkillCreateUpdateRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Chỉnh sửa thông tin, trọng số hoặc chuẩn đầu ra của kỹ năng."""
    skill = store.get_skill(code.upper().strip())
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy kỹ năng có mã '{code}'."
        )

    skill["skill_name"] = body.skill_name
    skill["category"] = body.category
    skill["target_level"] = body.target_level
    skill["weight"] = body.weight
    skill["is_core"] = body.is_core
    if body.source_reference:
        skill["source_reference"] = body.source_reference
    if body.description:
        skill["description"] = body.description
    if body.rubric_summary:
        skill["rubric_summary"] = body.rubric_summary
    store.persist_content("skills")

    total_weight = sum(s["weight"] for s in store.skills)
    warning = None if abs(total_weight - 1.0) < 1e-4 else f"Cảnh báo: Tổng trọng số các kỹ năng hiện là {round(total_weight, 4)} != 1.0"

    return {
        "message": f"Cập nhật kỹ năng '{code}' thành công.",
        "skill": skill,
        "total_weight": round(total_weight, 4),
        "warning": warning
    }


@router.delete("/skills/{code}")
def delete_skill(
    code: str,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Xóa một kỹ năng khỏi khung năng lực."""
    upper_code = code.upper().strip()
    skill = store.get_skill(upper_code)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy kỹ năng có mã '{code}'."
        )

    store.skills = [s for s in store.skills if s["skill_code"] != upper_code]
    store.persist_content("skills")
    total_weight = sum(s["weight"] for s in store.skills)

    return {
        "message": f"Đã xóa kỹ năng '{upper_code}'.",
        "total_weight": round(total_weight, 4),
        "warning": None if abs(total_weight - 1.0) < 1e-4 else f"Cảnh báo: Tổng trọng số các kỹ năng hiện là {round(total_weight, 4)} != 1.0"
    }


# ==============================================================================
# 2. Task Catalog CRUD
# ==============================================================================
class TaskCreateUpdateRequest(BaseModel):
    task_id: str
    title: str
    description: str
    skills_evaluated: list[dict] = Field(default_factory=list)
    estimated_duration_minutes: int = 35
    status: str = "DRAFT"  # "DRAFT" hoặc "PUBLISHED"
    dataset_preview: Optional[str] = "orders_da01a.csv"
    business_rules: Optional[dict] = Field(default_factory=dict)
    reference_values: Optional[dict] = Field(default_factory=dict)
    is_reassessment_variant: bool = False
    comparable_to: Optional[str] = None
    comparability_status: str = "NOT_APPLICABLE"


@router.get("/tasks")
def list_tasks(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Xem danh mục toàn bộ đề bài và biến thể A/B."""
    return store.tasks


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreateUpdateRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Tạo đề bài mới trong ngân hàng đề."""
    tid = body.task_id.upper().strip()
    if store.get_task(tid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Đề bài có mã '{tid}' đã tồn tại."
        )

    new_task = {
        "task_id": tid,
        "title": body.title,
        "description": body.description,
        "skills_evaluated": body.skills_evaluated,
        "estimated_duration_minutes": body.estimated_duration_minutes,
        "status": body.status.upper(),
        "dataset_preview": body.dataset_preview,
        "business_rules": body.business_rules or {},
        "reference_values": body.reference_values or {},
        "content_version": 1,
        "is_reassessment_variant": body.is_reassessment_variant,
        "comparable_to": body.comparable_to.upper().strip() if body.comparable_to else None,
        "comparability_status": body.comparability_status.upper() if body.is_reassessment_variant else "NOT_APPLICABLE"
    }
    if new_task["status"] == "PUBLISHED" and not get_blueprint(tid):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Đề chỉ được phát hành khi đã có blueprint, rubric và test case.")
    if new_task["is_reassessment_variant"] and not new_task["comparable_to"]:
        raise HTTPException(status_code=422, detail="Đề đánh giá lại cần khai báo mã đề gốc để đối chiếu.")
    if new_task["is_reassessment_variant"]:
        if new_task["comparable_to"] == tid or not store.get_task(new_task["comparable_to"]):
            raise HTTPException(status_code=422, detail="Đề gốc để đối chiếu phải là một đề khác đang tồn tại.")
        if new_task["comparability_status"] not in {"NOT_REVIEWED", "APPROVED", "REJECTED"}:
            raise HTTPException(status_code=422, detail="Trạng thái tương đương không hợp lệ.")
    store.tasks.append(new_task)
    store.task_versions[tid] = [copy.deepcopy(new_task)]
    store.persist_content("tasks", "task_versions")
    return {"message": f"Đã tạo đề bài '{tid}' thành công.", "task": new_task}


@router.put("/tasks/{id}")
def update_task(
    id: str,
    body: TaskCreateUpdateRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Cập nhật đề bài, rubric và đáp án kiểm tra xác định."""
    tid = id.upper().strip()
    task = store.get_task(tid)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đề bài '{tid}'."
        )
    if body.is_reassessment_variant and not body.comparable_to:
        raise HTTPException(status_code=422, detail="Đề đánh giá lại cần khai báo mã đề gốc để đối chiếu.")
    if body.status.upper() == "PUBLISHED" and not get_blueprint(tid):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Đề chỉ được phát hành khi đã có blueprint, rubric và test case.")
    comparable_to = body.comparable_to.upper().strip() if body.comparable_to else None
    if body.is_reassessment_variant:
        if comparable_to == tid or not store.get_task(comparable_to):
            raise HTTPException(status_code=422, detail="Đề gốc để đối chiếu phải là một đề khác đang tồn tại.")
        if body.comparability_status.upper() not in {"NOT_REVIEWED", "APPROVED", "REJECTED"}:
            raise HTTPException(status_code=422, detail="Trạng thái tương đương không hợp lệ.")

    store.archive_task_version(task)
    next_version = int(task.get("content_version", 1)) + 1
    task["title"] = body.title
    task["description"] = body.description
    task["skills_evaluated"] = body.skills_evaluated
    task["estimated_duration_minutes"] = body.estimated_duration_minutes
    task["status"] = body.status.upper()
    task["dataset_preview"] = body.dataset_preview or ""
    task["business_rules"] = body.business_rules or {}
    task["reference_values"] = body.reference_values or {}
    task["is_reassessment_variant"] = body.is_reassessment_variant
    task["comparable_to"] = comparable_to
    task["comparability_status"] = body.comparability_status.upper() if body.is_reassessment_variant else "NOT_APPLICABLE"
    task["content_version"] = next_version
    store.task_versions.setdefault(tid, []).append(copy.deepcopy(task))
    store.persist_content("tasks", "task_versions")

    return {"message": f"Cập nhật đề bài '{tid}' thành công.", "task": task}


@router.get("/tasks/{id}/versions")
def list_task_versions(
    id: str,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Xem các phiên bản nội dung đã lưu của một đề bài."""
    tid = id.upper().strip()
    if not store.get_task(tid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy đề bài '{tid}'.")
    return store.task_versions.get(tid, [])


@router.delete("/tasks/{id}")
def delete_task(
    id: str,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Xóa đề bài khỏi ngân hàng đề."""
    tid = id.upper().strip()
    task = store.get_task(tid)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đề bài '{tid}'."
        )

    store.tasks = [t for t in store.tasks if t["task_id"] != tid]
    store.persist_content("tasks")
    return {"message": f"Đã xóa đề bài '{tid}'."}


# ==============================================================================
# 3. Learning Activities CRUD & DAG Cycle Prevention
# ==============================================================================
class ActivityCreateUpdateRequest(BaseModel):
    # Bounded like the skill model: the scheduler divides by hours and compares levels on the 1-3 scale.
    activity_id: str = Field(min_length=2, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    target_skill: str = Field(min_length=1, max_length=40)
    target_level: int = Field(default=2, ge=1, le=3)
    estimated_hours: float = Field(default=3.0, gt=0, le=200)
    prerequisites: list[str] = Field(default_factory=list, max_length=30)
    learning_objectives: Optional[list[str]] = Field(default_factory=list, max_length=20)
    learning_outcome: Optional[str] = Field(default="", max_length=1000)
    resource_ids: list[str] = Field(default_factory=list, max_length=50)
    splittable: bool = True
    assessment_task_id: Optional[str] = ""


def validate_activity_course_fields(body: ActivityCreateUpdateRequest) -> None:
    if not any(skill["skill_code"] == body.target_skill for skill in store.skills):
        raise HTTPException(status_code=422, detail=f"Kỹ năng '{body.target_skill}' không có trong danh mục.")
    missing = [resource_id for resource_id in body.resource_ids if not get_resource(store.db, resource_id)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Học liệu không có trong kho: {', '.join(missing)}.")
    if body.assessment_task_id:
        task = store.get_task(body.assessment_task_id)
        if not task:
            raise HTTPException(status_code=422, detail="Mã bài test gắn với khóa học không tồn tại.")
        if not any(skill.get("skill_code") == body.target_skill for skill in task.get("skills_evaluated", [])):
            raise HTTPException(status_code=422, detail="Bài test đã chọn không đánh giá kỹ năng mục tiêu của học phần.")


@router.get("/activities")
def list_activities(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Xem danh sách các học phần trong lộ trình."""
    return store.activities


@router.post("/activities", status_code=status.HTTP_201_CREATED)
def create_activity(
    body: ActivityCreateUpdateRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Tạo học phần mới có kiểm tra chu trình DAG (DFS Cycle Detection)."""
    aid = body.activity_id.strip()
    validate_activity_course_fields(body)
    if store.get_activity(aid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Học phần có mã '{aid}' đã tồn tại."
        )

    # Candidate activity
    new_act = {
        "activity_id": aid,
        "title": body.title,
        "target_skill": body.target_skill,
        "target_level": body.target_level,
        "estimated_hours": body.estimated_hours,
        "prerequisites": body.prerequisites,
        "learning_objectives": body.learning_objectives or [],
        "learning_outcome": body.learning_outcome or "",
        "resource_ids": body.resource_ids,
        "splittable": body.splittable,
        "assessment_task_id": body.assessment_task_id or ""
    }

    # Simulate combined graph to check for DAG cycles
    candidate_graph = list(store.activities) + [new_act]
    has_cycle, cycle_path = detect_cycle_dfs(candidate_graph)
    if has_cycle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PHÁT HIỆN VÒNG LẶP CHU TRÌNH (DAG Cycle): {' -> '.join(cycle_path)}. Không thể lưu phụ thuộc tiên quyết gây tắc nghẽn lộ trình!"
        )

    store.activities.append(new_act)
    store.persist_content("activities")
    return {"message": f"Đã tạo học phần '{aid}' thành công.", "activity": new_act}


@router.put("/activities/{id}")
def update_activity(
    id: str,
    body: ActivityCreateUpdateRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Chỉnh sửa học phần và kiểm tra phát hiện chu trình DAG."""
    aid = id.strip()
    validate_activity_course_fields(body)
    activity = store.get_activity(aid)
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy học phần '{aid}'."
        )

    # Candidate graph with updated node
    updated_act = {
        "activity_id": aid,
        "title": body.title,
        "target_skill": body.target_skill,
        "target_level": body.target_level,
        "estimated_hours": body.estimated_hours,
        "prerequisites": body.prerequisites,
        "learning_objectives": body.learning_objectives or [],
        "learning_outcome": body.learning_outcome or "",
        "resource_ids": body.resource_ids,
        "splittable": body.splittable,
        "assessment_task_id": body.assessment_task_id or ""
    }

    candidate_graph = [updated_act if a["activity_id"] == aid else a for a in store.activities]
    has_cycle, cycle_path = detect_cycle_dfs(candidate_graph)
    if has_cycle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PHÁT HIỆN VÒNG LẶP CHU TRÌNH (DAG Cycle): {' -> '.join(cycle_path)}. Không thể lưu phụ thuộc tiên quyết này!"
        )

    # Apply updates
    activity.update(updated_act)
    store.persist_content("activities")
    return {"message": f"Đã cập nhật học phần '{aid}' thành công.", "activity": activity}


@router.delete("/activities/{id}")
def delete_activity(
    id: str,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Xóa học phần khỏi danh mục hoạt động."""
    aid = id.strip()
    activity = store.get_activity(aid)
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy học phần '{aid}'."
        )

    store.activities = [a for a in store.activities if a["activity_id"] != aid]
    # Remove as prerequisite from any other activity
    for a in store.activities:
        if aid in a.get("prerequisites", []):
            a["prerequisites"] = [p for p in a["prerequisites"] if p != aid]
    store.persist_content("activities")

    return {"message": f"Đã xóa học phần '{aid}'."}


# ==============================================================================
# 4. Human-in-the-Loop Review & Arbitration
# ==============================================================================
class ResolveReviewRequest(BaseModel):
    override_level: Optional[int] = Field(default=None, ge=0, le=3, description="Tương thích client cũ")
    skill_levels: Optional[dict[str, int]] = None
    reviewer_notes: str = Field(description="Nhận xét giải trình của Quản trị viên")


@router.get("/reviews")
def list_review_queue(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Xem danh sách các bài nộp cần duyệt thủ công (NEEDS_REVIEW)."""
    # Augment queue items with student details and submission text
    augmented = []
    for item in store.review_queue:
        sub_id = item["submission_id"]
        sub = store.submissions.get(sub_id, {})
        assessment = store.assessments.get(sub_id, {})
        augmented.append({
            **item,
            "answers": {row["question_id"]: row["answer_text"] for row in store.db.query("SELECT question_id, answer_text FROM submission_answers WHERE submission_id = ?", (str(sub_id),))},
            "mode": sub.get("mode", "ASSESSMENT"),
            "deterministic_result": assessment.get("deterministic_result"),
            "ai_result": assessment.get("ai_result")
        })
    return augmented


@router.post("/reviews/{submission_id}/resolve")
def resolve_review(
    submission_id: uuid.UUID,
    body: ResolveReviewRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Quản trị viên ghi đè cấp độ và phê duyệt bài nộp từ hàng đợi NEEDS_REVIEW."""
    now = utcnow()
    sub = store.submissions.get(submission_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy bài nộp có ID '{submission_id}'."
        )

    assessment = store.assessments.get(submission_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy bản ghi đánh giá cho bài nộp '{submission_id}'."
        )

    user_id = sub["user_id"]
    task_id = sub["task_id"]
    task = store.get_task(task_id) or {"skills_evaluated": [{"skill_code": "SQL"}]}
    expected_codes = {item["skill_code"] for item in task.get("skills_evaluated", [])}
    if body.skill_levels is not None:
        if set(body.skill_levels) != expected_codes or any(isinstance(value, bool) or value not in range(4) for value in body.skill_levels.values()):
            raise HTTPException(status_code=422, detail="Cần chấm riêng mọi kỹ năng của đề ở thang 0–3.")
        skill_levels = body.skill_levels
    elif body.override_level is not None:
        skill_levels = {code: body.override_level for code in expected_codes}
    else:
        raise HTTPException(status_code=422, detail="Thiếu mức đánh giá theo kỹ năng.")
    total_weight = sum(float(item.get("weight", 1) or 0) for item in task.get("skills_evaluated", [])) or len(skill_levels)
    final_level = round(sum(skill_levels[code] * float(item.get("weight", 1) or 0) for item in task.get("skills_evaluated", []) for code in [item["skill_code"]]) / total_weight)

    assessment["status"] = "REVIEWED_APPROVED"
    assessment["final_level"] = final_level
    if assessment.get("final_score") is None and assessment.get("provisional_score") is not None:
        assessment["final_score"] = assessment["provisional_score"]
    if assessment.get("scoring"):
        # The reviewer settles levels; the score stays the rule engine's.
        assessment["passed"] = assessment["scoring"]["passed"]
    assessment["per_skill_results"] = {
        code: {**assessment.get("per_skill_results", {}).get(code, {}), "skill_code": code, "level": level, "human_verified": True}
        for code, level in skill_levels.items()
    }
    assessment["human_review"] = {
        "reviewed_by": admin_user.email,
        "reviewed_at": now.isoformat(),
        "skill_levels": skill_levels,
        "notes": body.reviewer_notes
    }
    sub["status"] = "REVIEWED_APPROVED"
    sub["final_level"] = final_level
    # The reviewer changes another account: take that learner's lock and start from their latest data.
    with store.user_scope(user_id):
        profile_before = copy.deepcopy(store.get_or_create_profile(user_id))
        try:
            with store.db.transaction():
                if sub.get("mode") == "ASSESSMENT":
                    assessment["skill_changes"] = apply_skill_update(user_id, assessment, assessment["per_skill_results"], source_type="HUMAN_REVIEW")
                store.save_assessment(assessment)
                store.save_submission(sub)
                store.record_progress_assessment(user_id, assessment)
                store.persist_user_runtime(user_id)
        except Exception:
            store.profiles[user_id] = profile_before
            raise

    # Remove from review queue
    store.review_queue = [r for r in store.review_queue if r["submission_id"] != submission_id]
    store._bump("reviews")

    store.add_history_event(
        user_id,
        "ADMIN_REVIEW_RESOLVED",
        f"Quản trị viên ({admin_user.email}) đã duyệt bài {task_id} theo kỹ năng {skill_levels}: {body.reviewer_notes}"
    )

    return {
        "message": f"Đã giải quyết phê duyệt bài nộp '{submission_id}'. Cấp độ tổng hợp: {final_level}",
        "submission_id": submission_id,
        "final_level": final_level,
        "per_skill_results": assessment["per_skill_results"],
        "status": "REVIEWED_APPROVED"
    }


# ==============================================================================
# 5. Calibration samples (F22): only anonymized, reviewer-labelled, approved samples
# ==============================================================================
class CalibrationRequest(BaseModel):
    submission_id: uuid.UUID
    skill_code: str = Field(max_length=40)
    reference_level: int = Field(ge=0, le=3)
    split: Literal["CALIBRATION", "HOLDOUT"] = "CALIBRATION"
    consent_basis: str = Field(min_length=3, max_length=200, description="Cơ sở được phép dùng bài làm này")
    reviewer_scores: list[int] = Field(default_factory=list, max_length=5)
    disagreement_type: str = Field(default="", max_length=120)


@router.post("/calibration-samples", status_code=status.HTTP_201_CREATED)
def add_calibration_sample(body: CalibrationRequest, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Thêm mẫu hiệu chỉnh đã ẩn danh. Không có cơ sở sử dụng thì không được thêm."""
    assessment = store.assessments.get(body.submission_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài nộp.")
    rows = store.db.query("SELECT answer_text FROM submission_answers WHERE submission_id = ? AND answer_text IS NOT NULL", (str(body.submission_id),))
    text = anonymize_submission("\n".join(row["answer_text"] for row in rows))
    if not text.strip():
        raise HTTPException(status_code=409, detail="Bài nộp không còn nội dung để đưa vào tập hiệu chỉnh.")
    sample_id = str(uuid.uuid4())
    system_level = (assessment.get("per_skill_results", {}).get(body.skill_code) or {}).get("level")
    store.db.execute(
        """INSERT INTO calibration_samples(sample_id, task_id, anonymized_text, reference_level, system_level, reviewer_scores, disagreement_type, split, approved, consent_basis, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
        (sample_id, f"{assessment['task_id']}:{body.skill_code}", text, body.reference_level, system_level, dumps(body.reviewer_scores), body.disagreement_type,
         body.split, body.consent_basis, admin_user.email, utcnow().isoformat()),
    )
    return {"sample_id": sample_id, "system_level": system_level, "reference_level": body.reference_level, "split": body.split}


@router.get("/calibration-samples")
def calibration_report(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Sai lệch tuyệt đối trung bình; tập giữ lại được báo riêng với tập hiệu chỉnh."""
    rows = store.db.query("SELECT sample_id, task_id, reference_level, system_level, split, disagreement_type, created_at FROM calibration_samples ORDER BY created_at DESC")
    report = {}
    for split in ("CALIBRATION", "HOLDOUT"):
        pairs = [row for row in rows if row["split"] == split and row["system_level"] is not None]
        report[split] = {"count": len(pairs), "mae": round(sum(abs(row["reference_level"] - row["system_level"]) for row in pairs) / len(pairs), 3) if pairs else None}
    return {"samples": rows, "report": report, "target_mae": 0.5}
