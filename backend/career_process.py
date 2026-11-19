"""The Career Adapt process: one account, one run, steps in a fixed order.

The server owns the step. Each step's data goes through the endpoint that already handles it
(skill report, target JD, roadmap); those endpoints call ``guard_step`` first and report back
here when they finish, so a skipped step, a return to an earlier step or an edit after completion
is refused however the request was made. A reset archives instead of deleting, and ``store``
keeps serving the same profile fields, so the gap and roadmap engines did not have to change.
"""
from __future__ import annotations

import copy
import json
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status

from backend.clock import utcnow
from backend.database import ARCHIVABLE_TABLES, ROADMAP_ARCHIVABLE_TABLES, dumps
from backend.store import store

STEPS = ("SKILLS", "JD", "EXAM", "RESULT", "ROADMAP", "DONE")
STEP_LABELS = {"SKILLS": "Báo cáo kỹ năng", "JD": "Chọn JD", "EXAM": "Bài kiểm tra", "RESULT": "Kết quả", "ROADMAP": "Lộ trình", "DONE": "Hoàn tất"}
CAREERS = (
    {"career_code": "DATA_ANALYST", "title": "Data Analyst", "status": "ACTIVE", "summary": "Đầy đủ dữ liệu, bài kiểm tra và lộ trình."},
    {"career_code": "BACKEND_DEVELOPER", "title": "Backend Developer", "status": "SIMULATED", "summary": "Giao diện mô phỏng định hướng sản phẩm. Chưa có dữ liệu và bài kiểm tra."},
    {"career_code": "QA_TESTER", "title": "QA Tester", "status": "SIMULATED", "summary": "Giao diện mô phỏng định hướng sản phẩm. Chưa có dữ liệu và bài kiểm tra."},
)
PROCESS_PROFILE_FIELDS = ("self_reported_skills", "skill_report", "target_jd", "custom_job_profile", "assessed_skills", "job_profile_id")
DEFAULT_JOB_PROFILE = "VN_ENTRY_ANALYST"


def _load(row: Optional[dict]) -> Optional[dict]:
    return {**row, "payload": json.loads(row["payload"])} if row else None


def active_run(user_id: uuid.UUID) -> Optional[dict]:
    return _load(store.db.one("SELECT * FROM career_runs WHERE user_id = ? AND status != 'ARCHIVED'", (str(user_id),)))


def run_history(user_id: uuid.UUID) -> list[dict]:
    rows = store.db.query("SELECT run_id, career_code, status, step, created_at, completed_at, archived_at FROM career_runs WHERE user_id = ? AND status = 'ARCHIVED' ORDER BY archived_at DESC", (str(user_id),))
    return rows


def career(career_code: str) -> Optional[dict]:
    return next((item for item in CAREERS if item["career_code"] == career_code), None)


def public_run(run: Optional[dict]) -> Optional[dict]:
    if not run:
        return None
    payload = run["payload"]
    return {
        "run_id": run["run_id"], "career_code": run["career_code"], "career_title": career(run["career_code"])["title"], "status": run["status"], "step": run["step"],
        "step_index": STEPS.index(run["step"]), "created_at": run["created_at"], "completed_at": run["completed_at"],
        "skill_method": payload.get("skill_method"), "skills": payload.get("skills", []), "jd": payload.get("jd"),
        "goal_change": bool(payload.get("goal_change")), "goal_changes": len(payload.get("goal_history", [])),
    }


def save_run(run: dict, **columns: Any) -> None:
    fields = {"payload": dumps(run["payload"]), "updated_at": utcnow().isoformat(), **columns}
    assignments = ", ".join(f"{name} = ?" for name in fields)
    store.db.execute(f"UPDATE career_runs SET {assignments} WHERE run_id = ?", (*fields.values(), run["run_id"]))
    run.update(columns)


def guard_step(user_id: uuid.UUID, step: str, action: str) -> Optional[dict]:
    """Refuse an action outside its step. Accounts with no run keep the plain API behaviour."""
    run = active_run(user_id)
    if run is None:
        return None
    if run["status"] == "COMPLETED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Quy trình Career Adapt đã hoàn tất nên không thể {action}. Muốn làm lại, hãy reset quy trình.")
    if run["step"] != step:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Không thể {action} ở bước {STEP_LABELS[run['step']]}. Các bước phải làm tuần tự và không được quay lại.")
    return run


def advance(run: dict, expected: str, **payload_updates: Any) -> dict:
    """Move one step forward. The WHERE clause makes a repeated or racing call a no-op."""
    following = STEPS[STEPS.index(expected) + 1]
    run["payload"].update(payload_updates)
    columns: dict[str, Any] = {"step": following, "payload": dumps(run["payload"]), "updated_at": utcnow().isoformat()}
    if following == "DONE":
        columns.update(status="COMPLETED", completed_at=columns["updated_at"])
    assignments = ", ".join(f"{name} = ?" for name in columns)
    moved = store.db.execute(f"UPDATE career_runs SET {assignments} WHERE run_id = ? AND step = ?", (*columns.values(), run["run_id"], expected)).rowcount
    if not moved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bước này đã được xác nhận trước đó.")
    run.update(columns)
    run["payload"] = json.loads(columns["payload"])
    return run


