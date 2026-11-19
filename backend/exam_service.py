"""The Career Adapt exam: one frozen form, a server timer, server autosave and one submission.

An attempt moves IN_PROGRESS -> SUBMITTED -> GRADING -> GRADED, each move an atomic UPDATE, so a
double click, a second tab and the timer can never submit or grade twice. Grading goes through the
V4 pipeline (``grade_submission_orchestrator``), so points, trail, AI checks and the skill update
are the same code as before.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import random
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status

from backend import career_process, grading_queue
from backend.ai_service.assessment_provider import is_enabled as ai_is_enabled
from backend.ai_service.llm_grader import grade_submission_orchestrator
from backend.api.submissions import _after_grading, _store_answers
from backend.clock import utcnow
from backend.levels import LEVEL_NAMES
from backend.database import dumps
from backend.engine.python_sandbox import DATA_FILE, run_python
from backend.engine.exam_grader import BANK_VERSION, PASS_THRESHOLD, TIER_LABELS, build_blueprint, plan_questions, verify_exam
from backend.engine.sql_sandbox import execute_readonly_sql, load_dataset
from backend.store import store

GRACE_SECONDS = 30
RUN_GAP_SECONDS = 1.0
# Longer than the slowest sandbox run, so a lease left by a killed process expires on its own.
RUN_LEASE_SECONDS = 60.0
MAX_RESULT_ROWS = 200
_run_lock = threading.Lock()
_running: set[str] = set()
_last_run: dict[str, float] = {}
MAX_FOCUS_VIOLATIONS = 3
MAX_EVENTS = 300
# Audit B-02: focus events come from the browser, which a learner controls. The server can see one thing on
# its own: how much an answer grows between two saves. Autosave runs 1.5 s after typing stops, so hundreds of
# characters in one save is a paste. It is recorded for the reviewer and shown in the review; it never changes
# a mark or a level, because pasting one's own code from the run panel is allowed.
PASTE_SIGNAL_CHARS = 300
SERVER_PASTE_EVENT = "server_large_insert"


def _attempt_for(run_id: str) -> Optional[dict]:
    row = store.db.one("SELECT * FROM exam_attempts WHERE run_id = ?", (run_id,))
    return {**row, "payload": json.loads(row["payload"])} if row else None


def _attempt_by_id(attempt_id: str) -> Optional[dict]:
    row = store.db.one("SELECT * FROM exam_attempts WHERE attempt_id = ?", (attempt_id,))
    return {**row, "payload": json.loads(row["payload"])} if row else None


def queue_grading(attempt_id: str, fault_injection: Optional[str] = None) -> bool:
    """Put a submitted attempt on the grading queue (audit B-04). Grading reads the attempt again when it starts."""
    def job() -> None:
        attempt = _attempt_by_id(attempt_id)
        if attempt and attempt["status"] == "SUBMITTED":
            _grade(attempt, fault_injection)
    return grading_queue.enqueue(f"exam:{attempt_id}", job)


def queue_pending() -> int:
    """Queue every submitted attempt; a GRADING row no worker owns was cut off by a restart and goes back to SUBMITTED."""
    queued = 0
    for row in store.db.query("SELECT attempt_id, status FROM exam_attempts WHERE status IN ('SUBMITTED', 'GRADING')"):
        if row["status"] == "GRADING":
            # A live lease means a worker in some process owns it; only an expired one was lost to a crash.
            if grading_queue.is_active(f"exam:{row['attempt_id']}") or grading_queue.lease_alive(f"grading:exam:{row['attempt_id']}"):
                continue
            store.db.execute("UPDATE exam_attempts SET status = 'SUBMITTED' WHERE attempt_id = ? AND status = 'GRADING'", (row["attempt_id"],))
        queued += queue_grading(row["attempt_id"])
    return queued


def _answers(attempt_id: str) -> dict[str, str]:
    rows = store.db.query("SELECT question_id, answer_text FROM exam_responses WHERE attempt_id = ?", (attempt_id,))
    return {row["question_id"]: row["answer_text"] for row in rows}


def _seen_items(user_id: uuid.UUID) -> set[str]:
    seen: set[str] = set()
    for row in store.db.query("SELECT payload FROM exam_attempts WHERE user_id = ?", (str(user_id),)):
        seen.update(item["item_id"] for item in json.loads(row["payload"])["questions"])
    return seen


def start(user_id: uuid.UUID) -> dict:
    """Create the single attempt for this run, or resume it. Resuming never restarts the clock."""
    run = career_process.guard_step(user_id, "EXAM", "bắt đầu bài kiểm tra")
    if run is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài kiểm tra chỉ làm trong Quy trình Career Adapt.")
    existing = _attempt_for(run["run_id"])
    if existing:
        return existing
    profile = store.get_or_create_profile(user_id)
    target = profile.get("target_jd") or {}
    declared = {item["skill_code"]: item.get("level") for item in profile.get("self_reported_skills", [])}
    questions = plan_questions(target.get("requirements_by_skill", {}), declared, _seen_items(user_id), random.SystemRandom().randrange(2**31), author_id=str(user_id))
    if not questions:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="JD đã chọn không có kỹ năng nào đo được nên chưa tạo được bài kiểm tra.")
    now = utcnow()
    minutes = sum(question["minutes"] for question in questions)
    attempt_id = str(uuid.uuid4())
    payload = {"questions": questions, "blueprint": build_blueprint(questions), "time_limit_minutes": minutes, "bank_version": BANK_VERSION}
    created = store.db.execute(
        "INSERT OR IGNORE INTO exam_attempts(attempt_id, run_id, user_id, status, started_at, expires_at, payload) VALUES (?, ?, ?, 'IN_PROGRESS', ?, ?, ?)",
        (attempt_id, run["run_id"], str(user_id), now.isoformat(), (now + timedelta(minutes=minutes)).isoformat(), dumps(payload)),
    ).rowcount
    if created:
        store.add_history_event(user_id, "EXAM_STARTED", f"Bắt đầu bài kiểm tra: {len(questions)} câu, {minutes} phút.")
    return _attempt_for(run["run_id"])


def _column_type(values: list[str]) -> str:
    filled = [value for value in values if value != ""]
    if not filled:
        return "TEXT"
    try:
        numbers = [float(value) for value in filled]
    except ValueError:
        return "TEXT"
    return "INTEGER" if all(number.is_integer() for number in numbers) and not any("." in value for value in filled) else "REAL"


def _dataset_view(name: str) -> dict:
    columns, rows = load_dataset(name)
    table = [[row.get(column, "") for column in columns] for row in rows]
    schema = [{"name": column, "type": _column_type([row[index] for row in table])} for index, column in enumerate(columns)]
    return {"table": "orders_raw", "file": DATA_FILE, "columns": columns, "rows": table, "schema": schema}


def _workspace(question: dict) -> str:
    """Attempts started before workspaces existed keep working from their frozen answer type."""
    return question.get("workspace") or {"sql": "sql", "python": "python"}.get(question["answer_type"], "report")


def public_state(attempt: dict) -> dict:
    """What the learner sees while sitting the exam: no cases, no expected values."""
    answers = _answers(attempt["attempt_id"])
    saved_at = {row["question_id"]: row["updated_at"] for row in store.db.query("SELECT question_id, updated_at FROM exam_responses WHERE attempt_id = ?", (attempt["attempt_id"],))}
    remaining = max(0, int((datetime.fromisoformat(attempt["expires_at"]) - utcnow()).total_seconds()))
    return {
        "attempt_id": attempt["attempt_id"], "status": attempt["status"], "started_at": attempt["started_at"], "server_time": utcnow().isoformat(), "remaining_seconds": remaining,
        "time_limit_minutes": attempt["payload"]["time_limit_minutes"], "violations": attempt["violations"], "max_violations": MAX_FOCUS_VIOLATIONS,
        "questions": [{
            "question_id": question["question_id"], "label": question["label"], "topic": question["topic"], "skill_code": question["skill_code"], "tier_label": TIER_LABELS[question["tier"]],
            "prompt": question["prompt"], "answer_type": question["answer_type"], "workspace": _workspace(question), "max_chars": question["max_chars"], "placeholder": question["placeholder"], "dataset": _dataset_view(question["dataset"]),
            "report_sections": question.get("report_sections", []), "answer": answers.get(question["question_id"], ""), "saved_at": saved_at.get(question["question_id"], ""),
        } for question in attempt["payload"]["questions"]],
    }


def _expired(attempt: dict) -> bool:
    return attempt["status"] == "IN_PROGRESS" and utcnow() > datetime.fromisoformat(attempt["expires_at"]) + timedelta(seconds=GRACE_SECONDS)


def current_attempt(user_id: uuid.UUID) -> Optional[dict]:
    """The learner's attempt for the active run, settling a timeout or an unfinished grading."""
    run = career_process.active_run(user_id)
    attempt = _attempt_for(run["run_id"]) if run else None
    if attempt is None:
        return None
    if _expired(attempt):
        submit(user_id, auto=True)
    elif attempt["status"] == "SUBMITTED":
        queue_grading(attempt["attempt_id"])
    return _attempt_for(run["run_id"])


