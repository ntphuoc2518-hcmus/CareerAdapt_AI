"""F03: Submissions & Assessment Queue Endpoints (TV3 / F03).

Integrates safe file storage (TV5) and idempotency checks.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from auth import AuthenticatedUser, get_current_user, check_resource_ownership
from schemas.models import SubmissionCreateRequest, SubmissionResponse, SubmissionStatusResponse
from services.store import store
from services.assessment_orchestrator import orchestrator
from file_storage_service import validate_and_save_file

router = APIRouter(prefix="/submissions", tags=["F03 - Submissions"])


@router.post("", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
def submit_text_solution(
    body: SubmissionCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Submit a text solution for evaluation with idempotency protection."""
    uid = current_user.user_id
    now = datetime.now(timezone.utc)

    # 1. Idempotency Check
    if body.idempotency_key and body.idempotency_key in store.idempotency_keys:
        existing_sub_id = store.idempotency_keys[body.idempotency_key]
        sub = store.submissions.get(existing_sub_id)
        if sub and sub["user_id"] == uid:
            return SubmissionResponse(
                submission_id=sub["submission_id"],
                user_id=sub["user_id"],
                task_version_id=sub["task_version_id"],
                mode=sub["mode"],
                processing_status=sub["processing_status"],
                submitted_at=sub["submitted_at"],
                file_metadata=sub.get("file_metadata"),
                message="Yêu cầu đã được tiếp nhận trước đó (Idempotency matched)."
            )

    # 2. Validate Task
    task_match = None
    for task in store.tasks.values():
        if task.task_id == body.task_version_id or task.task_version_id == body.task_version_id:
            task_match = task
            break
    if not task_match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mã bài thử '{body.task_version_id}' không tồn tại."
        )

    if not body.submission_text or not body.submission_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nội dung bài nộp không được để trống."
        )

    # 3. Create Submission record
    sub_id = uuid.uuid4()
    submission_record = {
        "submission_id": sub_id,
        "user_id": uid,
        "task_version_id": task_match.task_id,
        "mode": body.mode,
        "submission_text": body.submission_text,
        "processing_status": "PROCESSING",
        "retry_count": 0,
        "submitted_at": now,
        "updated_at": now,
        "file_metadata": None
    }
    store.submissions[sub_id] = submission_record
    if body.idempotency_key:
        store.idempotency_keys[body.idempotency_key] = sub_id

    # 4. Trigger Assessment Orchestrator
    assessment = orchestrator.evaluate_submission(
        submission_id=sub_id,
        task_id=task_match.task_id,
        submission_text=body.submission_text
    )
    store.assessments[sub_id] = assessment.model_dump()
    submission_record["processing_status"] = "COMPLETED"
    submission_record["assessment_id"] = assessment.assessment_id

    return SubmissionResponse(
        submission_id=sub_id,
        user_id=uid,
        task_version_id=task_match.task_id,
        mode=body.mode,
        processing_status=submission_record["processing_status"],
        submitted_at=now,
        file_metadata=None,
        message="Nộp bài thành công và đã được chấm điểm."
    )


@router.post("/upload", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_file_solution(
    task_version_id: str = Form(...),
    mode: str = Form("ASSESSMENT"),
    idempotency_key: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Upload submission file (TXT, CSV, SQL) with security validation (TV5 integration)."""
    uid = current_user.user_id
    now = datetime.now(timezone.utc)

    # 1. Idempotency Check
    if idempotency_key and idempotency_key in store.idempotency_keys:
        existing_sub_id = store.idempotency_keys[idempotency_key]
        sub = store.submissions.get(existing_sub_id)
        if sub and sub["user_id"] == uid:
            return SubmissionResponse(
                submission_id=sub["submission_id"],
                user_id=sub["user_id"],
                task_version_id=sub["task_version_id"],
                mode=sub["mode"],
                processing_status=sub["processing_status"],
                submitted_at=sub["submitted_at"],
                file_metadata=sub.get("file_metadata"),
                message="Yêu cầu đã được tiếp nhận trước đó (Idempotency matched)."
            )

    content_bytes = await file.read()
    sub_id = uuid.uuid4()

    # 2. Validate and safe save file using TV5's file_storage_service
    ok, stored_path, file_type, size_bytes, sha256_hash, err_msg = validate_and_save_file(
        original_filename=file.filename or "submission.txt",
        file_content=content_bytes,
        submission_id=str(sub_id)
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Kiểm tra file thất bại: {err_msg}"
        )

    file_meta = {
        "original_filename": file.filename,
        "stored_path": stored_path,
        "file_type": file_type,
        "size_bytes": size_bytes,
        "sha256": sha256_hash
    }

    text_content = content_bytes.decode("utf-8", errors="replace")

    # 3. Create record
    submission_record = {
        "submission_id": sub_id,
        "user_id": uid,
        "task_version_id": task_version_id,
        "mode": mode,
        "submission_text": text_content,
        "processing_status": "PROCESSING",
        "retry_count": 0,
        "submitted_at": now,
        "updated_at": now,
        "file_metadata": file_meta
    }
    store.submissions[sub_id] = submission_record
    if idempotency_key:
        store.idempotency_keys[idempotency_key] = sub_id

    # 4. Trigger Assessment Orchestrator
    assessment = orchestrator.evaluate_submission(
        submission_id=sub_id,
        task_id=task_version_id,
        submission_text=text_content
    )
    store.assessments[sub_id] = assessment.model_dump()
    submission_record["processing_status"] = "COMPLETED"
    submission_record["assessment_id"] = assessment.assessment_id

    return SubmissionResponse(
        submission_id=sub_id,
        user_id=uid,
        task_version_id=task_version_id,
        mode=mode,
        processing_status="COMPLETED",
        submitted_at=now,
        file_metadata=file_meta,
        message="Nộp tệp giải pháp thành công và đã được chấm điểm."
    )


@router.get("/{submission_id}", response_model=SubmissionStatusResponse)
def get_submission_status(
    submission_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Check status of a submission. Strictly checks ownership (TV5 rule)."""
    sub = store.submissions.get(submission_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bài nộp."
        )
    check_resource_ownership(sub["user_id"], current_user.user_id)

    return SubmissionStatusResponse(
        submission_id=sub["submission_id"],
        processing_status=sub["processing_status"],
        submitted_at=sub["submitted_at"],
        retry_count=sub.get("retry_count", 0),
        assessment_id=sub.get("assessment_id")
    )


@router.get("", response_model=list[SubmissionResponse])
def list_my_submissions(current_user: AuthenticatedUser = Depends(get_current_user)):
    """List all submissions owned by the authenticated user."""
    uid = current_user.user_id
    results = [
        SubmissionResponse(
            submission_id=s["submission_id"],
            user_id=s["user_id"],
            task_version_id=s["task_version_id"],
            mode=s["mode"],
            processing_status=s["processing_status"],
            submitted_at=s["submitted_at"],
            file_metadata=s.get("file_metadata"),
            message="OK"
        )
        for s in store.submissions.values()
        if s["user_id"] == uid
    ]
    return sorted(results, key=lambda x: x.submitted_at, reverse=True)
