"""F07: Progress Tracking Endpoints (TV3 / F07)."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, get_current_user
from schemas.models import ProgressUpdateRequest, ProgressResponse, ProgressRecordItem
from services.store import store

router = APIRouter(prefix="/progress", tags=["F07 - Progress Tracking"])


@router.put("", response_model=ProgressResponse)
def update_activity_progress(
    body: ProgressUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Mark progress on a learning activity.
    
    Principle 1.1: Marking an activity COMPLETED tracks progress but does NOT
    automatically change verified competency levels.
    """
    uid = current_user.user_id
    now = datetime.now(timezone.utc)

    # Validate activity
    valid_act_ids = {a["activity_id"] for a in store.activities}
    if body.activity_id not in valid_act_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hoạt động '{body.activity_id}' không tồn tại trong danh mục."
        )

    if body.new_status not in {"NOT_STARTED", "IN_PROGRESS", "COMPLETED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trạng thái không hợp lệ. Chọn NOT_STARTED, IN_PROGRESS hoặc COMPLETED."
        )

    if uid not in store.progress:
        store.progress[uid] = {}

    existing = store.progress[uid].get(body.activity_id, {})
    completed_time = now if body.new_status == "COMPLETED" else existing.get("completed_at")

    store.progress[uid][body.activity_id] = {
        "activity_id": body.activity_id,
        "status": body.new_status,
        "completed_at": completed_time,
        "hours_spent": body.hours_spent or existing.get("hours_spent", 0.0),
        "updated_at": now
    }

    return get_user_progress(current_user)


@router.get("", response_model=ProgressResponse)
def get_user_progress(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Retrieve full progress summary and completion percentage."""
    uid = current_user.user_id
    user_prog = store.progress.get(uid, {})

    records = [
        ProgressRecordItem(
            activity_id=aid,
            status=p["status"],
            completed_at=p.get("completed_at"),
            hours_spent=p.get("hours_spent", 0.0)
        )
        for aid, p in user_prog.items()
    ]

    completed_count = sum(1 for r in records if r.status == "COMPLETED")
    total_count = len(store.activities)
    percentage = round((completed_count / total_count) * 100.0, 1) if total_count > 0 else 0.0

    return ProgressResponse(
        user_id=uid,
        completed_count=completed_count,
        total_count=total_count,
        percentage=percentage,
        records=records
    )
