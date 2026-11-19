"""Career Context Service: read-only views of one account's data for the assistant.

``user_id`` comes from the authenticated session through ``ToolContext``. It is never a tool
argument, so a model has no way to name another account. Every number here is the value the
existing engines computed; nothing is recalculated, and answer keys stay out of these views.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException

from backend import career_process, exam_service
from backend.ai_service.knowledge import terms_of
from backend.catalog import list_resources
from backend.store import store
from backend.targeting import evaluate_learner, resolve_target


@dataclass(frozen=True)
class ToolContext:
    user_id: uuid.UUID


def _card(title: str, rows: list[tuple]) -> dict:
    """A small table of system figures shown beside an answer. A row may carry the raw numbers the value text
    came from (level, target, scale, percent) so the page can draw a bar; the text itself never changes."""
    out = []
    for label, value, *extra in rows:
        row = {"label": label, "value": str(value)}
        if extra and extra[0]:
            row.update({key: number for key, number in extra[0].items() if number is not None})
        out.append(row)
    return {"title": title, "rows": out}


LEVEL_SCALE = 3


def _skill_name(code: str) -> str:
    return (store.get_skill(code) or {}).get("skill_name") or code


def _not_available(reason: str) -> dict:
    return {"data": {"status": "NOT_AVAILABLE", "reason": reason}}


def _level(value: Optional[int]) -> str:
    return "Chưa đánh giá" if value is None else f"Mức {value}"


def get_my_profile(context: ToolContext) -> dict:
    profile = store.get_or_create_profile(context.user_id)
    run = career_process.active_run(context.user_id)
    data = {
        "major": profile.get("major"), "weekly_hours_budget": profile.get("weekly_hours_budget"), "target_timeline_weeks": profile.get("target_timeline_weeks"),
        "target_career": profile.get("target_career_id"), "process_step": run["step"] if run else None, "process_status": run["status"] if run else None,
        "self_reported_skills_not_evidence": [{"skill_code": item.get("skill_code"), "level": item.get("level")} for item in profile.get("self_reported_skills", []) if isinstance(item, dict)],
    }
    return {"data": data}


def get_my_current_jd(context: ToolContext) -> dict:
    profile = store.get_or_create_profile(context.user_id)
    target = resolve_target(profile)
    run = career_process.active_run(context.user_id)
    jd = (run["payload"].get("jd") if run else None) or {}
    requirements = [{"skill_code": code, "target_level": item.get("target_level"), "weight": item.get("weight"), "requirement_type": item.get("requirement_type"), "is_core": item.get("is_core")}
                    for code, item in target.get("requirements_by_skill", {}).items() if float(item.get("weight", 0)) > 0]
    data = {"name": target.get("name"), "employer": target.get("employer"), "source_type": target.get("source_type"), "is_confirmed": target.get("is_confirmed"), "summary": jd.get("summary"),
            "summary_source": jd.get("summary_source"), "requirements": requirements, "unmeasured_requirements": target.get("additional_requirements", [])}
    return {"data": data, "card": _card("JD đang dùng", [("Tên", target.get("name")), ("Đã xác nhận", "Có" if target.get("is_confirmed") else "Chưa"), ("Kỹ năng yêu cầu", len(requirements))])}


def get_my_assessment_summary(context: ToolContext) -> dict:
    try:
        review = exam_service.review(context.user_id)
    except HTTPException:
        return _not_available("Chưa có bài kiểm tra đã chấm trong quy trình hiện tại.")
    conclusion = review["conclusion"]
    questions = [{"label": item["label"], "topic": item["topic"], "skill_code": item["skill_code"], "difficulty": item["tier_label"], "points_awarded": item["points_awarded"], "max_points": item["max_points"], "blank": item["blank"],
                  "passed_checks": [case["description"] for case in item["cases"] if case["passed"]], "failed_checks": [case["description"] for case in item["cases"] if not case["passed"]], "critical_errors": item["critical"]} for item in review["questions"]]
    data = {"status": "GRADED", "score": review["score"], "max_score": review["max_score"], "pass_threshold": review["pass_threshold"], "passed": review["passed"], "overall_level": conclusion["overall_level"], "overall_label": conclusion["overall_label"],
            "summary": conclusion["summary"], "skills": conclusion["skills"], "questions": questions, "submitted_at": review["submitted_at"]}
    return {"data": data, "card": _card("Kết quả bài kiểm tra", [("Điểm", f"{review['score']}/{review['max_score']}"), ("Kết quả", "Đạt" if review["passed"] else "Chưa đạt"), ("Trình độ xác thực", f"{conclusion['overall_label']} (mức {conclusion['overall_level']}/3)")])}


def get_my_verified_skills(context: ToolContext) -> dict:
    assessed = store.get_or_create_profile(context.user_id).get("assessed_skills", {})
    skills = [{"skill_code": code, "level": item.get("level"), "source_type": item.get("source_type"), "assessed_at": item.get("assessed_at")} for code, item in assessed.items()]
    if not skills:
        return _not_available("Chưa có kỹ năng nào được xác thực bằng bài đánh giá.")
    return {"data": {"status": "VERIFIED", "skills": skills}, "card": _card("Kỹ năng đã xác thực", [(_skill_name(item["skill_code"]), f"Mức {item['level']}", {"level": item["level"], "scale": LEVEL_SCALE}) for item in skills])}


def get_my_skill_gap(context: ToolContext) -> dict:
    evaluation = evaluate_learner(context.user_id)
    skills = [{key: item.get(key) for key in ("skill_code", "skill_name", "is_core", "weight", "target_level", "current_level", "status", "gap", "next_action", "explanation")} for item in evaluation["skill_evaluations"]]
    coverage = round(evaluation["coverage"] * 100, 1)
    readiness = evaluation["readiness"]
    data = {"coverage_percent": coverage, "readiness_percent": readiness, "is_readiness_locked": evaluation["is_readiness_locked"], "lock_reasons": evaluation["lock_reasons"], "core_skills_met": evaluation["core_skills_met"],
            "skills_measured": evaluation["skills_measured"], "skills_total": evaluation["skills_total"], "skills": skills, "scope_notice": evaluation["scope_notice"]}
    rows = [("Coverage", f"{coverage:g}%", {"percent": coverage}), ("Readiness", "Đang khóa" if readiness is None else f"{readiness:g}%", {"percent": readiness})]
    rows += [(item["skill_name"], f"{_level(item['current_level'])} / mục tiêu {item['target_level']}",
              {"level": item["current_level"], "target": item["target_level"], "scale": LEVEL_SCALE}) for item in skills]
    return {"data": data, "card": _card("Skill Gap theo hệ thống", rows)}


def _plan(user_id: uuid.UUID) -> Optional[dict]:
    roadmap = store.roadmaps.get(user_id)
    return roadmap if roadmap and roadmap.get("schedule") else None


def get_my_roadmap(context: ToolContext) -> dict:
    roadmap = _plan(context.user_id)
    if roadmap is None:
        return _not_available("Chưa có lộ trình.")
    schedule = roadmap["schedule"]
    progress = roadmap.get("activity_progress", {})
    weeks = [{"week": week["week_number"], "activities": [{"activity_id": item["activity_id"], "title": item.get("title"), "kind": item.get("kind", "LEARNING"), "skill_code": item.get("target_skill"), "hours": item.get("estimated_hours"),
                                                           "status": (progress.get(item["activity_id"]) or {}).get("status", "NOT_STARTED")} for item in week.get("activities", [])]} for week in schedule.get("scheduled_weeks", [])]
    next_activity = roadmap.get("next_activity") or {}
    data = {"roadmap_version": roadmap.get("roadmap_version"), "weekly_hours_budget": roadmap.get("weekly_hours_budget"), "target_timeline_weeks": roadmap.get("target_timeline_weeks"), "total_weeks_needed": schedule.get("total_weeks_needed"),
            "total_scheduled_hours": schedule.get("total_scheduled_hours"), "meets_deadline": schedule.get("meets_deadline"), "next_activity": next_activity.get("title"), "weeks": weeks,
            "unscheduled": [item.get("title") or item.get("activity_id") for item in schedule.get("unscheduled_activities", [])]}
    return {"data": data, "card": _card("Lộ trình hiện tại", [("Phiên bản", roadmap.get("roadmap_version")), ("Tổng giờ", schedule.get("total_scheduled_hours")), ("Số tuần", schedule.get("total_weeks_needed")), ("Việc tiếp theo", next_activity.get("title") or "Không có")])}


def get_my_learning_progress(context: ToolContext) -> dict:
    from backend.api.roadmaps import _roadmap_activity_ids, overall_progress_percent, verified_progress

    roadmap = _plan(context.user_id)
    if roadmap is None:
        return _not_available("Chưa có lộ trình nên chưa có tiến độ.")
    activity_progress = roadmap.get("activity_progress", {})
    ids = _roadmap_activity_ids(roadmap)
    percent = overall_progress_percent(activity_progress, ids)
    counts: dict[str, int] = {}
    for activity_id in ids:
        status = (activity_progress.get(activity_id) or {}).get("status", "NOT_STARTED")
        counts[status] = counts.get(status, 0) + 1
    key = str(context.user_id)
    checkins = store.db.query("SELECT skill_code, due_at, status FROM learning_checkins WHERE user_id = ? AND status IN ('SCHEDULED', 'DUE', 'SNOOZED') ORDER BY due_at LIMIT 5", (key,))
    tests = store.db.query("SELECT status, COUNT(*) AS n FROM micro_assessments WHERE user_id = ? AND status != 'ARCHIVED' GROUP BY status", (key,))
    verified = verified_progress(context.user_id)
    data = {"overall_progress_percent": percent, "self_marked_note": "overall_progress_percent and activities_by_status are what the learner marked, not evidence.",
            "verified_progress_percent": verified["verified_progress_percent"], "lessons_verified": verified["lessons_verified"], "lessons_total": verified["lessons_total"], "activities_by_status": counts, "upcoming_checkins": checkins, "mini_tests_by_status": {row["status"]: row["n"] for row in tests}}
    return {"data": data, "card": _card("Tiến độ học tập", [("Bài học đã xác minh", f"{verified['lessons_verified']}/{verified['lessons_total']}", {"percent": verified["verified_progress_percent"]}),
                                                           ("Tự đánh dấu hoàn thành", counts.get("COMPLETED", 0)), ("Lịch ôn sắp tới", len(checkins))])}


def search_approved_learning_resources(context: ToolContext, query: str = "", skill_code: str = "") -> dict:
    wanted = set(terms_of(query))
    found = []
    for resource in list_resources(store.db, approved_only=True):
        if skill_code and skill_code not in resource.get("skill_ids", []):
            continue
        score = len(wanted & set(terms_of(f"{resource.get('title')} {resource.get('learning_outcome', '')} {' '.join(resource.get('skill_ids', []))}")))
        if score or not wanted:
            found.append((score, resource))
    found.sort(key=lambda item: (-item[0], item[1]["resource_id"]))
    return {"data": {"resources": [{key: resource.get(key) for key in ("resource_id", "title", "provider", "url", "resource_type", "language", "level", "skill_ids", "estimated_minutes", "learning_outcome")} for _, resource in found[:5]]}}


def get_my_career_journey_summary(context: ToolContext) -> dict:
    run = career_process.active_run(context.user_id)
    gap = get_my_skill_gap(context)["data"]
    assessment = get_my_assessment_summary(context)["data"]
    roadmap = get_my_roadmap(context)["data"]
    progress = get_my_learning_progress(context)["data"]
    data = {
        "career": run["career_code"] if run else None, "process_step": run["step"] if run else None, "process_status": run["status"] if run else "NOT_STARTED", "jd": get_my_current_jd(context)["data"]["name"],
        "score": assessment.get("score"), "overall_level": assessment.get("overall_label"), "coverage_percent": gap["coverage_percent"], "readiness_percent": gap["readiness_percent"], "is_readiness_locked": gap["is_readiness_locked"],
        "skills_with_gap": [item["skill_name"] for item in gap["skills"] if item["gap"]], "next_activity": roadmap.get("next_activity"), "overall_progress_percent": progress.get("overall_progress_percent"),
        "verified_progress_percent": progress.get("verified_progress_percent"),
    }
    rows = [("Bước hiện tại", career_process.STEP_LABELS.get(data["process_step"], "Chưa bắt đầu")), ("Coverage", f"{gap['coverage_percent']:g}%"), ("Readiness", "Đang khóa" if gap["readiness_percent"] is None else f"{gap['readiness_percent']:g}%")]
    if data["verified_progress_percent"] is not None:
        rows.append(("Tiến độ đã xác minh", f"{data['verified_progress_percent']:g}%", {"percent": data["verified_progress_percent"]}))
    return {"data": data, "card": _card("Hành trình Career Adapt", rows)}
