"""Assessment submissions and results (F02-F04, F08, F16-F18).

The submission is stored before anything else runs. Grading is idempotent: the same key returns
the same submission, a retry reuses the stored answers, and one submission has one assessment.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from backend.ai_service.llm_grader import ACCEPTED_STATUSES, MAX_GRADE_ATTEMPTS, RETRYABLE_STATUSES, grade_submission_orchestrator
from backend.auth import AuthenticatedUser, get_current_user
from backend.clock import utcnow
from backend.engine.jd_parser import decode_text_bytes
from backend.engine.rubric_engine import get_blueprint, public_blueprint
from backend.engine.sql_sandbox import load_dataset
from backend.store import store

router = APIRouter(tags=["F02/F03 - Assessment & Evaluation"])

MAX_ANSWER_FILE_BYTES = 1024 * 1024
ANSWER_FILE_TYPES = (".txt", ".csv", ".sql", ".py", ".md")


class SubmissionRequest(BaseModel):
    task_id: str = Field(max_length=20, description="Mã bài thử, ví dụ DA01A, DA01B, DA02A, DA03A")
    answers: Optional[dict[str, str]] = Field(default=None, description="Câu trả lời theo từng câu hỏi của đề")
    submission_text: Optional[str] = Field(default=None, max_length=30000, description="Bài làm dạng một văn bản (client cũ)")
    mode: str = Field(default="ASSESSMENT", description="Chế độ làm bài: 'ASSESSMENT' hoặc 'PRACTICE'")
    idempotency_key: Optional[str] = Field(default=None, max_length=100, description="Khóa chống xử lý trùng")
    fault_injection: Optional[str] = Field(default=None, description="Mô phỏng lỗi: 'timeout', 'invalid_json', 'conflict', 'hallucination'")
    declared_tool: str = Field(default="Chưa khai báo", max_length=80)
    used_assistance: bool = False
    assistance_details: str = Field(default="", max_length=500)
    started_at: Optional[datetime] = None


class SubmissionResponse(BaseModel):
    submission_id: uuid.UUID
    user_id: uuid.UUID
    task_id: str
    mode: str
    status: str
    submitted_at: str
    idempotency_key: Optional[str]
    is_duplicate: bool = False
    final_score: Optional[float] = None
    passed: Optional[bool] = None
    message: str


def legacy_assessment_api_enabled() -> bool:
    """Tests and scripts only. Learners sit the single exam in the Career Adapt process."""
    return os.getenv("CAREERADAPT_LEGACY_ASSESSMENT_API", "false").lower() == "true"


def fault_injection_allowed() -> bool:
    return os.getenv("CAREERADAPT_ENABLE_FAULT_INJECTION", "false").lower() == "true" and os.getenv("CAREERADAPT_ENV", "development").lower() != "production"


STATUS_MESSAGES = {
    "GRADED": "Bài đã được chấm.",
    "REVIEWED_APPROVED": "Bài đã được người duyệt xác nhận.",
    "NEEDS_REVIEW": "Bài cần người duyệt kiểm tra; hồ sơ kỹ năng chưa thay đổi.",
    "PENDING_RETRY": "Bài đã được lưu nhưng dịch vụ chấm chưa hoàn tất. Bạn có thể thử chấm lại.",
    "INCOMPLETE": "Bài nộp chưa có câu trả lời nên chưa được chấm. Hãy làm bài và nộp lại.",
    "INVALID": "Bài nộp thiếu đầu ra bắt buộc nên chưa được chấm. Hãy bổ sung và nộp lại.",
}


def _response(record: dict, duplicate: bool) -> SubmissionResponse:
    assessment = store.assessments.get(record["submission_id"]) or {}
    state = assessment.get("status") or record.get("status", "RECEIVED")
    return SubmissionResponse(
        submission_id=record["submission_id"], user_id=record["user_id"], task_id=record["task_id"], mode=record["mode"], status=state,
        submitted_at=record["submitted_at"], idempotency_key=record.get("idempotency_key"), is_duplicate=duplicate,
        final_score=assessment.get("final_score"), passed=assessment.get("passed"),
        message=("Yêu cầu trùng lặp; trả về bài đã xử lý. " if duplicate else "") + STATUS_MESSAGES.get(state, "Bài nộp đã được tiếp nhận."),
    )


def _answer_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content_hash(task_id: str, mode: str, answers: Optional[dict[str, str]], text: str) -> str:
    return _answer_hash(json.dumps({"task": task_id, "mode": mode, "answers": answers, "text": text}, ensure_ascii=False, sort_keys=True))


def _store_answers(submission_id: uuid.UUID, task_id: str, answers: Optional[dict[str, str]], text: str, submitted_at: str, known: Optional[set[str]] = None) -> None:
    blueprint = get_blueprint(task_id) or {"questions": []}
    entries = dict(answers) if answers is not None else {"FULL_TEXT": text}
    known = known if known is not None else {item["question_id"] for item in blueprint["questions"]}
    for question_id, value in entries.items():
        state = "BLANK" if not value.strip() else ("OK" if question_id in known or question_id == "FULL_TEXT" else "UNKNOWN_QUESTION")
        store.db.execute(
            "INSERT OR REPLACE INTO submission_answers(submission_id, question_id, answer_text, answer_hash, format_validation, submitted_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(submission_id), question_id, value, _answer_hash(value), state, submitted_at),
        )


def _load_answers(submission_id: uuid.UUID) -> tuple[Optional[dict[str, str]], str]:
    rows = store.db.query("SELECT question_id, answer_text FROM submission_answers WHERE submission_id = ?", (str(submission_id),))
    answers = {row["question_id"]: row["answer_text"] or "" for row in rows}
    if "FULL_TEXT" in answers:
        return None, answers["FULL_TEXT"]
    return answers, ""


@router.post("/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
def submit_task(body: SubmissionRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Nộp bài: lưu trước, chấm sau, có khóa chống trùng."""
    if not legacy_assessment_api_enabled() and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Bài đánh giá giờ chỉ làm một lần trong Quy trình Career Adapt.")
    now = utcnow()
    task_id = body.task_id.upper().strip()
    mode = body.mode.upper().strip()
    if mode not in {"ASSESSMENT", "PRACTICE"}:
        raise HTTPException(status_code=422, detail="Chế độ làm bài phải là ASSESSMENT hoặc PRACTICE.")
    text = body.submission_text or ""
    if body.answers is not None:
        unknown = set(body.answers) - {item["question_id"] for item in (get_blueprint(task_id) or {"questions": []})["questions"]}
        if unknown:
            raise HTTPException(status_code=422, detail="Bài nộp có câu hỏi không thuộc đề này.")
        if sum(len(value) for value in body.answers.values()) > 30000:
            raise HTTPException(status_code=413, detail="Bài nộp vượt giới hạn 30.000 ký tự.")
    content_hash = _content_hash(task_id, mode, body.answers, text)

    if body.idempotency_key:
        existing = store.db.one(
            "SELECT submission_id, content_hash FROM assessment_attempts WHERE user_id = ? AND idempotency_key = ?",
            (str(current_user.user_id), body.idempotency_key),
        )
        if existing:
            if existing["content_hash"] != content_hash:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Khóa chống trùng đã được dùng cho một bài nộp khác.")
            return _response(store.submissions[uuid.UUID(existing["submission_id"])], duplicate=True)

    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy bài thực hành có mã '{body.task_id}' trong ngân hàng đề.")
    if task.get("status", "PUBLISHED").upper() != "PUBLISHED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Đề bài chưa được xuất bản.")
    if mode == "ASSESSMENT" and task.get("is_reassessment_variant") and task.get("comparability_status", "NOT_REVIEWED") != "APPROVED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Biến thể này chưa được duyệt tính tương đương; hiện chỉ dùng ở chế độ luyện tập.")

    submission_id = uuid.uuid4()
    record = {
        "submission_id": submission_id, "user_id": current_user.user_id, "task_id": task_id, "mode": mode, "task_version": task.get("content_version", 1),
        "declared_tool": body.declared_tool.strip() or "Chưa khai báo", "used_assistance": body.used_assistance, "assistance_details": body.assistance_details.strip(),
        "status": "RECEIVED", "started_at": body.started_at.isoformat() if body.started_at else None, "submitted_at": now.isoformat(),
        "elapsed_seconds": (now - body.started_at).total_seconds() if body.started_at and body.started_at.tzinfo else None,
        "idempotency_key": body.idempotency_key, "content_hash": content_hash, "grade_attempts": 0, "task_snapshot": copy.deepcopy(task),
    }
    # The unique key on (user, idempotency key) settles a double click racing past the check above.
    try:
        with store.db.transaction():
            store.save_submission(record)
            _store_answers(submission_id, task_id, body.answers, text, now.isoformat())
    except sqlite3.IntegrityError:
        existing = store.db.one("SELECT submission_id FROM assessment_attempts WHERE user_id = ? AND idempotency_key = ?", (str(current_user.user_id), body.idempotency_key))
        store.submissions.pop(submission_id, None)
        return _response(store.submissions[uuid.UUID(existing["submission_id"])], duplicate=True)

    try:
        assessment = grade_submission_orchestrator(
            submission_id=submission_id, user_id=current_user.user_id, task_id=task_id, submission_text=text, mode=mode,
            fault_injection=body.fault_injection if fault_injection_allowed() else None, task_snapshot=copy.deepcopy(task),
            declared_tool=record["declared_tool"], used_assistance=body.used_assistance, assistance_details=record["assistance_details"], answers=body.answers,
        )
    except Exception:
        # The submission is safe in the database; it can be graded again.
        record["status"] = "PENDING_RETRY"
        store.save_submission(record)
        store.add_history_event(current_user.user_id, "GRADING_FAILED", f"Chấm bài {task_id} gặp lỗi; bài được giữ để chấm lại.")
        return _response(record, duplicate=False)

    _after_grading(current_user.user_id, assessment)
    return _response(record, duplicate=False)


