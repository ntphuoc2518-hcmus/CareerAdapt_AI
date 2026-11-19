"""Choose what belongs on a learner's roadmap, before the scheduler places it in weeks.

Pure functions, so the same inputs always give the same plan. Rules from the V4.0 specification:
- An unmeasured skill gets an assessment first; it is never treated as a weak skill.
- A learning activity is chosen only for a measured skill with a gap, up to the target level.
- A learning activity needs an approved resource, an outcome and an estimated duration.
- Nothing disappears silently: whatever is left out is returned with a reason.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

ALGORITHM_VERSION = "ROADMAP-4.0"
ASSESSMENT_PRIORITY_BASE = 1000.0


def resources_for(activity: dict, resources_by_id: dict[str, dict]) -> list[dict]:
    return [resources_by_id[resource_id] for resource_id in activity.get("resource_ids", []) if resource_id in resources_by_id]


def _assessment_tasks_by_skill(tasks: list[dict]) -> dict[str, dict]:
    chosen: dict[str, dict] = {}
    for task in tasks:
        if task.get("status", "PUBLISHED").upper() != "PUBLISHED" or task.get("is_reassessment_variant"):
            continue
        for item in task.get("skills_evaluated", []):
            chosen.setdefault(item.get("skill_code"), task)
    return chosen


def plan_items(evaluation: dict, activities: list[dict], tasks: list[dict], usable_resources: list[dict],
               completed_ids: set[str], additional_requirements: Optional[list[str]] = None) -> dict:
    """Return {"items": activities to schedule, "excluded": items left out with reasons}."""
    skills = {item["skill_code"]: item for item in evaluation["skill_evaluations"]}
    resources_by_id = {item["resource_id"]: item for item in usable_resources}
    task_by_skill = _assessment_tasks_by_skill(tasks)
    by_id = {activity["activity_id"]: activity for activity in activities}
    items: list[dict] = []
    excluded: list[dict] = []

    # 1. Missing evidence comes first, one assessment for all the skills a task measures.
    assessments: dict[str, dict] = {}
    for code, skill in skills.items():
        if skill["status"] == "ASSESSED":
            continue
        task = task_by_skill.get(code)
        if not task:
            excluded.append({"activity_id": f"ASSESS:{code}", "title": f"Đánh giá {skill['skill_name']}", "target_skill": code, "kind": "ASSESSMENT",
                             "reason_code": "MISSING_EVIDENCE", "reason": "Chưa có bài đánh giá đã phát hành cho kỹ năng này."})
            continue
        entry = assessments.setdefault(task["task_id"], {
            "activity_id": f"ASSESS_{task['task_id']}", "kind": "ASSESSMENT", "task_id": task["task_id"], "title": f"Làm bài đánh giá {task['task_id']}",
            "target_skill": code, "skills": [], "estimated_hours": round(float(task.get("estimated_duration_minutes", 30)) / 60, 2), "prerequisites": [],
            "learning_outcome": "Có bằng chứng hợp lệ để xác định khoảng cách kỹ năng.", "splittable": False, "resources": [], "learning_objectives": [],
            "priority_score": ASSESSMENT_PRIORITY_BASE, "is_core": False, "skill_weight": 0.0,
        })
        entry["skills"].append(code)
        entry["priority_score"] += float(skill["weight"]) * 100
        entry["is_core"] = entry["is_core"] or bool(skill.get("is_core"))
        entry["skill_weight"] = max(entry["skill_weight"], float(skill["weight"]))
    items.extend(assessments.values())

    # 2. Learning activities for measured gaps.
    selected: dict[str, dict] = {}
    for code, skill in skills.items():
        if skill["status"] != "ASSESSED" or not skill["gap"]:
            continue
        candidates = [
            activity for activity in activities
            if activity.get("target_skill") == code and int(skill["current_level"] or 0) < int(activity.get("target_level", 1)) <= int(skill["target_level"])
        ]
        if not candidates:
            excluded.append({"activity_id": f"GAP:{code}", "title": f"Học phần cho {skill['skill_name']}", "target_skill": code, "kind": "LEARNING",
                             "reason_code": "NO_ACTIVITY", "reason": "Chưa có học phần đã duyệt cho mức kỹ năng này."})
        for activity in candidates:
            if activity["activity_id"] in completed_ids:
                continue
            attached = resources_for(activity, resources_by_id)
            if not attached:
                excluded.append({"activity_id": activity["activity_id"], "title": activity["title"], "target_skill": code, "kind": "LEARNING", "estimated_hours": activity.get("estimated_hours"),
                                 "reason_code": "NO_APPROVED_RESOURCE", "reason": "Chưa có học liệu đã duyệt và còn truy cập được cho học phần này."})
                continue
            if not activity.get("learning_outcome") or not activity.get("estimated_hours"):
                excluded.append({"activity_id": activity["activity_id"], "title": activity["title"], "target_skill": code, "kind": "LEARNING",
                                 "reason_code": "INCOMPLETE_ACTIVITY", "reason": "Học phần thiếu đầu ra hoặc thời lượng dự kiến."})
                continue
            selected[activity["activity_id"]] = {
                **activity, "kind": "LEARNING", "resources": attached, "priority_score": skill["priority_score"],
                "is_core": bool(skill.get("is_core")), "skill_weight": float(skill["weight"]),
            }

    # 3. Prerequisites: met by completion or by evidence; otherwise they must be on the plan too.
    pending = list(selected)
    while pending:
        activity = selected[pending.pop()]
        kept = []
        for prerequisite in activity.get("prerequisites", []):
            if prerequisite in completed_ids:
                continue
            definition = by_id.get(prerequisite)
            if definition is None:
                kept.append(prerequisite)
                continue
            owner = skills.get(definition.get("target_skill"))
            if owner and owner["status"] == "ASSESSED" and int(owner["current_level"] or 0) >= int(definition.get("target_level", 1)):
                continue  # Valid evidence already shows this level.
            # A prerequisite can belong to a skill the JD does not ask for; it still has to be learned.
            if prerequisite not in selected and (owner is None or owner["status"] == "ASSESSED"):
                attached = resources_for(definition, resources_by_id)
                if attached:
                    selected[prerequisite] = {
                        **definition, "kind": "LEARNING", "resources": attached, "priority_score": activity["priority_score"], "is_core": bool((owner or {}).get("is_core")),
                        "skill_weight": float((owner or {}).get("weight", 0)), "is_supporting_prerequisite": True,
                    }
                    pending.append(prerequisite)
            kept.append(prerequisite)
        activity["prerequisites"] = kept
    items.extend(selected.values())

    # 4. JD requirements the catalog cannot measure stay visible.
    for label in additional_requirements or []:
        excluded.append({"activity_id": f"JD:{label}", "title": label, "target_skill": None, "kind": "JD_REQUIREMENT",
                         "reason_code": "OUTSIDE_CATALOG", "reason": "Yêu cầu trong JD nhưng chưa có rubric để đo nên chưa xếp vào lộ trình."})
    return {"items": items, "excluded": excluded}


def attach_dates(schedule: dict, start_date: date, cycle_days: int) -> dict[str, dict]:
    """Add planned dates to scheduled items; returns the plan per activity for progress tracking."""
    plan: dict[str, dict] = {}
    for week in schedule.get("scheduled_weeks", []):
        week_start = start_date + timedelta(days=7 * (week["week_number"] - 1))
        week_end = week_start + timedelta(days=6)
        week["start_date"] = week_start.isoformat()
        week["end_date"] = week_end.isoformat()
        for activity in week["activities"]:
            entry = plan.setdefault(activity["activity_id"], {"planned_start": week_start.isoformat(), "planned_end": week_end.isoformat(), "kind": activity.get("kind", "LEARNING")})
            entry["planned_end"] = week_end.isoformat()
    for week in schedule.get("scheduled_weeks", []):
        for activity in week["activities"]:
            entry = plan[activity["activity_id"]]
            activity["planned_start"] = entry["planned_start"]
            activity["planned_end"] = entry["planned_end"]
            if activity.get("kind", "LEARNING") == "LEARNING":
                activity["review_due"] = (date.fromisoformat(entry["planned_end"]) + timedelta(days=cycle_days)).isoformat()
    return plan


def recovery_options(schedule: dict, total_hours_needed: float) -> list[dict]:
    """When hours run out, offer longer timelines or a smaller target rather than raising hours."""
    if not any(item.get("reason_code") in {"INSUFFICIENT_HOURS", "EXCEEDS_WEEKLY_BUDGET"} for item in schedule.get("unscheduled_activities", [])):
        return []
    weekly = float(schedule.get("weekly_hours_budget") or 0)
    options = []
    if weekly > 0:
        weeks = int(-(-total_hours_needed // weekly))
        if weeks > int(schedule.get("target_timeline_weeks") or 0):
            options.append({"kind": "EXTEND_TIMELINE", "weeks": weeks, "message": f"Kéo dài thời hạn lên khoảng {weeks} tuần với quỹ {weekly:g}h/tuần."})
    if any(item.get("reason_code") == "EXCEEDS_WEEKLY_BUDGET" for item in schedule.get("unscheduled_activities", [])):
        options.append({"kind": "INCREASE_HOURS", "message": "Một số học phần không chia nhỏ được; bạn có thể tự tăng giờ/tuần trong hồ sơ nếu thực tế cho phép."})
    options.append({"kind": "LOWER_TARGET", "message": "Hoặc chọn mục tiêu thấp hơn ở trang Mục tiêu JD."})
    return options