def save_response(user_id: uuid.UUID, question_id: str, text: str, base_saved_at: Optional[str] = None) -> dict:
    attempt = current_attempt(user_id)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chưa có bài kiểm tra.")
    if attempt["status"] != "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài đã nộp nên không thể sửa.")
    question = next((item for item in attempt["payload"]["questions"] if item["question_id"] == question_id), None)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Câu hỏi không thuộc bài này.")
    if len(text) > question["max_chars"]:
        raise HTTPException(status_code=413, detail=f"Câu trả lời vượt giới hạn {question['max_chars']} ký tự.")
    return write_response("exam_attempts", attempt["attempt_id"], question_id, text, base_saved_at)


CHANGED_ELSEWHERE = "Câu này vừa được lưu từ một tab hoặc thiết bị khác. Hãy tải lại trang để xem bản mới nhất rồi làm tiếp."


def write_response(table: str, attempt_id: str, question_id: str, text: str, base_saved_at: Optional[str]) -> dict:
    """Store one answer of an entry exam or a final assessment (they share ``exam_responses``).

    The status check is part of the write, so an answer racing the submit cannot change a locked exam.
    ``base_saved_at`` is when the page last saw this answer saved ("" = never). When another tab or device
    saved a different text since, the write is refused instead of silently overwriting the newer answer
    (audit 2026-11-17, several tabs). Callers that send no base keep the old last-write-wins behaviour.
    """
    now = utcnow().isoformat()
    with store.db.transaction():
        if store.db.one(f"SELECT status FROM {table} WHERE attempt_id = ?", (attempt_id,))["status"] != "IN_PROGRESS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài đã nộp nên không thể sửa.")
        stored = store.db.one("SELECT answer_text, updated_at FROM exam_responses WHERE attempt_id = ? AND question_id = ?", (attempt_id, question_id))
        if base_saved_at is not None and stored and stored["updated_at"] != base_saved_at and (stored["answer_text"] or "") != text:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CHANGED_ELSEWHERE)
        _note_large_insert(attempt_id, question_id, text, now)
        store.db.execute(
            "INSERT INTO exam_responses(attempt_id, question_id, answer_text, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(attempt_id, question_id) DO UPDATE SET answer_text = excluded.answer_text, updated_at = excluded.updated_at",
            (attempt_id, question_id, text, now),
        )
    return {"question_id": question_id, "saved_at": now}


