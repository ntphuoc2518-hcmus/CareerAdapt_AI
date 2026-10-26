"""F04: Assessments & Evidence Verification Endpoints (TV3 / F04)."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, get_current_user, check_resource_ownership
from schemas.models import AssessmentResponse
from services.store import store

router = APIRouter(prefix="/assessments", tags=["F04 - Assessments & Evidence"])


@router.get("/by-submission/{submission_id}", response_model=AssessmentResponse)
def get_assessment_by_submission(
    submission_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Retrieve detailed assessment and verified evidence for a submission."""
    sub = store.submissions.get(submission_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bài nộp tương ứng."
        )
    check_resource_ownership(sub["user_id"], current_user.user_id)

    assessment_data = store.assessments.get(submission_id)
    if not assessment_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bài nộp đang trong quá trình chấm hoặc chưa có kết quả."
        )

    return AssessmentResponse(**assessment_data)
