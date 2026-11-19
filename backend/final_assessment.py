"""Final career assessment at the end of the learning roadmap.

It opens only when every lesson of the roadmap has passed its completion check. The form takes one
practical task per JD skill from the Career Adapt exam bank, at the difficulty of the level the JD
asks for, preferring the dataset variant the learner has not seen. Grading is the exam's test-case
engine; nothing is graded by AI. The verdict is not the total alone: it needs the total, every core
skill at its JD level, enough of the JD's weight met, no blank task and no critical error.

The result is stored as skill evidence. A level can rise from it but never drops because of it.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status

from backend import assessment_policy as policy, config
from backend.clock import utcnow
from backend.database import dumps
from backend.engine.exam_grader import BANK_VERSION, PASS_THRESHOLD, TIER_LABELS, plan_questions, verify_exam
from backend.store import store
from backend.targeting import evaluate_learner, resolve_target

GRACE_SECONDS = 30
MAX_FOCUS_VIOLATIONS = 3
MAX_EVENTS = 300
RETAKE_HOURS = policy.FINAL_RETAKE_HOURS
COVERAGE_REQUIRED = policy.FINAL_COVERAGE_REQUIRED
OPEN = ("IN_PROGRESS", "SUBMITTED", "GRADING")
SCOPE_NOTE = ("Đạt tiêu chí đánh giá theo JD đã chọn trong phạm vi các bài đã đo. "
              "Đây không phải chứng chỉ nghề và không bảo đảm được tuyển dụng hay được nhận thực tập.")


def _key(user_id: uuid.UUID) -> str:
    return str(user_id)


def _load(row: Optional[dict]) -> Optional[dict]:
    return {**row, "payload": json.loads(row["payload"])} if row else None


def _attempt(attempt_id: str) -> Optional[dict]:
    return _load(store.db.one("SELECT * FROM final_attempts WHERE attempt_id = ?", (attempt_id,)))


def attempts(user_id: uuid.UUID) -> list[dict]:
    rows = store.db.query("SELECT * FROM final_attempts WHERE user_id = ? AND archived_by_run IS NULL AND status != 'ARCHIVED' ORDER BY started_at DESC", (_key(user_id),))
    return [_load(row) for row in rows]


def _summary(attempt: dict) -> dict:
    result = attempt["payload"].get("result") or {}
    return {"attempt_id": attempt["attempt_id"], "status": attempt["status"], "started_at": attempt["started_at"], "submitted_at": attempt["submitted_at"],
            "score": result.get("score"), "passed": result.get("passed"), "auto_submitted": bool(attempt["auto_submitted"])}


def status_for(user_id: uuid.UUID, states: Optional[dict] = None) -> dict:
    """Whether the final assessment is open to this learner, and why not if it is not."""
    from backend.learning_journey import lesson_states

    roadmap = store.roadmaps.get(user_id) or {}
    if not roadmap.get("schedule"):
        # Same keys as the full answer below: start() reads can_start, and a missing key was a server error (audit 2026-11-15).
        return {"eligible": False, "can_start": False, "reason": "Chưa có lộ trình học tập.", "lessons_remaining": None, "remaining_ids": [], "attempts": [], "current": None,
                "passed_attempt_id": None, "retake_at": None, "pass_rules": {"score": PASS_THRESHOLD, "coverage": round(COVERAGE_REQUIRED * 100), "retake_hours": RETAKE_HOURS}}
    states = states if states is not None else lesson_states(user_id)
    remaining = [activity_id for activity_id, item in states.items() if item["learning_state"] != "COMPLETED"]
    history = attempts(user_id)
    current = next((item for item in history if item["status"] in OPEN), None)
    graded = [item for item in history if item["status"] == "GRADED"]
    passed = next((item for item in graded if (item["payload"].get("result") or {}).get("passed")), None)
    retake_at = None
    if graded and not passed:
        retake_at = (datetime.fromisoformat(graded[0]["submitted_at"]) + timedelta(hours=RETAKE_HOURS)).isoformat()
    reason = None
    if remaining:
        reason = f"Còn {len(remaining)} bài học chưa đạt bài kiểm tra hoàn thành."
    elif passed:
        reason = "Bạn đã đạt bài đánh giá tổng hợp."
    elif retake_at and utcnow() < datetime.fromisoformat(retake_at) and not current:
        reason = "Bạn có thể làm lại sau thời gian chờ để kịp ôn phần còn thiếu."
    return {
        "eligible": not remaining, "can_start": not remaining and not passed and not current and (not retake_at or utcnow() >= datetime.fromisoformat(retake_at)),
        "reason": reason, "lessons_remaining": len(remaining), "remaining_ids": remaining, "attempts": [_summary(item) for item in history],
        "current": _summary(current) if current else None, "passed_attempt_id": passed["attempt_id"] if passed else None, "retake_at": retake_at,
        "pass_rules": {"score": PASS_THRESHOLD, "coverage": round(COVERAGE_REQUIRED * 100), "retake_hours": RETAKE_HOURS},
    }


def _seen_items(user_id: uuid.UUID) -> set[str]:
    seen: set[str] = set()
    for table in ("exam_attempts", "final_attempts"):
        for row in store.db.query(f"SELECT payload FROM {table} WHERE user_id = ?", (_key(user_id),)):
            seen.update(item["item_id"] for item in json.loads(row["payload"]).get("questions", []))
    return seen


def start(user_id: uuid.UUID) -> dict:
    """Create the attempt, or return the one in progress. Resuming never restarts the clock."""
    current = next((item for item in attempts(user_id) if item["status"] in OPEN), None)
    if current:
        return current
    state = status_for(user_id)
    if not state["can_start"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=state["reason"] or "Chưa thể bắt đầu bài đánh giá tổng hợp.")
    profile = store.get_or_create_profile(user_id)
    requirements = resolve_target(profile).get("requirements_by_skill", {})
    # The difficulty of each task is the level the JD asks for, not the learner's own declaration.
    targets = {code: int(item.get("target_level", 1)) for code, item in requirements.items()}
    questions = plan_questions(requirements, targets, _seen_items(user_id), random.SystemRandom().randrange(2**31), author_id=str(user_id))
    if not questions:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mục tiêu hiện tại không có kỹ năng nào đo được nên chưa tạo được bài đánh giá.")
    for question in questions:
        question["is_core"] = bool(requirements.get(question["skill_code"], {}).get("is_core", (store.get_skill(question["skill_code"]) or {}).get("is_core")))
    minutes = sum(question["minutes"] for question in questions)
    now = utcnow()
    attempt_id = str(uuid.uuid4())
    roadmap = store.roadmaps.get(user_id) or {}
    payload = {"questions": questions, "time_limit_minutes": minutes, "bank_version": BANK_VERSION, "levels_at_roadmap_start": roadmap.get("assessed_levels", {})}
    try:
        store.db.execute(
            "INSERT INTO final_attempts(attempt_id, user_id, roadmap_version, status, started_at, expires_at, payload) VALUES (?, ?, ?, 'IN_PROGRESS', ?, ?, ?)",
            (attempt_id, _key(user_id), roadmap.get("roadmap_version"), now.isoformat(), (now + timedelta(minutes=minutes)).isoformat(), dumps(payload)),
        )
    except Exception as error:  # Two tabs pressed start: the unique index keeps one attempt.
        if "UNIQUE" not in str(error):
            raise
        return next(item for item in attempts(user_id) if item["status"] in OPEN)
    store.add_history_event(user_id, "FINAL_STARTED", f"Bắt đầu bài đánh giá tổng hợp: {len(questions)} bài, {minutes} phút.")
    return _attempt(attempt_id)


def _expired(attempt: dict) -> bool:
    return attempt["status"] == "IN_PROGRESS" and utcnow() > datetime.fromisoformat(attempt["expires_at"]) + timedelta(seconds=GRACE_SECONDS)


def queue_grading(attempt_id: str) -> bool:
    """Put a submitted final attempt on the grading queue (audit B-04)."""
    from backend import grading_queue

    def job() -> None:
        attempt = _attempt(attempt_id)
        if attempt and attempt["status"] == "SUBMITTED":
            _grade(attempt)
    return grading_queue.enqueue(f"final:{attempt_id}", job)


def queue_pending() -> int:
    from backend import grading_queue

    queued = 0
    for row in store.db.query("SELECT attempt_id, status FROM final_attempts WHERE status IN ('SUBMITTED', 'GRADING')"):
        if row["status"] == "GRADING":
            # A live lease means a worker in some process owns it; only an expired one was lost to a crash.
            if grading_queue.is_active(f"final:{row['attempt_id']}") or grading_queue.lease_alive(f"grading:final:{row['attempt_id']}"):
                continue
            store.db.execute("UPDATE final_attempts SET status = 'SUBMITTED' WHERE attempt_id = ? AND status = 'GRADING'", (row["attempt_id"],))
        queued += queue_grading(row["attempt_id"])
    return queued


def finish_expired() -> int:
    """Background sweep: a final assessment whose time ran out while the learner was away is submitted with
    what was saved (audit 2026-11-17). Before, only the entry exam had this sweep, so an abandoned final stayed
    IN_PROGRESS until the learner came back and blocked "Đổi JD mục tiêu" meanwhile."""
    now = utcnow()
    done = 0
    for row in store.db.query("SELECT user_id, expires_at FROM final_attempts WHERE status = 'IN_PROGRESS' AND archived_by_run IS NULL"):
        if now > datetime.fromisoformat(row["expires_at"]) + timedelta(seconds=GRACE_SECONDS):
            current(uuid.UUID(row["user_id"]))
            done += 1
    return done


def current(user_id: uuid.UUID) -> Optional[dict]:
    """The open attempt, settling a timeout or an unfinished grading first."""
    attempt = next((item for item in attempts(user_id) if item["status"] in OPEN), None)
    if attempt is None:
        return None
    if _expired(attempt):
        submit(user_id, auto=True)
    elif attempt["status"] == "SUBMITTED":
        queue_grading(attempt["attempt_id"])
    return _attempt(attempt["attempt_id"])


def _open(user_id: uuid.UUID) -> dict:
    attempt = current(user_id)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không có bài đánh giá tổng hợp đang làm.")
    if attempt["status"] != "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài đã nộp nên không thể sửa.")
    return attempt


def _question(attempt: dict, question_id: str) -> dict:
    question = next((item for item in attempt["payload"]["questions"] if item["question_id"] == question_id), None)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Câu hỏi không thuộc bài này.")
    return question


def public_state(attempt: dict) -> dict:
    from backend.exam_service import public_state as exam_view

    view = exam_view(attempt)
    view["max_violations"] = MAX_FOCUS_VIOLATIONS
    view["kind"] = "FINAL"
    return view


def save_response(user_id: uuid.UUID, question_id: str, text: str, base_saved_at: Optional[str] = None) -> dict:
    from backend.exam_service import write_response

    attempt = _open(user_id)
    question = _question(attempt, question_id)
    if len(text) > question["max_chars"]:
        raise HTTPException(status_code=413, detail=f"Câu trả lời vượt giới hạn {question['max_chars']} ký tự.")
    return write_response("final_attempts", attempt["attempt_id"], question_id, text, base_saved_at)


def run_code(user_id: uuid.UUID, question_id: str, code: str) -> dict:
    from backend.exam_service import run_question_code

    attempt = _open(user_id)
    return run_question_code(user_id, _question(attempt, question_id), code)


def record_event(user_id: uuid.UUID, kind: str, detail: str) -> dict:
    """Log an integrity event. Leaving the assessment a third time submits it."""
    attempt = current(user_id)
    if attempt is None or attempt["status"] != "IN_PROGRESS":
        return {"violations": attempt["violations"] if attempt else 0, "max_violations": MAX_FOCUS_VIOLATIONS, "auto_submitted": False, "status": attempt["status"] if attempt else None}
    if store.db.one("SELECT COUNT(*) AS n FROM exam_events WHERE attempt_id = ?", (attempt["attempt_id"],))["n"] < MAX_EVENTS:
        store.db.execute("INSERT INTO exam_events(event_id, attempt_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), attempt["attempt_id"], kind, detail[:200], utcnow().isoformat()))
    if kind == "focus_lost":
        store.db.execute("UPDATE final_attempts SET violations = violations + 1 WHERE attempt_id = ?", (attempt["attempt_id"],))
    violations = store.db.one("SELECT violations FROM final_attempts WHERE attempt_id = ?", (attempt["attempt_id"],))["violations"]
    forced = violations >= MAX_FOCUS_VIOLATIONS
    if forced:
        submit(user_id, auto=True)
    return {"violations": violations, "max_violations": MAX_FOCUS_VIOLATIONS, "auto_submitted": forced, "status": "SUBMITTED" if forced else "IN_PROGRESS"}


def submit(user_id: uuid.UUID, auto: bool = False) -> dict:
    attempt = next((item for item in attempts(user_id) if item["status"] in OPEN), None)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không có bài đánh giá tổng hợp đang làm.")
    claimed = store.db.execute(
        "UPDATE final_attempts SET status = 'SUBMITTED', submitted_at = ?, auto_submitted = ? WHERE attempt_id = ? AND status = 'IN_PROGRESS'",
        (utcnow().isoformat(), int(auto), attempt["attempt_id"]),
    ).rowcount
    attempt = _attempt(attempt["attempt_id"])
    if attempt["status"] == "SUBMITTED":
        queue_grading(attempt["attempt_id"])
        attempt = _attempt(attempt["attempt_id"])
    return {"is_duplicate": not claimed, "status": attempt["status"], "auto_submitted": bool(attempt["auto_submitted"]), "attempt_id": attempt["attempt_id"]}


def _answers(attempt_id: str) -> dict[str, str]:
    rows = store.db.query("SELECT question_id, answer_text FROM exam_responses WHERE attempt_id = ?", (attempt_id,))
    return {row["question_id"]: row["answer_text"] or "" for row in rows}


def evaluate(questions: list[dict], answers: dict[str, str]) -> dict:
    """The verdict from the test cases alone, with each rule shown separately."""
    verifier = verify_exam(questions, answers)
    skills, total = [], 0.0
    blank, critical = [], [gate for gate, hit in verifier["critical"].items() if hit]
    for question in questions:
        result = verifier["skill_results"][question["skill_code"]]
        share = float(question["weight"]) * 100
        points = round(share * float(result["score"]), 2)
        total += points
        if result["blank"]:
            blank.append(question["label"])
        skills.append({
            "skill_code": question["skill_code"], "question_id": question["question_id"], "topic": question["topic"], "tier_label": TIER_LABELS[question["tier"]],
            "verified_level": int(result["level"]), "target_level": int(question["target_level"]), "met": int(result["level"]) >= int(question["target_level"]),
            "is_core": bool(question.get("is_core")), "weight": round(float(question["weight"]), 4), "percent": round(float(result["score"]) * 100),
            "points": points, "max_points": round(share, 2), "blank": result["blank"], "missing": result.get("next_steps", [])[:4],
        })
    total = round(total, 2)
    coverage = sum(item["weight"] for item in skills if item["met"]) / (sum(item["weight"] for item in skills) or 1)
    core_short = [item["skill_code"] for item in skills if item["is_core"] and not item["met"]]
    rules = [
        {"rule": "SCORE", "passed": total >= PASS_THRESHOLD, "detail": f"Điểm tổng {total:g}/100, cần từ {PASS_THRESHOLD:g}."},
        {"rule": "CORE", "passed": not core_short, "detail": "Mọi kỹ năng cốt lõi đạt mức JD." if not core_short else f"Kỹ năng cốt lõi chưa đạt mức JD: {', '.join(core_short)}."},
        {"rule": "COVERAGE", "passed": coverage >= COVERAGE_REQUIRED, "detail": f"Đáp ứng {round(coverage * 100)}% trọng số yêu cầu của JD, cần từ {round(COVERAGE_REQUIRED * 100)}%."},
        {"rule": "COMPLETE", "passed": not blank, "detail": "Đã làm đủ mọi bài thực hành." if not blank else f"Bỏ trống: {', '.join(blank)}."},
        {"rule": "CRITICAL", "passed": not critical, "detail": "Không mắc lỗi trọng yếu." if not critical else "Mắc lỗi trọng yếu trong bài làm."},
    ]
    return {"score": total, "passed": all(rule["passed"] for rule in rules), "coverage": round(coverage * 100), "rules": rules, "skills": skills,
            "test_cases": verifier["test_cases"], "critical_gates": critical}


def _grade(attempt: dict) -> None:
    claimed = store.db.execute("UPDATE final_attempts SET status = 'GRADING' WHERE attempt_id = ? AND status = 'SUBMITTED'", (attempt["attempt_id"],)).rowcount
    if not claimed:
        return
    user_id = uuid.UUID(attempt["user_id"])
    try:
        result = evaluate(attempt["payload"]["questions"], _answers(attempt["attempt_id"]))
    except Exception:
        # The answers are saved; the next read grades again.
        store.db.execute("UPDATE final_attempts SET status = 'SUBMITTED' WHERE attempt_id = ?", (attempt["attempt_id"],))
        raise
    with store.user_scope(user_id):
        _apply_final(user_id, attempt, result)


def _apply_final(user_id: uuid.UUID, attempt: dict, result: dict) -> None:
    now = utcnow().isoformat()
    profile = store.get_or_create_profile(user_id)
    assessed = profile.setdefault("assessed_skills", {})
    changes = []
    for item in result["skills"]:
        before = (assessed.get(item["skill_code"]) or {}).get("level")
        # A single assessment can raise a verified level, never lower it.
        after = item["verified_level"] if before is None else max(int(before), item["verified_level"])
        item.update(level_before=before, level_after=after)
        changes.append(item)
    result.update(scope_note=SCOPE_NOTE, graded_at=now)
    payload = {**attempt["payload"], "result": result}
    with store.db.transaction():
        store.db.execute("UPDATE final_attempts SET status = 'GRADED', payload = ? WHERE attempt_id = ?", (dumps(payload), attempt["attempt_id"]))
        for item in changes:
            store.add_skill_evidence(user_id, item["skill_code"], item["verified_level"], "FINAL_ASSESSMENT", attempt["attempt_id"], score=item["percent"] / 100,
                                     task_id=f"FINAL:{item['question_id']}", rubric_version=BANK_VERSION, scope_note=SCOPE_NOTE, created_at=now)
            if item["level_after"] != item["level_before"]:
                assessed[item["skill_code"]] = {
                    "level": item["level_after"], "score": item["percent"] / 100, "confidence": None, "submission_id": attempt["attempt_id"], "assessed_at": now,
                    "assessment_status": "VERIFIED", "source_type": "FINAL_ASSESSMENT", "task_id": f"FINAL:{item['question_id']}", "scope_note": SCOPE_NOTE,
                }
        profile["updated_at"] = now
        store.persist_user_runtime(user_id)
    raised = [item for item in changes if item["level_after"] != item["level_before"]]
    if raised:
        from backend.api.roadmaps import replan

        replan(user_id, "Bài đánh giá tổng hợp nâng mức đã xác thực của " + ", ".join(item["skill_code"] for item in raised) + ".")
    store.add_history_event(user_id, "FINAL_GRADED", f"Bài đánh giá tổng hợp: {result['score']:g}/100 ({'Đạt' if result['passed'] else 'Chưa đạt'})",
                            version=BANK_VERSION, meta={"attempt_id": attempt["attempt_id"], "passed": result["passed"]})


def review(user_id: uuid.UUID, attempt_id: str) -> dict:
    """A graded attempt with every task, its marks and the reasons, plus the completion summary."""
    from backend.exam_service import _dataset_view, _explain_case, _workspace
    from backend.learning_journey import lesson_states

    attempt = _attempt(attempt_id)
    if not attempt or attempt["user_id"] != _key(user_id) or attempt["archived_by_run"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài đánh giá.")
    if attempt["status"] == "SUBMITTED":
        queue_grading(attempt_id)
        attempt = _attempt(attempt_id)
    if attempt["status"] in ("SUBMITTED", "GRADING"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài đang được chấm. Kết quả sẽ có sau ít phút.")
    if attempt["status"] != "GRADED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài đánh giá chưa được chấm xong.")
    result = attempt["payload"]["result"]
    answers = _answers(attempt_id)
    questions = []
    for question in attempt["payload"]["questions"]:
        skill = next(item for item in result["skills"] if item["question_id"] == question["question_id"])
        cases = []
        for case in question["cases"]:
            outcome = result["test_cases"].get(f"{question['question_id']}.{case['id']}") or {}
            row = {"description": case["description"], "passed": bool(outcome.get("passed")), "expected_summary": outcome.get("expected_summary") or case["description"],
                   "actual_summary": outcome.get("actual_summary") or "", "failure_code": outcome.get("failure_code"),
                   "points_awarded": round(skill["max_points"] * case["points"] / 100, 2) if outcome.get("passed") else 0, "points_max": round(skill["max_points"] * case["points"] / 100, 2)}
            row["explanation"] = _explain_case(row)
            cases.append(row)
        questions.append({
            "question_id": question["question_id"], "label": question["label"], "topic": question["topic"], "skill_code": question["skill_code"], "tier_label": TIER_LABELS[question["tier"]],
            "prompt": question["prompt"], "answer_type": question["answer_type"], "workspace": _workspace(question), "dataset": _dataset_view(question["dataset"]),
            "answer": answers.get(question["question_id"], ""), "blank": skill["blank"], "points_awarded": skill["points"], "max_points": skill["max_points"],
            "correct": skill["points"] >= skill["max_points"], "critical": [], "cases": cases, "ai_comment": None,
        })
    states = lesson_states(user_id)
    evaluation = evaluate_learner(user_id)
    remaining = [{"skill_code": item["skill_code"], "current_level": item.get("current_level"), "target_level": item["target_level"]} for item in evaluation["skill_evaluations"] if item.get("gap")]
    weak_lessons = []
    for item in result["skills"]:
        if not item["met"]:
            weak_lessons += [{"activity_id": activity_id, "title": (store.get_activity(activity_id) or {}).get("title"), "skill_code": item["skill_code"]}
                             for activity_id in states if (store.get_activity(activity_id) or {}).get("target_skill") == item["skill_code"]]
    from backend.learning_journey import study_seconds

    return {
        "attempt_id": attempt_id, "submitted_at": attempt["submitted_at"], "auto_submitted": bool(attempt["auto_submitted"]), "violations": attempt["violations"],
        "score": result["score"], "max_score": 100, "pass_threshold": PASS_THRESHOLD, "passed": result["passed"], "coverage": result["coverage"], "rules": result["rules"],
        "skills": result["skills"], "questions": questions, "scope_note": result["scope_note"],
        "summary": {
            "study_seconds": sum(study_seconds(user_id).values()), "lessons_done": sum(1 for item in states.values() if item["learning_state"] == "COMPLETED"),
            "lessons_total": len(states), "levels_at_roadmap_start": attempt["payload"].get("levels_at_roadmap_start", {}),
            "remaining_gaps": remaining, "weak_lessons": weak_lessons,
        },
        "retake_at": None if result["passed"] else (datetime.fromisoformat(attempt["submitted_at"]) + timedelta(hours=RETAKE_HOURS)).isoformat(),
    }
