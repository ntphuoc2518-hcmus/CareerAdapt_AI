"""Knowledge checks for roadmap learning activities.

Marking an activity as studied is learning progress only. The learner then takes a lesson check: a
mini-test row (payload kind ``LESSON_CHECK``) drawn from the reviewed question bank for the activity's
skill and level, ranked by how closely each question matches the activity's objectives. It is graded
and recorded by the same code as every mini-test, so a blank answer scores zero, a resubmission is
idempotent and only a passed check adds skill evidence.

The learning task state shown to the learner is derived, never stored:
NOT_STARTED / IN_PROGRESS from the progress record, then PENDING_ASSESSMENT, VERIFIED or NEEDS_REVIEW
from the latest lesson check of a completed activity.
"""
from __future__ import annotations

import json
import random
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException, status

from backend import assessment_policy as policy
from backend.clock import utcnow
from backend.database import dumps
from backend.store import store

LESSON_CHECK_KIND = "LESSON_CHECK"
LESSON_CHECK_MAX_ITEMS = 8
LESSON_CHECK_MIN_ITEMS = 3
LESSON_PASS_THRESHOLD = policy.LESSON_CHECK_PASS_SCORE
# Closed questions (choice, number, order) can confirm a skill up to this level. Level 3 needs practical
# evidence: the entry exam or the final assessment, where code runs and answers are written (audit A-03).
QUIZ_LEVEL_CEILING = policy.LESSON_QUIZ_LEVEL_CEILING
# After a failed completion check the learner studies again before a new form is issued, so a check
# cannot be retaken over and over until the answers are remembered (audit A-03).
RETRY_WAIT_HOURS = policy.LESSON_RETRY_WAIT_HOURS
TASK_STATES = ("NOT_STARTED", "IN_PROGRESS", "PENDING_ASSESSMENT", "VERIFIED", "NEEDS_REVIEW")
GRADED = ("PASSED", "FAILED")


def _words(text: str) -> set[str]:
    """Accent-folded words of three letters or more, for a rough topic match."""
    folded = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D").casefold())
    plain = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return {word for word in re.findall(r"[a-z0-9_]+", plain) if len(word) >= 3}


def select_lesson_items(activity: dict, excluded: set[str], seed: Optional[int] = None) -> list[dict]:
    """Up to eight active questions for the activity's skill up to its target level.

    Every level up to the target is represented, because the level estimate climbs from level 1 and
    stops at the first level not tested. Within that, questions closest to the objectives and not
    seen in recent checks come first. Fewer than three usable questions means no check at all.
    """
    rng = random.Random(seed)
    skill = activity.get("target_skill")
    top = max(int(activity.get("target_level") or 1), 1)
    pool = [item for item in store.question_items if item["skill_code"] == skill and item.get("status", "ACTIVE") == "ACTIVE" and int(item["level"]) <= top]
    if len(pool) < LESSON_CHECK_MIN_ITEMS:
        return []
    goal = _words(" ".join([activity.get("title", ""), activity.get("learning_outcome", ""), *activity.get("learning_objectives", [])]))
    rng.shuffle(pool)
    pool.sort(key=lambda item: (item["item_id"] in excluded, -len(goal & _words(f"{item.get('topic', '')} {item.get('stem', '')}"))))
    chosen: list[dict] = []
    for level in sorted({int(item["level"]) for item in pool}):
        chosen.append(next(item for item in pool if int(item["level"]) == level))
    chosen += [item for item in pool if item not in chosen][: LESSON_CHECK_MAX_ITEMS - len(chosen)]
    chosen.sort(key=lambda item: int(item["level"]))
    return chosen


def lesson_checks(user_id: uuid.UUID, activity_id: Optional[str] = None) -> list[dict]:
    """The learner's lesson checks, newest first, with parsed payloads."""
    sql = "SELECT * FROM micro_assessments WHERE user_id = ? AND status != 'ARCHIVED' AND json_extract(payload, '$.kind') = ?"
    parameters: list[Any] = [str(user_id), LESSON_CHECK_KIND]
    if activity_id:
        sql += " AND activity_id = ?"
        parameters.append(activity_id)
    rows = store.db.query(sql + " ORDER BY created_at DESC, rowid DESC", parameters)
    return [{**row, "payload": json.loads(row["payload"])} for row in rows]


def _local_time(moment: datetime) -> str:
    """Vietnam time (UTC+7), the learners' time zone, for messages."""
    return (moment + timedelta(hours=7)).strftime("%H:%M %d/%m/%Y")


def _recent_items(user_id: uuid.UUID, activity_id: str) -> set[str]:
    return {item["item_id"] for row in lesson_checks(user_id, activity_id)[:2] for item in row["payload"].get("items", [])}


