"""Gap analysis, personalised roadmap and progress (F05-F07, F19).

A roadmap is built from the confirmed target, the valid evidence and the available hours. Every
plan that differs from the previous one becomes a new version; older versions and all progress
records are kept.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend import career_process
from backend.auth import AuthenticatedUser, get_current_user
from backend.catalog import get_resource, is_usable, list_resources
from backend.clock import utcnow
from backend.engine.dag_scheduler import schedule_dag_roadmap, validate_prerequisite_graph
from backend.engine.roadmap_planner import ALGORITHM_VERSION, attach_dates, plan_items, recovery_options, resources_for
from backend.learning_cycle_service import get_preferences, local_today, resolve_activity_reminders
from backend import supplementary
from backend.store import store
from backend.targeting import evaluate_learner, resolve_target, target_summary

PROGRESS_WORDS = {"NOT_STARTED": "chưa bắt đầu", "IN_PROGRESS": "đang học", "COMPLETED": "hoàn thành"}
router = APIRouter(tags=["F05/F06/F07 - Gap Analysis & DAG Roadmap"])


class ProgressUpdateRequest(BaseModel):
    # No default status: an empty or malformed body must not record a completion.
    status: Literal["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "PAUSED"]
    progress_percent: Optional[int] = Field(default=None, ge=0, le=100, description="Phần trăm hoàn thành (0 - 100); bỏ trống thì suy ra từ trạng thái")
    notes: Optional[str] = Field(default="", max_length=1000)
    actual_hours: Optional[float] = Field(default=None, ge=0, le=1000)
    evidence_note: Optional[str] = Field(default="", max_length=2000)


def normalize_progress(activity_status: str, percent: int) -> tuple[str, int]:
    """Keep status and percent consistent server-side instead of trusting the client.

    Rule: COMPLETED <=> 100%, NOT_STARTED <=> 0%, IN_PROGRESS 1-99%, PAUSED 0-99%.
    - COMPLETED is always stored as 100%.
    - NOT_STARTED with any progress (>0) becomes IN_PROGRESS.
    - IN_PROGRESS at 100% is promoted to COMPLETED (the prerequisite check that follows still
      applies, so an activity with unmet prerequisites can never become COMPLETED); at 0% it is 1%.
    - PAUSED keeps the client's percent clamped to 0-99 (a paused module is never 100%).
    """
    percent = max(0, min(100, int(percent)))
    if activity_status == "COMPLETED":
        return "COMPLETED", 100
    if activity_status == "NOT_STARTED":
        if percent == 0:
            return "NOT_STARTED", 0
        activity_status = "IN_PROGRESS"
    if activity_status == "PAUSED":
        return "PAUSED", min(99, percent)
    if activity_status == "IN_PROGRESS" and percent == 100:
        return "COMPLETED", 100
    return activity_status, max(1, min(99, percent))


def overall_progress_percent(activity_progress: dict, activity_ids: Optional[set[str]] = None) -> float:
    """Mean progress over the roadmap's activities, weighted by estimated hours (1h when unknown).

    Activities without a progress record count as 0%, so the bar reflects partial progress honestly."""
    ids = set(activity_ids) if activity_ids is not None else set(activity_progress)
    if not ids:
        return 0.0
    total_weight = weighted = 0.0
    for activity_id in ids:
        activity = store.get_activity(activity_id) or {}
        weight = float(activity.get("estimated_hours") or 0) or 1.0
        total_weight += weight
        weighted += weight * float((activity_progress.get(activity_id) or {}).get("progress_percent", 0) or 0)
    return round(weighted / total_weight, 1)


def _roadmap_activity_ids(roadmap: dict) -> set[str]:
    """Learning activities only: assessments are finished by submitting them, not by a progress update."""
    ids = set(roadmap.get("activity_progress", {}))
    for week in (roadmap.get("schedule") or {}).get("scheduled_weeks", []):
        ids.update(activity["activity_id"] for activity in week.get("activities", []) if activity.get("kind", "LEARNING") == "LEARNING")
    return ids


def _next_assessment(evaluation: dict) -> Optional[dict]:
    pending = [item for item in evaluation["skill_evaluations"] if item["status"] == "UNASSESSED"]
    pending.sort(key=lambda item: (not item["is_core"], -item["weight"], item["skill_code"]))
    for item in pending:
        for task in store.tasks:
            if task.get("status", "PUBLISHED").upper() == "PUBLISHED" and not task.get("is_reassessment_variant") and any(skill.get("skill_code") == item["skill_code"] for skill in task.get("skills_evaluated", [])):
                return {"task_id": task["task_id"], "title": task["title"], "skill_code": item["skill_code"]}
    return None


@router.get("/me/gap")
def get_gap(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Khoảng cách kỹ năng, độ phủ và mức đáp ứng theo mục tiêu đang chọn, kèm lý do và bằng chứng."""
    from backend.lesson_checks import reconfirm_levels

    reconfirm_levels(current_user.user_id)
    evaluation = evaluate_learner(current_user.user_id)
    return {**evaluation, "recommended_assessment": _next_assessment(evaluation)}


