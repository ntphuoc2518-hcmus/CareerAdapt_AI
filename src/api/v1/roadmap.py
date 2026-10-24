"""F06: DAG Roadmap Generator and Versioning Endpoints (TV3 / F06)."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, get_current_user
from schemas.models import (
    RoadmapResponse, RoadmapActivityItem, UnscheduledActivityItem,
    RoadmapGenerateRequest
)
from services.store import store
from domain.scheduler import ActivityNode, generate_roadmap

router = APIRouter(prefix="/roadmap", tags=["F06 - Roadmap DAG"])


def _enrich_roadmap_with_live_progress(roadmap_data: dict, uid: uuid.UUID) -> RoadmapResponse:
    """Enrich roadmap schedule items with current live progress status."""
    user_progress = store.progress.get(uid, {})
    enriched_schedule: list[RoadmapActivityItem] = []
    for item in roadmap_data.get("schedule", []):
        item_copy = dict(item)
        if item_copy["activity_id"] in user_progress:
            item_copy["status"] = user_progress[item_copy["activity_id"]]["status"]
        enriched_schedule.append(RoadmapActivityItem(**item_copy))

    unscheduled = [UnscheduledActivityItem(**u) for u in roadmap_data.get("unscheduled", [])]
    return RoadmapResponse(
        roadmap_version_id=roadmap_data["roadmap_version_id"],
        user_id=roadmap_data["user_id"],
        total_weeks=roadmap_data["total_weeks"],
        weekly_hours_budget=roadmap_data["weekly_hours_budget"],
        total_hours=roadmap_data["total_hours"],
        schedule=enriched_schedule,
        unscheduled=unscheduled,
        generated_at=roadmap_data["generated_at"]
    )


@router.post("/generate", response_model=RoadmapResponse, status_code=status.HTTP_201_CREATED)
def generate_user_roadmap(
    body: Optional[RoadmapGenerateRequest] = None,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Generate a personalized, topologically-sorted roadmap honoring DAG constraints and weekly hours."""
    uid = current_user.user_id
    now = datetime.now(timezone.utc)

    # 1. Fetch user profile weekly hours budget and allow optional override
    profile = store.profiles.get(uid, {})
    weekly_hours = profile.get("weekly_hours_budget", 10.0)
    max_weeks = profile.get("target_timeline_weeks", 8)

    if body:
        if body.weekly_hours_budget is not None:
            weekly_hours = body.weekly_hours_budget
            # Update profile for consistency (Task T3.6)
            if uid in store.profiles:
                store.profiles[uid]["weekly_hours_budget"] = weekly_hours
        if body.target_timeline_weeks is not None:
            max_weeks = body.target_timeline_weeks
            if uid in store.profiles:
                store.profiles[uid]["target_timeline_weeks"] = max_weeks

    # 2. Build ActivityNodes from catalog
    activity_nodes = [
        ActivityNode(
            activity_id=a["activity_id"],
            title=a["title"],
            skill_id=a["skill_id"],
            estimated_hours=a["estimated_hours"],
            priority=a["priority"],
            prerequisites=a["prerequisites"]
        )
        for a in store.activities
    ]

    # 3. Execute DAG scheduler
    schedule_result = generate_roadmap(
        activities=activity_nodes,
        hours_per_week=weekly_hours,
        max_weeks=max_weeks
    )

    if not schedule_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=schedule_result.error_message or "Không thể lập lịch với cấu hình hiện tại."
        )

    # 4. Save new immutable roadmap version (Preserves history)
    roadmap_version_id = uuid.uuid4()
    user_progress = store.progress.get(uid, {})

    scheduled_items: list[RoadmapActivityItem] = []
    for item in schedule_result.schedule:
        act_status = user_progress.get(item.activity_id, {}).get("status", "NOT_STARTED")
        scheduled_items.append(RoadmapActivityItem(
            activity_id=item.activity_id,
            title=item.title,
            skill_id=item.skill_id,
            week_number=item.week_number,
            allocated_hours=item.allocated_hours,
            prerequisites_met=item.prerequisites_met,
            status=act_status
        ))

    unscheduled_items = [
        UnscheduledActivityItem(
            activity_id=u.activity_id,
            title=u.title,
            reason=u.reason
        )
        for u in schedule_result.unscheduled
    ]

    roadmap_record = {
        "roadmap_version_id": roadmap_version_id,
        "user_id": uid,
        "total_weeks": schedule_result.total_weeks,
        "weekly_hours_budget": weekly_hours,
        "total_hours": schedule_result.total_scheduled_hours,
        "schedule": [s.model_dump() for s in scheduled_items],
        "unscheduled": [u.model_dump() for u in unscheduled_items],
        "generated_at": now
    }

    if uid not in store.roadmaps:
        store.roadmaps[uid] = []
    store.roadmaps[uid].append(roadmap_record)

    return RoadmapResponse(
        roadmap_version_id=roadmap_version_id,
        user_id=uid,
        total_weeks=schedule_result.total_weeks,
        weekly_hours_budget=weekly_hours,
        total_hours=schedule_result.total_scheduled_hours,
        schedule=scheduled_items,
        unscheduled=unscheduled_items,
        generated_at=now
    )


@router.get("/latest", response_model=RoadmapResponse)
def get_latest_roadmap(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Retrieve the latest active roadmap version for the authenticated user with live progress status."""
    uid = current_user.user_id
    versions = store.roadmaps.get(uid, [])
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chưa có lộ trình nào được khởi tạo. Hãy gọi POST /api/v1/roadmap/generate."
        )
    return _enrich_roadmap_with_live_progress(versions[-1], uid)


@router.get("/versions", response_model=list[RoadmapResponse])
def list_roadmap_versions(current_user: AuthenticatedUser = Depends(get_current_user)):
    """List all historical roadmap versions generated for this user."""
    uid = current_user.user_id
    versions = store.roadmaps.get(uid, [])
    return [_enrich_roadmap_with_live_progress(v, uid) for v in versions]


@router.get("/{roadmap_version_id}", response_model=RoadmapResponse)
def get_roadmap_by_version(
    roadmap_version_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Retrieve a specific historical roadmap version by its ID."""
    uid = current_user.user_id
    versions = store.roadmaps.get(uid, [])
    for v in versions:
        if v["roadmap_version_id"] == roadmap_version_id:
            return _enrich_roadmap_with_live_progress(v, uid)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Không tìm thấy phiên bản lộ trình '{roadmap_version_id}' cho người dùng hiện tại."
    )