def issue_lesson_check(user_id: uuid.UUID, activity: dict, roadmap_version: Optional[int]) -> dict:
    """The open check of this activity, or a new one. Never two open checks for one activity."""
    with store.db.transaction():
        open_check = next((row for row in lesson_checks(user_id, activity["activity_id"]) if row["status"] == "PENDING"), None)
        if open_check:
            return open_check
        ready = retry_available_at(user_id, activity["activity_id"])
        if ready:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"Bạn vừa chưa đạt bài kiểm tra này. Hãy ôn lại các ý sai; bài mới mở sau {RETRY_WAIT_HOURS} giờ, lúc {_local_time(ready)}.")
        items = select_lesson_items(activity, _recent_items(user_id, activity["activity_id"]))
        orders = {}
        for item in items:
            order = [option["id"] for option in item.get("options", [])]
            random.shuffle(order)
            orders[item["item_id"]] = order
        micro_id = str(uuid.uuid4())
        now = utcnow().isoformat()
        attempt_no = len([row for row in lesson_checks(user_id, activity["activity_id"]) if row["status"] in GRADED]) + 1
        payload = {
            "kind": LESSON_CHECK_KIND, "items": items, "option_orders": orders, "time_limit_minutes": None,
            "pass_threshold": float(activity.get("pass_threshold") or LESSON_PASS_THRESHOLD), "attempt_no": attempt_no,
            "activity_title": activity.get("title"), "learning_objectives": activity.get("learning_objectives", []),
            "learning_outcome": activity.get("learning_outcome"), "target_level": activity.get("target_level"),
            "resource_ids": activity.get("resource_ids", []), "roadmap_version": roadmap_version,
        }
        store.db.execute(
            """INSERT INTO micro_assessments(micro_id, user_id, checkin_id, due_at, skill_code, activity_id, status, bank_version, payload, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (micro_id, str(user_id), f"LESSON:{micro_id}", now, activity.get("target_skill"), activity["activity_id"],
             "PENDING" if items else "UNAVAILABLE", store.question_bank_version, dumps(payload), now),
        )
    return lesson_checks(user_id, activity["activity_id"])[0]


def confirmable_level(activity: dict) -> int:
    """The highest level a lesson's completion check can confirm: its own level, at most the quiz ceiling."""
    return min(int(activity.get("target_level") or 1), QUIZ_LEVEL_CEILING)


def level_confirmed(user_id: uuid.UUID, activity: dict) -> bool:
    """Whether the learner's verified level has reached what this lesson's check can confirm."""
    level = ((store.get_or_create_profile(user_id).get("assessed_skills") or {}).get(activity.get("target_skill")) or {}).get("level")
    return level is not None and int(level) >= confirmable_level(activity)


def retry_available_at(user_id: uuid.UUID, activity_id: str) -> Optional[datetime]:
    """When a new completion check may open after a failed one; None when it may open now."""
    latest = next((row for row in lesson_checks(user_id, activity_id) if row["status"] in GRADED), None)
    if not latest or latest["status"] != "FAILED" or not latest.get("submitted_at"):
        return None
    ready = datetime.fromisoformat(latest["submitted_at"]) + timedelta(hours=RETRY_WAIT_HOURS)
    return ready if utcnow() < ready else None


RECONFIRM_NOTE = "Tính lại theo quy tắc đã sửa (11/2026) từ câu trả lời đã chấm của bài kiểm tra hoàn thành; không dùng dữ liệu mới."


def reconfirm_levels(user_id: uuid.UUID) -> list[str]:
    """Re-apply the corrected rule to completion checks passed under the old one-step cap.

    The stored, already graded answers are read again: if they prove the lesson's level (every level up to
    it mastered by the same estimate as a new check), the verified level is raised to it. Nothing is
    regraded, no stored result is changed, a level never goes down, and running it twice does nothing.
    """
    from backend.engine.test_engine import estimate_level

    profile = store.get_or_create_profile(user_id)
    assessed = profile.setdefault("assessed_skills", {})
    raised: list[str] = []
    now = utcnow().isoformat()
    for row in lesson_checks(user_id):
        activity = store.get_activity(row["activity_id"]) or {}
        if row["status"] != "PASSED" or not activity or level_confirmed(user_id, activity):
            continue
        levels: dict[int, tuple[float, int]] = {}
        for item in (row["payload"].get("result") or {}).get("item_results", []):
            earned, count = levels.get(int(item["level"]), (0.0, 0))
            levels[int(item["level"])] = (earned + float(item.get("credit") or 0), count + 1)
        if 1 not in levels:
            continue
        skill = activity["target_skill"]
        current = (assessed.get(skill) or {}).get("level")
        observed = min(estimate_level(levels)[0], confirmable_level(activity))
        if current is not None and observed <= int(current):
            continue
        with store.db.transaction():
            # Its own source id: the original pass already holds one evidence row for this check.
            store.add_skill_evidence(user_id, skill, observed, "MINI_TEST", f"{row['micro_id']}:reconfirm", score=(row["payload"].get("result") or {}).get("score", 0) / 100,
                                     task_id=f"LESSON:{row['activity_id']}", scope_note=RECONFIRM_NOTE, created_at=now)
            assessed[skill] = {**(assessed.get(skill) or {}), "level": observed, "submission_id": row["micro_id"], "assessed_at": now, "assessment_status": "VERIFIED",
                               "source_type": "MINI_TEST", "task_id": f"LESSON:{row['activity_id']}", "scope_note": RECONFIRM_NOTE}
            profile["updated_at"] = now
            store.persist_user_runtime(user_id)
        store.add_history_event(user_id, "LEVEL_RECONFIRMED", f"Xác nhận lại mức {skill}: {current} → {observed} từ bài kiểm tra {activity.get('title', row['activity_id'])} đã chấm.",
                                meta={"micro_id": row["micro_id"], "activity_id": row["activity_id"], "skill_code": skill})
        raised.append(skill)
    if raised:
        from backend.api.roadmaps import replan

        replan(user_id, f"Xác nhận lại mức {', '.join(raised)} theo quy tắc đã sửa.")
    return raised


def task_state(progress: Optional[dict], latest_check: Optional[dict], confirmed: bool = True) -> str:
    status = (progress or {}).get("status") or "NOT_STARTED"
    if status != "COMPLETED":
        return "NOT_STARTED" if status == "NOT_STARTED" else "IN_PROGRESS"
    if not latest_check or latest_check["status"] not in GRADED:
        return "PENDING_ASSESSMENT"
    # A check passed under the old one-step rule can leave the skill below the lesson's level: not verified yet.
    return "VERIFIED" if latest_check["status"] == "PASSED" and confirmed else "NEEDS_REVIEW"


def latest_graded(checks: list[dict]) -> Optional[dict]:
    """The check that decides the state (newest first): the last graded result, so an open retry
    leaves a failed activity at NEEDS_REVIEW; else the open check; else one the bank could not fill."""
    for statuses in (GRADED, ("PENDING",), ("UNAVAILABLE",)):
        found = next((row for row in checks if row["status"] in statuses), None)
        if found:
            return found
    return None


def check_summary(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    result = row["payload"].get("result") or {}
    return {"micro_id": row["micro_id"], "status": row["status"], "score": result.get("score"), "passed": result.get("passed"),
            "submitted_at": row["submitted_at"], "created_at": row["created_at"], "attempt_no": row["payload"].get("attempt_no"),
            "pass_threshold": row["payload"].get("pass_threshold")}


def learning_tasks(user_id: uuid.UUID) -> dict:
    """Every learning activity of the current roadmap with its derived state and latest check."""
    roadmap = store.roadmaps.get(user_id) or {}
    progress = roadmap.get("activity_progress", {})
    plan = roadmap.get("activity_plan") or {}
    checks: dict[str, list[dict]] = {}
    for row in lesson_checks(user_id):
        checks.setdefault(row["activity_id"], []).append(row)
    tasks = []
    for activity_id, planned in plan.items():
        if planned.get("kind", "LEARNING") != "LEARNING":
            continue
        own = checks.get(activity_id, [])
        deciding = latest_graded(own)
        tasks.append({
            "activity_id": activity_id, "state": task_state(progress.get(activity_id), deciding, level_confirmed(user_id, store.get_activity(activity_id) or {})), "progress": progress.get(activity_id) or {"status": "NOT_STARTED", "progress_percent": 0},
            "latest_check": check_summary(deciding), "open_check_id": next((row["micro_id"] for row in own if row["status"] == "PENDING"), None),
            "graded_attempts": len([row for row in own if row["status"] in GRADED]),
        })
    counts = {state: sum(1 for task in tasks if task["state"] == state) for state in TASK_STATES}
    return {"tasks": tasks, "counts": counts, "total": len(tasks)}


def skill_mastery(user_id: uuid.UUID, evaluation: dict) -> list[dict]:
    """Verified level per target skill from the gap evaluation, plus the learner's graded check history.

    Only graded checks (passed or failed) appear; blank, cancelled or unavailable checks never count.
    """
    history: dict[str, list[dict]] = {}
    rows = store.db.query(
        "SELECT micro_id, skill_code, activity_id, status, submitted_at, payload FROM micro_assessments WHERE user_id = ? AND status IN ('PASSED', 'FAILED') ORDER BY submitted_at DESC",
        (str(user_id),),
    )
    for row in rows:
        payload = json.loads(row["payload"])
        history.setdefault(row["skill_code"], []).append({
            "micro_id": row["micro_id"], "activity_id": row["activity_id"], "activity_title": payload.get("activity_title"), "status": row["status"],
            "score": (payload.get("result") or {}).get("score"), "submitted_at": row["submitted_at"], "kind": payload.get("kind", "MINI_TEST"),
        })
    skills = []
    for item in evaluation.get("skill_evaluations", []):
        code = item["skill_code"]
        attempts = history.get(code, [])
        current, target = item.get("current_level"), item["target_level"]
        if current is None:
            status = "IN_PROGRESS" if attempts else "NOT_ASSESSED"
        elif current >= target:
            status = "VERIFIED"
        else:
            status = "NEEDS_IMPROVEMENT"
        evidence = item.get("evidence") or {}
        skills.append({
            "skill_code": code, "is_core": item.get("is_core"), "current_level": current, "target_level": target, "status": status,
            "evidence_score": round(evidence["score"] * 100, 1) if evidence.get("score") is not None else None, "evidence_source": evidence.get("source_type"),
            "assessed_at": evidence.get("assessed_at"), "latest_check": attempts[0] if attempts else None, "history": attempts[:10],
        })
    return skills