GENERIC_CHANGE = "Cập nhật danh mục học phần hoặc học liệu."


def _change_reason(previous: dict, roadmap: dict) -> str:
    if not previous.get("roadmap_version"):
        return "Lộ trình đầu tiên."
    reasons = []
    if previous.get("target", {}).get("jd_id") != roadmap["target"].get("jd_id") or previous.get("target", {}).get("target_version") != roadmap["target"].get("target_version"):
        reasons.append("đổi mục tiêu JD")
    if previous.get("weekly_hours_budget") != roadmap["weekly_hours_budget"]:
        reasons.append("đổi số giờ mỗi tuần")
    if previous.get("target_timeline_weeks") != roadmap["target_timeline_weeks"]:
        reasons.append("đổi thời hạn")
    if previous.get("assessed_levels") != roadmap["assessed_levels"]:
        reasons.append("có kết quả đánh giá mới")
    if previous.get("completed_activity_ids") != roadmap["completed_activity_ids"]:
        reasons.append("cập nhật hoạt động đã hoàn thành")
    return "Lập lại lịch vì " + ", ".join(reasons) + "." if reasons else GENERIC_CHANGE


@router.post("/roadmaps")
def generate_roadmap_endpoint(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Tạo lộ trình theo mục tiêu đã xác nhận, khoảng cách kỹ năng và quỹ giờ."""
    career_process.guard_step(current_user.user_id, "ROADMAP", "lập lại lộ trình")
    return build_roadmap(current_user.user_id)


def build_roadmap(user_id: uuid.UUID, completed_override: Optional[set[str]] = None, reason: Optional[str] = None, restart: bool = False) -> dict:
    """Plan and store a roadmap version. The process calls this from its own guarded step.

    ``completed_override`` is the re-planning mode: only lessons that passed their completion check count
    as done; they stay on the roadmap as carried-over lessons, and only what is still needed is rescheduled.
    """
    profile = store.get_or_create_profile(user_id)
    graph = validate_prerequisite_graph(store.activities)
    if graph["has_cycle"] or graph["missing_prerequisites"]:
        nodes = " -> ".join(graph["cycle_path"]) or ", ".join(f"{item['activity_id']} thiếu {item['prerequisite']}" for item in graph["missing_prerequisites"])
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Danh mục học phần có lỗi tiên quyết, chưa thể lập lịch: {nodes}.")

    target = resolve_target(profile)
    evaluation = evaluate_learner(user_id, profile, target)
    existing = store.roadmaps.get(user_id, {})
    activity_progress = existing.get("activity_progress", {})
    completed_ids = set(completed_override) if completed_override is not None else {aid for aid, item in activity_progress.items() if item.get("status") == "COMPLETED"}
    weekly_hours = float(profile.get("weekly_hours_budget", 4.0))
    timeline_weeks = int(profile.get("target_timeline_weeks", 8))
    preferences = get_preferences(user_id)
    cycle_days = int(preferences["default_cycle_days"])

    usable = list_resources(store.db, approved_only=True)
    plan = plan_items(evaluation, store.activities, store.tasks, usable, completed_ids, target.get("additional_requirements", []))
    schedule = schedule_dag_roadmap(plan["items"], weekly_hours, timeline_weeks, completed_ids)
    if schedule.get("blocked"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Đồ thị tiên quyết có chu trình: {' -> '.join(schedule['cycle_path'])}.")
    schedule["unscheduled_activities"].extend(plan["excluded"])
    schedule["meets_deadline"] = not any(item.get("kind") != "JD_REQUIREMENT" for item in schedule["unscheduled_activities"])
    today = local_today(preferences)
    activity_plan = attach_dates(schedule, today, cycle_days)
    old_plan = existing.get("activity_plan") or {}
    retired = []
    if completed_override is not None:
        # Lessons already passed stay on the roadmap (first, in their old order) so counts and history remain.
        carried = {aid: {**old_plan[aid], "kind": "LEARNING", "carried_over": True} for aid in old_plan if aid in completed_ids and old_plan[aid].get("kind", "LEARNING") == "LEARNING"}
        activity_plan = {**carried, **{aid: entry for aid, entry in activity_plan.items() if aid not in carried}}
        levels = {code: item.get("level") for code, item in profile.get("assessed_skills", {}).items()}
        for aid, entry in old_plan.items():
            if entry.get("kind", "LEARNING") != "LEARNING" or aid in activity_plan:
                continue
            activity = store.get_activity(aid) or {}
            reached = (levels.get(activity.get("target_skill")) or 0) >= int(activity.get("target_level") or 99)
            retired.append({"activity_id": aid, "title": activity.get("title", aid), "target_skill": activity.get("target_skill"),
                            "reason": "Mức đã xác thực đã đạt yêu cầu của bài này." if reached else "Bài này không còn cần cho mục tiêu hiện tại."})
    total_needed = sum(float(item.get("estimated_hours") or 0) for item in plan["items"])
    assessed_levels = {code: item["level"] for code, item in profile.get("assessed_skills", {}).items()}

    signature_inputs = {
        "assessed_levels": assessed_levels, "target": target_summary(target), "requirements": target.get("requirements_by_skill"),
        "weekly_hours_budget": weekly_hours, "target_timeline_weeks": timeline_weeks, "completed_activity_ids": sorted(completed_ids),
        "items": [{key: item.get(key) for key in ("activity_id", "estimated_hours", "prerequisites", "priority_score")} for item in plan["items"]],
        "resources": sorted(resource["resource_id"] for item in plan["items"] for resource in item.get("resources", [])),
        "algorithm": ALGORITHM_VERSION,
        # The plan's first day is part of what was planned: a restart from today is a new plan even when nothing else changed (audit B-01).
        "start_date": today.isoformat() if restart else existing.get("start_date", today.isoformat()),
    }
    planning_signature = hashlib.sha256(json.dumps(signature_inputs, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    unchanged = existing.get("planning_signature") == planning_signature
    now = utcnow().isoformat()

    next_scheduled = next((
        (week["week_number"], activity) for week in schedule["scheduled_weeks"] for activity in week["activities"]
        if activity["activity_id"] not in completed_ids
    ), None)
    next_activity = next_scheduled[1] if next_scheduled else None
    unassessed = [item for item in evaluation["skill_evaluations"] if item["status"] == "UNASSESSED"]
    reminder = (
        f"Chưa có bằng chứng cho {len(unassessed)} kỹ năng. Hãy làm bài đánh giá trước khi xem chúng như khoảng trống học tập."
        if unassessed else (f"Tuần {next_scheduled[0]}: {next_activity['title']}." if next_activity else "Không còn hoạt động nào đang được xếp lịch.")
    )
    roadmap = {
        "roadmap_id": existing.get("roadmap_id", uuid.uuid4()) if unchanged else uuid.uuid4(),
        "roadmap_version": existing.get("roadmap_version", 1) if unchanged else max(int(existing.get("roadmap_version", 0) or 0), store.latest_roadmap_version(user_id)) + 1,
        "planning_signature": planning_signature, "algorithm_version": ALGORITHM_VERSION, "user_id": user_id,
        "created_at": existing.get("created_at", now) if unchanged else now, "updated_at": now, "start_date": existing.get("start_date", today.isoformat()) if unchanged else today.isoformat(),
        "target": target_summary(target), "evaluation": evaluation, "assessed_levels": assessed_levels, "completed_activity_ids": sorted(completed_ids),
        "weekly_hours_budget": weekly_hours, "target_timeline_weeks": timeline_weeks, "cycle_days": cycle_days, "schedule": schedule,
        "activity_plan": activity_plan, "activity_progress": activity_progress, "next_activity": next_activity, "reminder": reminder,
        "assessment_prompts": unassessed, "recommended_assessment": _next_assessment(evaluation),
        "total_hours_needed": round(total_needed, 2), "recovery_options": recovery_options(schedule, total_needed),
        "retired_lessons": retired if completed_override is not None else existing.get("retired_lessons", []),
    }
    roadmap["overall_progress_percent"] = overall_progress_percent(activity_progress, _roadmap_activity_ids(roadmap))
    if not unchanged:
        automatic = _change_reason(existing, roadmap)
        # A re-plan names its own cause; the generic catalogue sentence would only mislead next to it.
        roadmap["change_reason"] = (reason if automatic == GENERIC_CHANGE else f"{reason} {automatic}") if reason else automatic
        if completed_override is not None:
            roadmap["replanned_at"] = now
    else:
        roadmap["change_reason"] = existing.get("change_reason")
    with store.db.transaction():
        store.roadmaps[user_id] = roadmap
        store.persist_user_runtime(user_id)
        if not unchanged:
            store.save_roadmap_version(user_id, roadmap, roadmap["change_reason"])
    if not unchanged:
        store.add_history_event(
            user_id, "GENERATE_ROADMAP", f"Lộ trình phiên bản {roadmap['roadmap_version']}: {schedule['total_scheduled_hours']:g} giờ trong {schedule['total_weeks_needed']} tuần. {roadmap['change_reason']}",
            version=ALGORITHM_VERSION, meta={"roadmap_version": roadmap["roadmap_version"], "jd_id": target.get("jd_id"), "jd_version": target.get("jd_version"), "mapping_version": target.get("mapping_version")},
        )
    return _annotated(roadmap)


def verified_lessons(user_id: uuid.UUID, plan: dict) -> set[str]:
    """Lessons of the plan whose deciding completion check passed and whose level the skill has reached."""
    from backend.lesson_checks import latest_graded, lesson_checks, level_confirmed

    found: dict[str, list[dict]] = {}
    for row in lesson_checks(user_id):
        found.setdefault(row["activity_id"], []).append(row)
    return {aid for aid in plan if (latest_graded(found.get(aid, [])) or {}).get("status") == "PASSED" and level_confirmed(user_id, store.get_activity(aid) or {})}


def replan(user_id: uuid.UUID, reason: str, force: bool = False) -> dict:
    """Re-plan what is still needed after a verified level changes. History is never removed.

    Without ``force`` nothing happens unless the lessons still needed differ from the lessons still
    on the roadmap, so a pass that changes nothing else does not reshuffle the weeks.
    """
    from backend.learning_journey import end_open_session_for

    roadmap = store.roadmaps.get(user_id) or {}
    plan = roadmap.get("activity_plan") or {}
    if not roadmap.get("schedule"):
        return {"changed": False, "message": "Chưa có lộ trình học tập."}
    verified = verified_lessons(user_id, plan)
    profile = store.get_or_create_profile(user_id)
    target = resolve_target(profile)
    evaluation = evaluate_learner(user_id, profile, target)
    needed_plan = plan_items(evaluation, store.activities, store.tasks, list_resources(store.db, approved_only=True), verified, target.get("additional_requirements", []))
    needed = {item["activity_id"] for item in needed_plan["items"] if item.get("kind", "LEARNING") == "LEARNING"}
    remaining = {aid for aid, entry in plan.items() if entry.get("kind", "LEARNING") == "LEARNING" and aid not in verified}
    if not force and needed == remaining:
        return {"changed": False, "added": [], "removed": [], "message": "Lộ trình hiện tại vẫn phù hợp với mức đã xác thực."}
    before = roadmap.get("roadmap_version")
    built = build_roadmap(user_id, completed_override=verified, reason=reason, restart=force)
    removed = sorted(remaining - needed)
    for activity_id in removed:
        end_open_session_for(user_id, activity_id, "REPLANNED")
    changed = built.get("roadmap_version") != before
    if changed:
        store.add_history_event(user_id, "ROADMAP_REPLANNED", f"Cập nhật lộ trình phiên bản {built['roadmap_version']}: thêm {len(needed - remaining)} bài, bỏ {len(removed)} bài.",
                                meta={"roadmap_version": built["roadmap_version"], "added": sorted(needed - remaining), "removed": removed})
    return {"changed": changed, "roadmap_version": built.get("roadmap_version"), "added": sorted(needed - remaining), "removed": removed,
            "message": "Đã cập nhật lộ trình theo mức đã xác thực mới." if changed else "Lộ trình hiện tại vẫn phù hợp với mức đã xác thực."}


def _annotated(roadmap: dict) -> dict:
    """Show each stored resource with its live status, so a dead link is flagged on an old plan."""
    view = copy.deepcopy(roadmap)
    usable = list_resources(store.db, approved_only=True)
    warnings = []
    for week in (view.get("schedule") or {}).get("scheduled_weeks", []):
        for activity in week.get("activities", []):
            for resource in activity.get("resources", []):
                current = get_resource(store.db, resource["resource_id"])
                resource["current_status"] = (current or {}).get("status", "REMOVED")
                resource["current_link_status"] = (current or {}).get("link_status", "UNKNOWN")
                resource["available"] = bool(current and is_usable(current))
                if not resource["available"]:
                    alternatives = [item for item in usable if set(item.get("skill_ids", [])) & set(resource.get("skill_ids", [])) and item["resource_id"] != resource["resource_id"]]
                    resource["alternatives"] = [{key: item.get(key) for key in ("resource_id", "title", "provider", "url")} for item in alternatives[:3]]
                    warnings.append({"activity_id": activity["activity_id"], "resource_id": resource["resource_id"], "title": resource.get("title"),
                                     "message": f"Học liệu “{resource.get('title')}” đang tạm ẩn hoặc link lỗi."})
    view["resource_warnings"] = warnings
    supplementary.attach((view.get("schedule") or {}).get("unscheduled_activities", []), usable)
    return view


@router.get("/me/roadmap")
def get_current_roadmap(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Lộ trình hiện tại; null khi chưa tạo."""
    roadmap = store.roadmaps.get(current_user.user_id)
    if not roadmap or not roadmap.get("schedule"):
        return None
    return {**_annotated(roadmap), **verified_progress(current_user.user_id)}


def verified_progress(user_id: uuid.UUID) -> dict:
    """Progress that rests on evidence: a lesson counts only once its completion check is passed.

    ``overall_progress_percent`` is what the learner marked; marking a lesson done proves nothing, so the
    dashboard, the report and the assistant show these figures instead (audit 2026-11-15)."""
    from backend.learning_journey import lesson_states

    states = lesson_states(user_id)
    done = sorted(activity_id for activity_id, item in states.items() if item["learning_state"] == "COMPLETED")
    return {"verified_activity_ids": done, "lessons_verified": len(done), "lessons_total": len(states),
            "verified_progress_percent": round(100 * len(done) / len(states)) if states else 0}


@router.get("/me/roadmaps/history")
def get_roadmap_history(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Trả về các phiên bản roadmap để xem lại thay đổi lịch."""
    return store.roadmap_history(current_user.user_id)


@router.patch("/activities/{id}/progress")
def update_activity_progress(id: str, body: ProgressUpdateRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Cập nhật tiến độ. Đánh dấu hoàn thành không làm thay đổi mức năng lực."""
    user_id = current_user.user_id
    activity = store.get_activity(id)
    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy học phần '{id}' trong hệ thống.")
    roadmap = store.roadmaps.get(user_id)
    if not roadmap or not roadmap.get("schedule"):
        build_roadmap(user_id)
        roadmap = store.roadmaps[user_id]
    roadmap.setdefault("activity_progress", {})

    completed_ids = {aid for aid, progress in roadmap["activity_progress"].items() if progress.get("status") == "COMPLETED"}
    profile = store.get_or_create_profile(user_id)
    levels = {code: item["level"] for code, item in profile.get("assessed_skills", {}).items()}
    missing_prereqs = []
    for prerequisite in activity.get("prerequisites", []):
        definition = store.get_activity(prerequisite) or {}
        met_by_evidence = levels.get(definition.get("target_skill"), -1) >= int(definition.get("target_level", 99))
        if prerequisite not in completed_ids and not met_by_evidence:
            missing_prereqs.append(prerequisite)
    percent = body.progress_percent
    if percent is None:
        # "IN_PROGRESS" alone keeps the saved percent instead of defaulting to 100 (which would mean completed).
        saved = int(roadmap["activity_progress"].get(id, {}).get("progress_percent") or 0)
        percent = {"COMPLETED": 100, "NOT_STARTED": 0}.get(body.status, min(saved, 99))
    activity_status, progress_percent = normalize_progress(body.status, percent)
    if activity_status in {"IN_PROGRESS", "COMPLETED"} and missing_prereqs:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Chưa thể cập nhật học phần này. Cần hoàn thành tiên quyết: {', '.join(missing_prereqs)}.")

    previous = roadmap["activity_progress"].get(id, {})
    # Sending the same state again changes nothing, so it adds no line to the activity log.
    unchanged = previous.get("status") == activity_status and previous.get("progress_percent") == progress_percent
    now = utcnow().isoformat()
    record = {
        **previous, "status": activity_status, "progress_percent": progress_percent, "notes": body.notes,
        "actual_hours": body.actual_hours if body.actual_hours is not None else previous.get("actual_hours"),
        "evidence_note": body.evidence_note or "", "started_at": previous.get("started_at") or (now if activity_status in {"IN_PROGRESS", "COMPLETED"} else None),
        "completed_at": now if activity_status == "COMPLETED" else None, "updated_at": now,
    }
    roadmap["activity_progress"][id] = record
    roadmap["overall_progress_percent"] = overall_progress_percent(roadmap["activity_progress"], _roadmap_activity_ids(roadmap))
    roadmap["updated_at"] = now
    with store.db.transaction():
        store.db.execute(
            "INSERT INTO progress_records(record_id, user_id, activity_id, roadmap_version, from_status, to_status, progress_percent, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), str(user_id), id, roadmap.get("roadmap_version"), previous.get("status"), activity_status, progress_percent, body.notes or "", now),
        )
        store.persist_user_runtime(user_id)
    if not unchanged:
        store.add_history_event(user_id, "UPDATE_PROGRESS", f"Cập nhật học phần {(store.get_activity(id) or {}).get('title') or id}: {PROGRESS_WORDS.get(activity_status, activity_status)} ({progress_percent}%)", meta={"activity_id": id, "roadmap_version": roadmap.get("roadmap_version")})
    checkin = None
    if activity_status == "COMPLETED":
        # The review clock starts only when the lesson completion check is passed (Learning Roadmap 2.0).
        resolve_activity_reminders(user_id, id)
    return {
        "activity_id": id, "status": activity_status, "progress_percent": progress_percent, "overall_progress_percent": roadmap["overall_progress_percent"],
        "actual_hours": record["actual_hours"], "evidence_note": record["evidence_note"], "updated_at": roadmap["updated_at"], "checkin": checkin,
        "message": "Đã ghi nhận tiến độ. Hoàn thành học phần không tự tăng mức năng lực; kết quả bài kiểm tra hợp lệ mới là bằng chứng. Lịch ôn tập bắt đầu khi bạn đạt bài kiểm tra hoàn thành.",
    }


@router.get("/me/progress-history")
def progress_history(current_user: AuthenticatedUser = Depends(get_current_user)):
    return store.db.query("SELECT activity_id, roadmap_version, from_status, to_status, progress_percent, note, created_at FROM progress_records WHERE user_id = ? AND archived_by_run IS NULL ORDER BY created_at DESC", (str(current_user.user_id),))


__all__ = ["router", "ProgressUpdateRequest", "generate_roadmap_endpoint", "update_activity_progress", "get_roadmap_history", "resources_for", "replan", "verified_lessons"]
