"""F07: Progress Tracking Endpoints (TV3 / F07)."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, get_current_user
from schemas.models import (
    ProgressUpdateRequest, ProgressResponse, ProgressRecordItem,
    ProgressHistoryResponse, ProgressHistoryItem
)
from services.store import store

router = APIRouter(prefix="/progress", tags=["F07 - Progress Tracking"])


def _apply_progress_update(
    body: ProgressUpdateRequest,
    current_user: AuthenticatedUser
) -> ProgressResponse:
    """Core logic to update activity progress with validation and history recording."""
    uid = current_user.user_id
    now = datetime.now(timezone.utc)

    # 1. Validate activity
    valid_act_ids = {a["activity_id"] for a in store.activities}
    if body.activity_id not in valid_act_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hoạt động '{body.activity_id}' không tồn tại trong danh mục."
        )

    # 2. Validate status
    if body.new_status not in {"NOT_STARTED", "IN_PROGRESS", "COMPLETED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trạng thái không hợp lệ. Chọn NOT_STARTED, IN_PROGRESS hoặc COMPLETED."
        )

    # 3. Validate hours
    if body.hours_spent < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Số giờ học tập đã dành (hours_spent) không được là số âm."
        )

    if uid not in store.progress:
        store.progress[uid] = {}

    existing = store.progress[uid].get(body.activity_id, {})
    prev_status = existing.get("status", "NOT_STARTED")
    completed_time = now if body.new_status == "COMPLETED" else existing.get("completed_at")
    final_hours = body.hours_spent if body.hours_spent > 0 else existing.get("hours_spent", 0.0)

    store.progress[uid][body.activity_id] = {
        "activity_id": body.activity_id,
        "status": body.new_status,
        "completed_at": completed_time,
        "hours_spent": final_hours,
        "updated_at": now
    }

    # Record history event for auditability (Task T3.6)
    if uid not in store.progress_history:
        store.progress_history[uid] = []

    store.progress_history[uid].append({
        "activity_id": body.activity_id,
        "previous_status": prev_status,
        "new_status": body.new_status,
        "hours_spent": final_hours,
        "timestamp": now
    })

    return get_user_progress(current_user)


@router.put("", response_model=ProgressResponse)
def update_activity_progress_put(
    body: ProgressUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Mark progress on a learning activity (PUT).
    
    Principle 1.1: Marking an activity COMPLETED tracks progress but does NOT
    automatically change verified competency levels.
    """
    return _apply_progress_update(body, current_user)


@router.patch("", response_model=ProgressResponse)
def update_activity_progress_patch(
    body: ProgressUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Mark progress on a learning activity (PATCH alias)."""
    return _apply_progress_update(body, current_user)


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


@router.get("/history", response_model=ProgressHistoryResponse)
def get_progress_history(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Retrieve full audit history of activity status transitions for this user."""
    uid = current_user.user_id
    events = store.progress_history.get(uid, [])
    items = [
        ProgressHistoryItem(
            activity_id=e["activity_id"],
            previous_status=e.get("previous_status"),
            new_status=e["new_status"],
            hours_spent=e.get("hours_spent", 0.0),
            timestamp=e["timestamp"]
        )
        for e in events
    ]
    items.sort(key=lambda x: x.timestamp, reverse=True)
    return ProgressHistoryResponse(
        user_id=uid,
        total_events=len(items),
        history=items
    )