def _note_large_insert(attempt_id: str, question_id: str, text: str, now: str) -> None:
    previous = store.db.one("SELECT answer_text FROM exam_responses WHERE attempt_id = ? AND question_id = ?", (attempt_id, question_id))
    grown = len(text) - len((previous or {}).get("answer_text") or "")
    if grown >= PASTE_SIGNAL_CHARS and store.db.one("SELECT COUNT(*) AS n FROM exam_events WHERE attempt_id = ?", (attempt_id,))["n"] < MAX_EVENTS:
        store.db.execute("INSERT INTO exam_events(event_id, attempt_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
                         (str(uuid.uuid4()), attempt_id, SERVER_PASTE_EVENT, f"{question_id}: +{grown}", now))


def integrity_summary(attempt_id: str, violations: int) -> dict:
    """What was observed during the exam, for the learner and the reviewer. Never part of the mark."""
    pasted = store.db.query("SELECT detail FROM exam_events WHERE attempt_id = ? AND kind = ? ORDER BY created_at", (attempt_id, SERVER_PASTE_EVENT))
    return {
        "focus_lost": int(violations), "large_inserts": len(pasted), "large_insert_questions": sorted({row["detail"].split(":")[0] for row in pasted}),
        "note": "Số lần rời màn hình do trình duyệt báo; lần dán nhiều chữ do máy chủ tự ghi nhận. Chỉ để tham khảo, không ảnh hưởng điểm hay mức.",
    }


