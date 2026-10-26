"""F01: Profile and Career Goals Endpoints (TV3 / F01)."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, get_current_user
from schemas.models import ProfileCreateRequest, ProfileResponse
from services.store import store

router = APIRouter(prefix="/profiles", tags=["F01 - Profile & Goals"])


@router.get("/me", response_model=ProfileResponse)
def get_user_profile(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Retrieve the authenticated user's profile.
    
    If no profile exists yet, initializes with default settings.
    """
    uid = current_user.user_id
    if uid not in store.profiles:
        # Default initialization
        now = datetime.now(timezone.utc)
        store.profiles[uid] = {
            "user_id": uid,
            "email": current_user.email,
            "target_career_id": "DATA_ANALYST",
            "weekly_hours_budget": 10.0,
            "target_timeline_weeks": 8,
            "self_reported_skills": [],
            "created_at": now,
            "updated_at": now
        }
    return store.profiles[uid]


@router.put("/me", response_model=ProfileResponse)
def update_user_profile(
    body: ProfileCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Update user goals, weekly hour budget, and self-reported skills.
    
    Note: Self-reported skills are explicitly marked as self-reported and never
    treated as verified competency evidence.
    """
    uid = current_user.user_id
    now = datetime.now(timezone.utc)

    # Validate that self-reported skill codes exist in the skills framework
    for skill in body.self_reported_skills:
        if skill.skill_id not in store.skills:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mã kỹ năng '{skill.skill_id}' không tồn tại trong khung kỹ năng."
            )

    self_reported_data = [
        {
            "skill_id": s.skill_id,
            "claimed_level": s.claimed_level,
            "is_self_reported": True  # Principle 1.1: Tự khai không phải bằng chứng
        }
        for s in body.self_reported_skills
    ]

    profile_data = {
        "user_id": uid,
        "email": current_user.email,
        "target_career_id": body.target_career_id,
        "weekly_hours_budget": body.weekly_hours_budget,
        "target_timeline_weeks": body.target_timeline_weeks,
        "self_reported_skills": self_reported_data,
        "created_at": store.profiles.get(uid, {}).get("created_at", now),
        "updated_at": now
    }
    store.profiles[uid] = profile_data
    return profile_data
