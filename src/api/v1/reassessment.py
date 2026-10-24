"""F08: Reassessment and Progress Comparison Endpoints (TV3 / F08)."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, get_current_user, check_resource_ownership
from schemas.models import ReassessmentCompareResponse, AssessmentComparisonItem
from services.store import store

router = APIRouter(prefix="/reassessment", tags=["F08 - Reassessment & Comparison"])


@router.get("/compare", response_model=ReassessmentCompareResponse)
def compare_assessments(
    previous_submission_id: uuid.UUID,
    current_submission_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Compare two assessments to evaluate skill progression.
    
    Principle 1.1: Only compare assessments that share compatible scope, task,
    or rubric versions. Old assessment records are never overwritten.
    """
    sub_prev = store.submissions.get(previous_submission_id)
    sub_curr = store.submissions.get(current_submission_id)

    if not sub_prev or not sub_curr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Một trong hai bài nộp không tồn tại."
        )

    check_resource_ownership(sub_prev["user_id"], current_user.user_id)
    check_resource_ownership(sub_curr["user_id"], current_user.user_id)

    # Check compatibility
    if sub_prev["task_version_id"] != sub_curr["task_version_id"]:
        return ReassessmentCompareResponse(
            task_id=sub_curr["task_version_id"],
            is_comparable=False,
            reason=f"Hai bài nộp thuộc hai nhiệm vụ khác nhau ({sub_prev['task_version_id']} vs {sub_curr['task_version_id']}), không thể so sánh tiến bộ trực tiếp.",
            previous_assessment_id=uuid.uuid4(),
            current_assessment_id=uuid.uuid4(),
            comparison=[]
        )

    ass_prev = store.assessments.get(previous_submission_id)
    ass_curr = store.assessments.get(current_submission_id)

    if not ass_prev or not ass_curr:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Một trong hai bài nộp chưa có kết quả đánh giá hoàn tất."
        )

    prev_scores = {s["criterion_id"]: s for s in ass_prev.get("scores", [])}
    curr_scores = {s["criterion_id"]: s for s in ass_curr.get("scores", [])}

    comparison_items: list[AssessmentComparisonItem] = []
    for crit_id, curr_s in curr_scores.items():
        prev_s = prev_scores.get(crit_id)
        prev_lvl = prev_s["level"] if prev_s else 0
        curr_lvl = curr_s["level"]
        delta = curr_lvl - prev_lvl

        comparison_items.append(AssessmentComparisonItem(
            criterion_id=crit_id,
            criterion_name=curr_s["criterion_name"],
            previous_level=prev_lvl,
            current_level=curr_lvl,
            delta=delta
        ))

    return ReassessmentCompareResponse(
        task_id=sub_curr["task_version_id"],
        is_comparable=True,
        reason="So sánh hợp lệ trên cùng tiêu chí và khung đánh giá tương thích.",
        previous_assessment_id=ass_prev["assessment_id"],
        current_assessment_id=ass_curr["assessment_id"],
        comparison=comparison_items
    )
