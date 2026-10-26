"""F10: In-App Reminder Endpoints with Deduplication (TV3 / F10).

Principles:
- Only in-app notifications. No push/email outside app in MVP.
- Strict deduplication: prevents spamming identical reminders.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, get_current_user
from schemas.models import (
    ReminderCreateRequest, ReminderItem, ReminderListResponse
)
from services.store import store

router = APIRouter(prefix="/reminders", tags=["F10 - In-App Reminders"])


@router.post("", response_model=ReminderItem, status_code=status.HTTP_201_CREATED)
def create_in_app_reminder(
    body: ReminderCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Create an in-app reminder with deduplication guard."""
    uid = current_user.user_id
    now = datetime.now(timezone.utc)

    user_reminders = store.reminders.get(uid, [])

    # Deduplication check: Check if an unread reminder with same type and target_id exists
    for r in user_reminders:
        if not r["is_read"] and r["reminder_type"] == body.reminder_type and r.get("target_id") == body.target_id:
            # Return existing unread reminder without duplicating
            return ReminderItem(**r)

    new_id = uuid.uuid4()
    reminder_record = {
        "reminder_id": new_id,
        "user_id": uid,
        "reminder_type": body.reminder_type,
        "message": body.message,
        "target_id": body.target_id,
        "is_read": False,
        "created_at": now
    }

    if uid not in store.reminders:
        store.reminders[uid] = []
    store.reminders[uid].append(reminder_record)

    return ReminderItem(**reminder_record)


@router.get("", response_model=ReminderListResponse)
def list_in_app_reminders(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Retrieve all in-app reminders for the authenticated user."""
    uid = current_user.user_id
    user_reminders = store.reminders.get(uid, [])

    items = [
        ReminderItem(
            reminder_id=r["reminder_id"],
            reminder_type=r["reminder_type"],
            message=r["message"],
            target_id=r.get("target_id"),
            is_read=r["is_read"],
            created_at=r["created_at"]
        )
        for r in user_reminders
    ]
    # Sort latest first
    items.sort(key=lambda x: x.created_at, reverse=True)
    unread_count = sum(1 for r in items if not r.is_read)

    return ReminderListResponse(
        unread_count=unread_count,
        reminders=items
    )


@router.patch("/{reminder_id}/read", response_model=ReminderItem)
def mark_reminder_as_read(
    reminder_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Mark an in-app reminder as read."""
    uid = current_user.user_id
    user_reminders = store.reminders.get(uid, [])

    for r in user_reminders:
        if r["reminder_id"] == reminder_id:
            r["is_read"] = True
            return ReminderItem(**r)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Không tìm thấy thông báo nhắc nhở tương ứng."
    )