def _after_grading(user_id: uuid.UUID, assessment: dict) -> None:
    store.record_progress_assessment(user_id, assessment)
    store.persist_user_runtime(user_id)
    score = assessment.get("final_score")
    event = "SUBMIT_ASSESSMENT" if assessment["mode"] == "ASSESSMENT" else "SUBMIT_PRACTICE"
    store.add_history_event(
        user_id, event, f"Nộp bài {assessment['task_id']} ({assessment['mode']}): {assessment['status']}" + (f", {score:g}/100" if score is not None else ""),
        version=str(assessment.get("rubric_version")), meta={"submission_id": str(assessment["submission_id"]), "task_id": assessment["task_id"], "status": assessment["status"]},
    )


@router.post("/submissions/{id}/grade")
def regrade_submission(id: uuid.UUID, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Chấm lại bài đang chờ (AI timeout/JSON sai). Bài đã có kết quả cuối được trả nguyên."""
    record = store.submissions.get(id)
    if not record or (record["user_id"] != current_user.user_id and current_user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài nộp.")
    # Atomic claim: only one request can move the submission into grading.
    claimed = store.db.execute(
        "UPDATE assessment_attempts SET status = 'PROCESSING' WHERE submission_id = ? AND status IN ('RECEIVED', 'PENDING_RETRY')", (str(id),)
    ).rowcount
    if not claimed:
        return {**_response(record, duplicate=True).model_dump(mode="json"), "regraded": False}
    if int(record.get("grade_attempts", 0)) >= MAX_GRADE_ATTEMPTS:
        store.db.execute("UPDATE assessment_attempts SET status = ? WHERE submission_id = ?", (record["status"], str(id)))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Đã hết số lần chấm lại. Bài được chuyển cho người duyệt.")
    answers, text = _load_answers(id)
    assessment = grade_submission_orchestrator(
        submission_id=id, user_id=record["user_id"], task_id=record["task_id"], submission_text=text, mode=record["mode"],
        task_snapshot=copy.deepcopy(record.get("task_snapshot")), declared_tool=record.get("declared_tool", "Chưa khai báo"),
        used_assistance=record.get("used_assistance", False), assistance_details=record.get("assistance_details", ""), answers=answers,
    )
    _after_grading(record["user_id"], assessment)
    return {**_response(record, duplicate=False).model_dump(mode="json"), "regraded": True}


def _public_task(task: dict) -> dict:
    """A task as a learner may see it: never the reference values."""
    blueprint = get_blueprint(task["task_id"])
    view = {key: value for key, value in task.items() if key not in {"reference_values"}}
    view["assessment_allowed"] = not task.get("is_reassessment_variant") or task.get("comparability_status") == "APPROVED"
    if blueprint:
        view["blueprint"] = public_blueprint(blueprint)
    dataset = task.get("dataset_preview")
    if dataset:
        try:
            columns, rows = load_dataset(dataset)
            view["dataset"] = {"name": dataset, "columns": columns, "rows": [[row.get(column, "") for column in columns] for row in rows]}
        except (ValueError, OSError):
            view["dataset"] = None
    return view


@router.get("/tasks")
def list_tasks(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Danh sách bài thực hành đã phát hành cùng lịch sử của người học."""
    tasks = []
    for task in store.tasks:
        if task.get("status", "PUBLISHED").upper() != "PUBLISHED":
            continue
        attempts = [item for item in store.assessments.values() if item.get("user_id") == current_user.user_id and item.get("task_id") == task["task_id"]]
        latest = max(attempts, key=lambda item: str(item.get("created_at", "")), default=None)
        view = _public_task(task)
        view["attempt_count"] = len(attempts)
        view["latest_result"] = None if not latest else {key: latest.get(key) for key in ("submission_id", "status", "final_score", "passed", "mode", "created_at")}
        tasks.append(view)
    return tasks


@router.get("/tasks/{task_id}")
def get_task(task_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    task = store.get_task(task_id.upper().strip())
    if not task or task.get("status", "PUBLISHED").upper() != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Không tìm thấy bài thực hành.")
    return _public_task(task)


@router.post("/submissions/extract-answer")
async def extract_answer_file(file: UploadFile = File(...), current_user: AuthenticatedUser = Depends(get_current_user)):
    """Đọc tệp trả lời dạng văn bản. Tệp hỏng hoặc sai định dạng bị từ chối, không chấm."""
    name = (file.filename or "").lower()
    if not name.endswith(ANSWER_FILE_TYPES):
        raise HTTPException(status_code=422, detail=f"Chỉ nhận tệp {', '.join(ANSWER_FILE_TYPES)}.")
    data = await file.read(MAX_ANSWER_FILE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="Tệp rỗng.")
    if len(data) > MAX_ANSWER_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Tệp vượt giới hạn 1 MB.")
    try:
        return {"text": decode_text_bytes(data), "file_name": file.filename}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


def _assessment_view(assessment: dict) -> dict:
    view = dict(assessment)
    identifier = str(assessment["submission_id"])
    view["ai_traces"] = store.db.query(
        "SELECT grade_attempt, provider, model, prompt_version, rubric_version, response_schema_version, validation_result, latency_ms, error, created_at "
        "FROM ai_feedback_traces WHERE submission_id = ? ORDER BY created_at", (identifier,)
    )
    rows = store.db.query("SELECT question_id, answer_text, format_validation FROM submission_answers WHERE submission_id = ?", (identifier,))
    view["answers"] = {row["question_id"]: row["answer_text"] for row in rows}
    view["can_retry"] = assessment.get("status") in RETRYABLE_STATUSES and int(assessment.get("grade_attempts", 0)) < MAX_GRADE_ATTEMPTS
    view["max_grade_attempts"] = MAX_GRADE_ATTEMPTS
    return view


@router.get("/assessments/{id}")
def get_assessment(id: uuid.UUID, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Xem kết quả đánh giá chi tiết theo ID bài nộp."""
    assessment = store.assessments.get(id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy kết quả đánh giá cho mã ID '{id}'.")
    if assessment["user_id"] != current_user.user_id and current_user.role != "admin":
        store.log_security_event(current_user.user_id, "ASSESSMENT_ACCESS_DENIED", str(id))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền xem kết quả đánh giá của người dùng khác.")
    return _assessment_view(assessment)


@router.get("/me/assessments")
def my_assessments(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Lịch sử chấm bài và các lần đánh giá của người học."""
    rows = store.db.query(
        # The exam lives in the plan page, and a reset exam must not reappear here.
        "SELECT submission_id, task_id, mode, status, final_score, passed, final_level, created_at FROM final_assessments WHERE user_id = ? AND task_id NOT LIKE 'EXAM-%' ORDER BY created_at DESC",
        (str(current_user.user_id),),
    )
    for row in rows:
        row["passed"] = None if row["passed"] is None else bool(row["passed"])
        assessment = store.assessments.get(uuid.UUID(row["submission_id"])) or {}
        row["task_title"] = assessment.get("task_title")
        row["rubric_version"] = assessment.get("rubric_version")
        row["task_version"] = assessment.get("task_version")
    return rows


__all__ = ["router", "submit_task", "get_assessment", "SubmissionRequest", "SubmissionResponse", "ACCEPTED_STATUSES"]
