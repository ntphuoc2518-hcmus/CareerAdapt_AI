"""Owner-scoped data access helpers for CareerAdapt.

Call these functions only with user_id from a verified server-side identity/token,
never directly from a request body or an untrusted X-User-Id header.
The caller owns the transaction and must commit/rollback the supplied connection.
"""
from __future__ import annotations
from typing import Any, Optional
from uuid import UUID
import json

ALLOWED_PROCESSING_STATUSES = {
    "SUBMITTED", "PROCESSING", "PENDING_RETRY", "NEEDS_REVIEW", "COMPLETED"
}


def _as_uuid(value: str) -> UUID:
    return UUID(str(value))


def _audit_denied(conn: Any, authenticated_user_id: str, target_type: str, target_id: str) -> None:
    """Log denial without storing submission content. Does not commit the transaction."""
    try:
        actor = str(_as_uuid(authenticated_user_id))
    except (ValueError, TypeError, AttributeError):
        actor = None
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO audit_logs
               (actor_user_id, action, target_type, target_id, outcome, details)
               VALUES (%s, %s, %s, %s, 'DENIED', %s::jsonb)""",
            (actor, "CROSS_USER_ACCESS", target_type, str(target_id),
             json.dumps({"reason": "not_found_or_not_owned"})),
        )
    finally:
        cur.close()


def get_owned_submission(conn: Any, authenticated_user_id: str, submission_id: str) -> Optional[dict]:
    """Return a submission only when it belongs to the authenticated user.

    A missing ID and another user's ID both return None. Denials are audited.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT submission_id, user_id, task_version_id, mode,
                      processing_status, retry_count, submitted_at, updated_at
               FROM submissions WHERE submission_id = %s AND user_id = %s""",
            (submission_id, authenticated_user_id),
        )
        row = cur.fetchone()
        if row is None:
            _audit_denied(conn, authenticated_user_id, "submission", str(submission_id))
            return None
        columns = [d[0] for d in cur.description]
        return dict(zip(columns, row))
    finally:
        cur.close()


def list_owned_submissions(conn: Any, authenticated_user_id: str) -> list[dict]:
    """List only the authenticated user's submissions; caller controls transaction."""
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT submission_id, task_version_id, mode, processing_status,
                      retry_count, submitted_at, updated_at
               FROM submissions WHERE user_id = %s ORDER BY submitted_at DESC""",
            (authenticated_user_id,),
        )
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        cur.close()


def update_owned_submission_status(
    conn: Any, authenticated_user_id: str, submission_id: str, new_status: str
) -> bool:
    """Update status only under an owner predicate; database trigger validates transitions."""
    if new_status not in ALLOWED_PROCESSING_STATUSES:
        raise ValueError("Invalid processing status")
    cur = conn.cursor()
    try:
        cur.execute(
            """UPDATE submissions SET processing_status = %s, updated_at = now()
               WHERE submission_id = %s AND user_id = %s""",
            (new_status, submission_id, authenticated_user_id),
        )
        if cur.rowcount == 1:
            return True
        _audit_denied(conn, authenticated_user_id, "submission", str(submission_id))
        return False
    finally:
        cur.close()


def read_owned_submission_file(conn: Any, authenticated_user_id: str, file_id: str) -> Optional[str]:
    """Read UTF-8 file text only after checking the file's submission owner."""
    from file_storage_service import read_stored_file
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT f.stored_path
               FROM submission_files f
               JOIN submissions s ON s.submission_id = f.submission_id
               WHERE f.file_id = %s AND s.user_id = %s AND f.deleted_at IS NULL""",
            (file_id, authenticated_user_id),
        )
        row = cur.fetchone()
        if row is None:
            _audit_denied(conn, authenticated_user_id, "submission_file", str(file_id))
            return None
        path = row[0]
    finally:
        cur.close()
    # read_stored_file enforces storage-root containment and UTF-8 decoding.
    return read_stored_file(path).decode("utf-8")