def _has_learning_state(user_id: uuid.UUID) -> bool:
    profile = store.profiles.get(user_id) or {}
    return bool(profile.get("assessed_skills") or profile.get("self_reported_skills") or profile.get("skill_report") or profile.get("target_jd")
                or (store.roadmaps.get(user_id) or {}).get("schedule") or (store.roadmaps.get(user_id) or {}).get("activity_progress"))


def _archive_learning_state(user_id: uuid.UUID, run_id: str) -> dict:
    """Clear the learner's process state and tag its rows. Call inside a transaction."""
    profile = store.get_or_create_profile(user_id)
    key = str(user_id)
    snapshot = {
        "profile": {field: copy.deepcopy(profile.get(field)) for field in PROCESS_PROFILE_FIELDS},
        "roadmap": json.loads(dumps(store.roadmaps.get(user_id) or {})),
        "assessment_history": json.loads(dumps(store.progress_assessment_history.get(user_id) or [])),
    }
    now = utcnow().isoformat()
    for table in ARCHIVABLE_TABLES:
        store.db.execute(f"UPDATE {table} SET archived_by_run = ? WHERE user_id = ? AND archived_by_run IS NULL", (run_id, key))
    store.db.execute("UPDATE learning_checkins SET status = 'ARCHIVED', updated_at = ? WHERE user_id = ?", (now, key))
    store.db.execute("UPDATE micro_assessments SET status = 'ARCHIVED' WHERE user_id = ?", (key,))
    store.db.execute("UPDATE reminder_jobs SET status = 'ARCHIVED', updated_at = ? WHERE user_id = ?", (now, key))
    store.db.execute("UPDATE study_sessions SET status = 'ENDED', end_reason = 'ARCHIVED', ended_at = ?, updated_at = ? WHERE user_id = ? AND status IN ('RUNNING', 'PAUSED')", (now, now, key))
    store.db.execute("UPDATE final_attempts SET status = 'ARCHIVED' WHERE user_id = ? AND status IN ('IN_PROGRESS', 'SUBMITTED', 'GRADING')", (key,))
    for table in ROADMAP_ARCHIVABLE_TABLES:
        store.db.execute(f"UPDATE {table} SET archived_by_run = ? WHERE user_id = ? AND archived_by_run IS NULL", (run_id, key))
    for field in ("skill_report", "target_jd", "custom_job_profile"):
        profile.pop(field, None)
    profile.update(self_reported_skills=[], assessed_skills={}, job_profile_id=DEFAULT_JOB_PROFILE, updated_at=now)
    store.roadmaps.pop(user_id, None)
    store.progress_assessment_history.pop(user_id, None)
    store.persist_user_runtime(user_id)
    return snapshot