def _claim_run(user_id: uuid.UUID, gap: bool = True) -> str:
    """One code run per learner at a time. The set covers this process; the lease covers every worker process
    (audit B-03: with CAREERADAPT_WORKERS > 1 the in-memory set alone let one learner run code in each process)."""
    from backend.grading_queue import take_lease

    now = time.monotonic()
    with _run_lock:
        if str(user_id) in _running or (gap and now - _last_run.get(str(user_id), -RUN_GAP_SECONDS) < RUN_GAP_SECONDS):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Hãy chờ lần chạy trước kết thúc rồi thử lại.")
        _running.add(str(user_id))
        _last_run[str(user_id)] = now
    owner = take_lease(f"code-run:{user_id}", RUN_LEASE_SECONDS)
    if owner is None:
        with _run_lock:
            _running.discard(str(user_id))
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Hãy chờ lần chạy trước kết thúc rồi thử lại.")
    return owner


def run_code(user_id: uuid.UUID, question_id: str, code: str) -> dict:
    """Run the learner's code on the task's own dataset. It reports what happened, never a mark."""
    attempt = current_attempt(user_id)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chưa có bài kiểm tra.")
    if attempt["status"] != "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài đã nộp nên không thể sửa.")
    question = next((item for item in attempt["payload"]["questions"] if item["question_id"] == question_id), None)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Câu hỏi không thuộc bài này.")
    return run_question_code(user_id, question, code)