def start_run(user_id: uuid.UUID, career_code: str) -> dict:
    chosen = career(career_code)
    if chosen is None:
        raise HTTPException(status_code=422, detail="Nghề nghiệp không hợp lệ.")
    if chosen["status"] != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{chosen['title']} mới là giao diện mô phỏng, chưa có dữ liệu để thực hiện quy trình.")
    if active_run(user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tài khoản đã có một quy trình Career Adapt. Mỗi tài khoản chỉ thực hiện một quy trình; muốn làm lại hãy reset từ mục Quy trình Career Adapt.")
    now = utcnow().isoformat()
    run_id = str(uuid.uuid4())
    with store.db.transaction():
        # Results from before this process existed stay in the account as an archived entry.
        if _has_learning_state(user_id):
            legacy_id = str(uuid.uuid4())
            snapshot = _archive_learning_state(user_id, legacy_id)
            store.db.execute(
                "INSERT INTO career_runs(run_id, user_id, career_code, status, step, payload, created_at, updated_at, archived_at) VALUES (?, ?, ?, 'ARCHIVED', 'DONE', ?, ?, ?, ?)",
                (legacy_id, str(user_id), "DATA_ANALYST", dumps({"legacy": True, "archive": snapshot}), now, now, now),
            )
        store.db.execute(
            "INSERT INTO career_runs(run_id, user_id, career_code, status, step, payload, created_at, updated_at) VALUES (?, ?, ?, 'IN_PROGRESS', 'SKILLS', '{}', ?, ?)",
            (run_id, str(user_id), career_code, now, now),
        )
    store.add_history_event(user_id, "PROCESS_STARTED", f"Bắt đầu Quy trình Career Adapt: {chosen['title']}")
    return active_run(user_id)


def on_skills_confirmed(user_id: uuid.UUID, method: str) -> None:
    run = active_run(user_id)
    if run and run["step"] == "SKILLS":
        profile = store.get_or_create_profile(user_id)
        advance(run, "SKILLS", skill_method=method, skills=copy.deepcopy(profile.get("self_reported_skills", [])))


def measured_gaps(user_id: uuid.UUID, target: dict) -> list[str]:
    """Skills the target weighs that have no verified level yet."""
    assessed = store.get_or_create_profile(user_id).get("assessed_skills") or {}
    return [code for code, item in (target.get("requirements_by_skill") or {}).items() if float(item.get("weight", 0)) > 0 and code not in assessed]


def change_goal(user_id: uuid.UUID) -> dict:
    """Reopen the JD step after the process is done, keeping every verified level (audit A-05).

    Verified levels describe the learner, not the JD, so they stay. Nothing is archived: the exam,
    its review, evidence, lesson history and study time remain. After the new JD is confirmed the run
    goes straight to the roadmap step; skills the new JD weighs that were never measured show as
    "not assessed" and are measured by lesson checks and the final assessment.
    """
    run = active_run(user_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài khoản chưa có quy trình nào.")
    if run["step"] not in {"ROADMAP", "DONE"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chỉ đổi mục tiêu được sau khi đã có kết quả bài kiểm tra. Hãy hoàn tất bước hiện tại trước.")
    from backend import final_assessment

    final_assessment.current(user_id)  # settles a final assessment whose time already ran out
    busy = store.db.one("SELECT 1 AS n FROM final_attempts WHERE user_id = ? AND status IN ('IN_PROGRESS', 'SUBMITTED', 'GRADING') AND archived_by_run IS NULL", (str(user_id),))
    if busy:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài đánh giá tổng hợp đang diễn ra. Hãy nộp bài trước khi đổi mục tiêu.")
    now = utcnow().isoformat()
    history = run["payload"].setdefault("goal_history", [])
    history.append({"jd": run["payload"].get("jd"), "changed_at": now})
    # Where the run stood, so the learner can step back out of the change before picking a new JD.
    run["payload"]["goal_change"] = True
    run["payload"]["goal_change_from"] = {"step": run["step"], "status": run["status"], "completed_at": run["completed_at"]}
    save_run(run, status="IN_PROGRESS", step="JD", completed_at=None)
    store.add_history_event(user_id, "GOAL_CHANGE_STARTED", "Bắt đầu đổi JD mục tiêu; mức kỹ năng đã xác thực được giữ nguyên.")
    return active_run(user_id)


def cancel_goal_change(user_id: uuid.UUID) -> dict:
    """Leave a goal change before a new JD is confirmed: the run returns to where it was (audit 2026-11-17).

    Before this, a learner who opened "Đổi JD mục tiêu" and changed their mind was held at the JD step with
    the plan locked until they picked some JD. Nothing else changed during the open change, so restoring
    the step, status and completion time is enough; the change is dropped from the goal history.
    """
    run = active_run(user_id)
    if run is None or run["step"] != "JD" or not run["payload"].get("goal_change"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Không có lần đổi mục tiêu nào đang mở để hủy.")
    before = run["payload"].pop("goal_change_from", None) or {"step": "DONE", "status": "COMPLETED", "completed_at": run.get("updated_at")}
    run["payload"]["goal_change"] = False
    history = run["payload"].get("goal_history") or []
    if history:
        history.pop()
    save_run(run, status=before["status"], step=before["step"], completed_at=before["completed_at"])
    store.add_history_event(user_id, "GOAL_CHANGE_CANCELLED", "Hủy đổi JD mục tiêu; giữ JD và lộ trình đang dùng.")
    return active_run(user_id)


def on_target_confirmed(user_id: uuid.UUID, target: dict) -> None:
    run = active_run(user_id)
    if run and run["step"] == "JD" and run["payload"].get("goal_change"):
        from backend.ai_service.assessment_provider import summarize_jd

        row = store.db.one("SELECT raw_text FROM jd_versions WHERE jd_id = ? AND jd_version = ?", (target.get("jd_id"), target.get("jd_version"))) or {}
        summary = summarize_jd(target, row.get("raw_text") or "")
        requirements = [{"skill_code": code, **{key: item.get(key) for key in ("target_level", "weight", "requirement_type", "is_core")}} for code, item in target.get("requirements_by_skill", {}).items() if float(item.get("weight", 0)) > 0]
        run["payload"].pop("goal_change_from", None)
        run["payload"].update(goal_change=False, jd={
            "name": target.get("name"), "employer": target.get("employer"), "source_type": target.get("source_type"), "jd_id": target.get("jd_id"), "jd_version": target.get("jd_version"),
            "summary": summary["text"], "summary_source": summary["source"], "requirements": requirements, "additional_requirements": target.get("additional_requirements", []),
        })
        # The exam already measured this learner; a new goal only needs a new plan.
        save_run(run, step="ROADMAP")
        missing = measured_gaps(user_id, target)
        store.add_history_event(user_id, "GOAL_CHANGED", f"Đổi mục tiêu sang {target.get('name')}; giữ mức đã xác thực" + (f", chưa có bằng chứng cho {', '.join(missing)}." if missing else "."),
                                meta={"jd_id": target.get("jd_id"), "unmeasured": missing})
        return
    if run and run["step"] == "JD":
        from backend.ai_service.assessment_provider import summarize_jd

        row = store.db.one("SELECT raw_text FROM jd_versions WHERE jd_id = ? AND jd_version = ?", (target.get("jd_id"), target.get("jd_version"))) or {}
        summary = summarize_jd(target, row.get("raw_text") or "")
        requirements = [{"skill_code": code, **{key: item.get(key) for key in ("target_level", "weight", "requirement_type", "is_core")}} for code, item in target.get("requirements_by_skill", {}).items() if float(item.get("weight", 0)) > 0]
        advance(run, "JD", jd={
            "name": target.get("name"), "employer": target.get("employer"), "source_type": target.get("source_type"), "jd_id": target.get("jd_id"), "jd_version": target.get("jd_version"),
            "summary": summary["text"], "summary_source": summary["source"], "requirements": requirements, "additional_requirements": target.get("additional_requirements", []),
        })


def reset_preview(user_id: uuid.UUID) -> dict:
    """Exactly what a reset removes from view, counted from this learner's own rows."""
    run = active_run(user_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài khoản chưa có quy trình nào để reset.")
    key = str(user_id)
    count = lambda sql: store.db.one(sql, (key,))["n"]
    plan = store.roadmaps.get(user_id) or {}
    attempt = store.db.one("SELECT status FROM exam_attempts WHERE run_id = ?", (run["run_id"],))
    items = [
        {"label": "Kỹ năng đã khai báo", "count": len(run["payload"].get("skills", []))},
        {"label": "JD đã chọn và mục tiêu", "count": 1 if run["payload"].get("jd") else 0},
        {"label": "Bài kiểm tra, điểm và nhận xét", "count": 1 if attempt else 0},
        {"label": "Mức kỹ năng đã xác thực", "count": count("SELECT COUNT(*) AS n FROM skill_evidence WHERE user_id = ? AND archived_by_run IS NULL")},
        {"label": "Lộ trình học tập", "count": 1 if plan.get("schedule") else 0},
        {"label": "Tiến độ đã cập nhật", "count": len(plan.get("activity_progress") or {})},
        {"label": "Lịch kiểm tra lại và mini-test", "count": count("SELECT COUNT(*) AS n FROM learning_checkins WHERE user_id = ? AND status != 'ARCHIVED'") + count("SELECT COUNT(*) AS n FROM micro_assessments WHERE user_id = ? AND status != 'ARCHIVED'")},
        {"label": "Nhắc nhở", "count": count("SELECT COUNT(*) AS n FROM reminder_jobs WHERE user_id = ? AND status != 'ARCHIVED'")},
    ]
    return {
        "career_title": career(run["career_code"])["title"], "items": items, "exam_in_progress": bool(attempt and attempt["status"] == "IN_PROGRESS"),
        "kept": ["Tài khoản và mật khẩu", "Ngành học, giờ học và thiết lập nhắc nhở", "Lịch sử Kiểm tra kiến thức", "JD bạn đã nhập trong kho riêng", "Hội thoại với trợ lý", "Dữ liệu của tài khoản khác"],
        "archive_note": "Sau khi reset, các dữ liệu trên biến mất khỏi tài khoản và bạn làm lại từ đầu. Hệ thống giữ một bản lưu trữ ẩn để đối soát. Muốn xóa hẳn, dùng nút Xóa toàn bộ dữ liệu học tập trong Hồ sơ.",
    }


def reset_run(user_id: uuid.UUID) -> None:
    run = active_run(user_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài khoản chưa có quy trình nào để reset.")
    attempt = store.db.one("SELECT status FROM exam_attempts WHERE run_id = ?", (run["run_id"],))
    if attempt and attempt["status"] == "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài kiểm tra đang diễn ra. Hãy nộp bài trước khi reset.")
    now = utcnow().isoformat()
    with store.db.transaction():
        run["payload"]["archive"] = _archive_learning_state(user_id, run["run_id"])
        save_run(run, status="ARCHIVED", archived_at=now)
    store.add_history_event(user_id, "PROCESS_RESET", "Reset Quy trình Career Adapt; dữ liệu cũ đã chuyển vào lưu trữ.")