def run_question_code(user_id: uuid.UUID, question: dict, code: str) -> dict:
    """Run code for one question on its own dataset (exam, final assessment or practice). Never a mark."""
    if question["answer_type"] not in {"sql", "python"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài này không có phần chạy code.")
    if len(code) > question["max_chars"]:
        raise HTTPException(status_code=413, detail=f"Câu trả lời vượt giới hạn {question['max_chars']} ký tự.")
    with code_run_slot(user_id):
        if question["answer_type"] == "python":
            return {"kind": "python", **run_python(code, question["dataset"])}
        started = time.monotonic()
        result = execute_readonly_sql(code, question["dataset"])
        sets = [{"columns": item["columns"], "rows": item["rows"][:MAX_RESULT_ROWS], "total": len(item["rows"])} for item in result.get("result_sets", [])]
        state = "OK" if result.get("executed") and not result.get("error") else "ERROR"
        return {"kind": "sql", "status": state, "result_sets": sets[-3:], "message": result.get("error"), "elapsed_ms": int((time.monotonic() - started) * 1000)}


@contextmanager
def code_run_slot(user_id: uuid.UUID, gap: bool = True):
    """Hold the learner's one code-run slot for a block that executes their code (a run, or a practice check).

    Every path that executes a learner's code on request takes this slot, so many tabs or scripted requests
    cannot start sandbox processes in parallel (audit 2026-11-18: practice checks used to skip it). ``gap`` adds the
    short pause between two "Chạy thử" clicks; a graded check is bounded by its own run time, so it needs only the slot."""
    owner = _claim_run(user_id, gap)
    try:
        yield
    finally:
        from backend.grading_queue import drop_lease

        drop_lease(f"code-run:{user_id}", owner)
        with _run_lock:
            _running.discard(str(user_id))


def record_event(user_id: uuid.UUID, kind: str, detail: str) -> dict:
    """Log an integrity event. Leaving the exam a third time submits it."""
    attempt = current_attempt(user_id)
    if attempt is None or attempt["status"] != "IN_PROGRESS":
        return {"violations": attempt["violations"] if attempt else 0, "max_violations": MAX_FOCUS_VIOLATIONS, "auto_submitted": False, "status": attempt["status"] if attempt else None}
    if store.db.one("SELECT COUNT(*) AS n FROM exam_events WHERE attempt_id = ?", (attempt["attempt_id"],))["n"] < MAX_EVENTS:
        store.db.execute("INSERT INTO exam_events(event_id, attempt_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), attempt["attempt_id"], kind, detail[:200], utcnow().isoformat()))
    if kind == "focus_lost":
        store.db.execute("UPDATE exam_attempts SET violations = violations + 1 WHERE attempt_id = ?", (attempt["attempt_id"],))
    violations = store.db.one("SELECT violations FROM exam_attempts WHERE attempt_id = ?", (attempt["attempt_id"],))["violations"]
    forced = violations >= MAX_FOCUS_VIOLATIONS
    if forced:
        submit(user_id, auto=True)
    return {"violations": violations, "max_violations": MAX_FOCUS_VIOLATIONS, "auto_submitted": forced, "status": "SUBMITTED" if forced else "IN_PROGRESS"}


def submit(user_id: uuid.UUID, auto: bool = False, fault_injection: Optional[str] = None) -> dict:
    run = career_process.active_run(user_id)
    attempt = _attempt_for(run["run_id"]) if run else None
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chưa có bài kiểm tra.")
    claimed = store.db.execute(
        "UPDATE exam_attempts SET status = 'SUBMITTED', submitted_at = ?, auto_submitted = ? WHERE attempt_id = ? AND status = 'IN_PROGRESS'",
        (utcnow().isoformat(), int(auto), attempt["attempt_id"]),
    ).rowcount
    attempt = _attempt_for(run["run_id"])
    if attempt["status"] == "SUBMITTED":
        # The answers are locked now; grading runs on the queue so this request returns at once.
        queue_grading(attempt["attempt_id"], fault_injection)
        attempt = _attempt_for(run["run_id"])
    return {"is_duplicate": not claimed, "status": attempt["status"], "auto_submitted": bool(attempt["auto_submitted"])}


def _grade(attempt: dict, fault_injection: Optional[str] = None) -> None:
    claimed = store.db.execute("UPDATE exam_attempts SET status = 'GRADING' WHERE attempt_id = ? AND status = 'SUBMITTED'", (attempt["attempt_id"],)).rowcount
    if not claimed:
        return
    user_id = uuid.UUID(attempt["user_id"])
    try:
        submission_id = _run_grading(user_id, attempt, fault_injection)
    except Exception:
        # The answers are safe; the next read of the exam grades it again.
        store.db.execute("UPDATE exam_attempts SET status = 'SUBMITTED' WHERE attempt_id = ?", (attempt["attempt_id"],))
        raise
    run = career_process.active_run(user_id)
    with store.db.transaction():
        store.db.execute("UPDATE exam_attempts SET status = 'GRADED', submission_id = ? WHERE attempt_id = ?", (str(submission_id), attempt["attempt_id"]))
        career_process.advance(run, "EXAM", exam={"attempt_id": attempt["attempt_id"], "submission_id": str(submission_id)})


def _run_grading(user_id: uuid.UUID, attempt: dict, fault_injection: Optional[str]) -> uuid.UUID:
    questions = attempt["payload"]["questions"]
    blueprint = attempt["payload"]["blueprint"]
    stored = _answers(attempt["attempt_id"])
    answers = {question["question_id"]: stored.get(question["question_id"], "") for question in questions}
    # A previous try may have stored the submission already; the idempotency key finds it.
    key = f"exam:{attempt['attempt_id']}"
    existing = store.db.one("SELECT submission_id FROM assessment_attempts WHERE user_id = ? AND idempotency_key = ?", (str(user_id), key))
    now = utcnow()
    task_id = f"EXAM-{attempt['attempt_id'][:8].upper()}"
    task = {
        "task_id": task_id, "title": "Bài kiểm tra Career Adapt", "content_version": 1,
        "description": "\n\n".join(f"{question['label']} ({question['topic']}): {question['prompt']}" for question in questions),
        "skills_evaluated": [{"skill_code": question["skill_code"], "target_level": question["target_level"], "weight": question["weight"]} for question in questions],
    }
    if existing:
        submission_id = uuid.UUID(existing["submission_id"])
        if submission_id in store.assessments and store.assessments[submission_id].get("status") == "GRADED":
            return submission_id
    else:
        submission_id = uuid.uuid4()
        record = {
            "submission_id": submission_id, "user_id": user_id, "task_id": task_id, "mode": "ASSESSMENT", "task_version": 1, "declared_tool": "Không áp dụng", "used_assistance": False,
            "assistance_details": "", "status": "RECEIVED", "started_at": attempt["started_at"], "submitted_at": now.isoformat(),
            "elapsed_seconds": (now - datetime.fromisoformat(attempt["started_at"])).total_seconds(), "idempotency_key": key, "content_hash": None, "grade_attempts": 0, "task_snapshot": copy.deepcopy(task),
        }
        with store.db.transaction():
            store.save_submission(record)
            _store_answers(submission_id, task_id, answers, "", now.isoformat(), known={question["question_id"] for question in questions})
    assessment = grade_submission_orchestrator(
        submission_id=submission_id, user_id=user_id, task_id=task_id, mode="ASSESSMENT", fault_injection=fault_injection, task_snapshot=copy.deepcopy(task),
        declared_tool="Không áp dụng", answers=answers, exam={"blueprint": blueprint, "verifier": verify_exam(questions, answers)},
    )
    with store.user_scope(user_id):
        _after_grading(user_id, assessment)
    return submission_id


def finish_expired() -> int:
    """Background sweep: an abandoned exam is submitted with what was saved."""
    now = utcnow()
    done = 0
    for row in store.db.query("SELECT user_id, expires_at FROM exam_attempts WHERE status IN ('IN_PROGRESS', 'SUBMITTED')"):
        if now > datetime.fromisoformat(row["expires_at"]) + timedelta(seconds=GRACE_SECONDS):
            current_attempt(uuid.UUID(row["user_id"]))
            done += 1
    return done


def _ai_view(record: dict, question_id: str) -> Optional[dict]:
    item = ((record.get("ai_result") or {}).get("criteria_feedback") or {}).get(question_id)
    return {"reason": item["reason"], "evidence": [ref["value"] for ref in item["evidence"] if ref["verified"]]} if item else None


def _explain_case(case: dict) -> str:
    if case["passed"]:
        return f"Đúng: {case['description']}."
    if case["failure_code"] == "BLANK_ANSWER":
        return f"Chưa làm: {case['description']}."
    if case["expected_summary"] == case["description"]:
        return f"Sai: {case['description']}. Bài làm chưa có nội dung này."
    return f"Sai: {case['description']}. Đáp án đúng: {case['expected_summary'].rstrip('.')}. Bài làm: {case['actual_summary']}"


def _conclusion(record: dict, questions: list[dict], requirements: dict[str, dict]) -> dict:
    """The verified-level verdict, each sentence traceable to one question and its rule."""
    skills = []
    results = record.get("per_skill_results", {})
    for question in questions:
        result = results.get(question["skill_code"], {})
        level = int(result.get("level", 0))
        declared = question["declared_level"]
        percent = round(float(result.get("score", 0)) * 100)
        tier = TIER_LABELS[question["tier"]]
        if result.get("blank"):
            reason = f"Bỏ trống câu độ khó {tier} nên chưa có bằng chứng, ghi nhận mức 0."
        else:
            reason = f"Đạt {percent}/100 ở câu độ khó {tier}, tương ứng mức {level}."
            if result.get("capped_by_critical_error"):
                reason += " Mức bị giới hạn vì mắc lỗi trọng yếu."
            elif result.get("capped_by_missing_data"):
                reason += " Mức bị giới hạn ở 1 vì bài chưa có số liệu tính đúng nào; nêu khái niệm thôi chưa chứng minh được phân tích."
            elif percent >= 70 and level == question["tier"] and level < 3:
                reason += f" Câu độ khó {tier} chỉ chứng minh được tối đa mức {question['tier']}."
        if declared is not None and declared > level:
            compare = f"Thấp hơn mức tự khai ({declared})."
        elif declared is not None and declared < level:
            compare = f"Cao hơn mức tự khai ({declared})."
        elif declared is not None:
            compare = "Khớp với mức tự khai."
        else:
            compare = "Bạn không khai báo kỹ năng này."
        skills.append({"skill_code": question["skill_code"], "topic": question["topic"], "tier_label": tier, "declared_level": declared, "verified_level": level, "target_level": question["target_level"], "percent": percent, "reason": reason, "compare": compare})
    overall = record.get("final_level") or 0
    met = [item for item in skills if item["verified_level"] >= item["target_level"]]
    summary = f"Trình độ đã xác thực: {LEVEL_NAMES[overall]} (mức {overall}/3). Đáp ứng {len(met)}/{len(skills)} kỹ năng theo mức JD yêu cầu."
    if len(met) < len(skills):
        weakest = min((item for item in skills if item["verified_level"] < item["target_level"]), key=lambda item: item["verified_level"] - item["target_level"])
        summary += f" Khoảng cách lớn nhất là ở chủ đề {weakest['topic'].lower()}."
    return {"overall_level": overall, "overall_label": LEVEL_NAMES[overall], "summary": summary, "skills": skills, "scope_note": record.get("scope_note")}


def review(user_id: uuid.UUID) -> dict:
    """The locked exam with marks, why each part is right or wrong, and the verdict."""
    run = career_process.active_run(user_id)
    attempt = _attempt_for(run["run_id"]) if run else None
    if attempt is None or attempt["status"] != "GRADED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài kiểm tra chưa được chấm xong.")
    record = store.assessments[uuid.UUID(attempt["submission_id"])]
    questions = attempt["payload"]["questions"]
    answers = {row["question_id"]: row["answer_text"] or "" for row in store.db.query("SELECT question_id, answer_text FROM submission_answers WHERE submission_id = ?", (attempt["submission_id"],))}
    scoring = record["scoring"]
    criteria = {item["criterion_id"]: item for item in scoring["criteria"]}
    views = []
    for question in questions:
        cases = [item for item in scoring["test_case_results"] if item["question_id"] == question["question_id"]]
        criterion = criteria[question["question_id"]]
        blank = not answers.get(question["question_id"], "").strip()
        violations = [gate["label"] for gate in question["gates"] if any(item["gate_id"] == gate["gate_id"] for item in scoring["critical_violations"])]
        views.append({
            "question_id": question["question_id"], "label": question["label"], "topic": question["topic"], "skill_code": question["skill_code"], "tier_label": TIER_LABELS[question["tier"]],
            "prompt": question["prompt"], "answer_type": question["answer_type"], "workspace": _workspace(question), "dataset": _dataset_view(question["dataset"]), "answer": answers.get(question["question_id"], ""), "blank": blank,
            "points_awarded": criterion["points_awarded"], "max_points": criterion["max_points"], "correct": criterion["points_awarded"] >= criterion["max_points"], "critical": violations if not blank else [],
            "cases": [{"description": item["description"], "passed": item["passed"], "expected": item["expected_summary"], "actual": item["actual_summary"], "points_awarded": item["points_awarded"], "points_max": item["points_max"], "explanation": _explain_case(item)} for item in cases],
            "ai_comment": _ai_view(record, question["question_id"]),
        })
    ai = record.get("ai_result") or {}
    return {
        "submission_id": attempt["submission_id"], "submitted_at": attempt["submitted_at"], "auto_submitted": bool(attempt["auto_submitted"]), "violations": attempt["violations"],
        "integrity": integrity_summary(attempt["attempt_id"], attempt["violations"]),
        "score": record["final_score"], "max_score": 100, "pass_threshold": PASS_THRESHOLD, "passed": record["passed"], "critical_violations": [item["label"] for item in scoring["critical_violations"]],
        "questions": views, "conclusion": _conclusion(record, questions, {}), "ai": {"enabled": ai_is_enabled(), "used": ai.get("status") == "COMPLETED", "overall": ai.get("feedback") if ai.get("status") == "COMPLETED" else None, "flag": record.get("ai_flag")},
    }
