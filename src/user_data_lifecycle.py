"""CareerAdapt AI - User Data Lifecycle (T5.4).
View, export, and delete a user's personal data.
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from file_storage_service import delete_physical_file

load_dotenv()


def get_db_connection():
    return psycopg2.connect(
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
    )


def export_user_data(user_id: str) -> dict:
    """Export the user's account, submissions, assessment evidence and learning data.

    Every query is scoped by user_id directly or through the user's roadmap/submission.
    Returned data is for the authenticated user's own data only.
    """
    user_data = {
        "account": None, "profile": None, "submissions": [], "assessments": [],
        "criterion_scores": [], "roadmaps": [], "learning_activities": [],
        "progress_records": [], "checklist_items": [], "reminders": [],
    }
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """SELECT user_id, email, role, is_active, created_at, updated_at
               FROM users WHERE user_id = %s""", (user_id,))
        user_data["account"] = cur.fetchone()
        if user_data["account"] is None:
            return user_data

        cur.execute(
            """SELECT user_id, display_name, major, career_goal,
                      weekly_available_hours, target_deadline,
                      self_reported_skills, reminder_preferences, created_at, updated_at
               FROM profiles WHERE user_id = %s""", (user_id,))
        user_data["profile"] = cur.fetchone()

        cur.execute(
            """SELECT s.submission_id, s.task_version_id, s.mode, s.submitted_text,
                      s.declared_tools, s.idempotency_key, s.processing_status,
                      s.retry_count, s.submitted_at, s.updated_at,
                      COALESCE((SELECT jsonb_agg(jsonb_build_object(
                          'file_id', f.file_id, 'stored_path', f.stored_path,
                          'original_name', f.original_name, 'file_type', f.file_type,
                          'mime_type', f.mime_type, 'size_bytes', f.size_bytes,
                          'sha256', f.sha256, 'uploaded_at', f.uploaded_at,
                          'expires_at', f.expires_at, 'deleted_at', f.deleted_at))
                          FROM submission_files f WHERE f.submission_id = s.submission_id), '[]'::jsonb) AS files
               FROM submissions s WHERE s.user_id = %s ORDER BY s.submitted_at""", (user_id,))
        user_data["submissions"] = cur.fetchall()

        cur.execute(
            """SELECT a.assessment_id, a.submission_id, a.deterministic_results,
                      a.overall_status, a.flags, a.evaluated_at
               FROM assessments a JOIN submissions s ON s.submission_id = a.submission_id
               WHERE s.user_id = %s ORDER BY a.evaluated_at""", (user_id,))
        user_data["assessments"] = cur.fetchall()

        cur.execute(
            """SELECT cs.score_id, cs.assessment_id, cs.criterion_id, cs.skill_code,
                      cs.score_level, cs.evidence_quote, cs.rationale, cs.is_verified, cs.flags
               FROM criterion_scores cs JOIN assessments a ON a.assessment_id = cs.assessment_id
               JOIN submissions s ON s.submission_id = a.submission_id
               WHERE s.user_id = %s ORDER BY cs.assessment_id, cs.criterion_id""", (user_id,))
        user_data["criterion_scores"] = cur.fetchall()

        cur.execute(
            """SELECT roadmap_version_id, career_version_id, based_on_assessment_ids,
                      weekly_hours_budget, total_weeks, status, unscheduled_activities, created_at
               FROM roadmap_versions WHERE user_id = %s ORDER BY created_at""", (user_id,))
        user_data["roadmaps"] = cur.fetchall()

        cur.execute(
            """SELECT la.learning_activity_id, la.roadmap_version_id, la.catalog_activity_id,
                      la.title, la.skill_code, la.week_number, la.estimated_hours,
                      la.required_output, la.due_date, la.current_status, la.created_at, la.updated_at
               FROM learning_activities la JOIN roadmap_versions rv
                 ON rv.roadmap_version_id = la.roadmap_version_id
               WHERE rv.user_id = %s ORDER BY la.week_number, la.created_at""", (user_id,))
        user_data["learning_activities"] = cur.fetchall()

        cur.execute(
            """SELECT pr.progress_id, pr.learning_activity_id, pr.old_status, pr.new_status,
                      pr.actual_duration_minutes, pr.output_note, pr.created_at
               FROM progress_records pr JOIN learning_activities la
                 ON la.learning_activity_id = pr.learning_activity_id
               JOIN roadmap_versions rv ON rv.roadmap_version_id = la.roadmap_version_id
               WHERE rv.user_id = %s ORDER BY pr.created_at""", (user_id,))
        user_data["progress_records"] = cur.fetchall()

        cur.execute(
            """SELECT checklist_item_id, user_id, learning_activity_id, content, due_date,
                      sort_order, source, is_done, done_at, created_at
               FROM checklist_items WHERE user_id = %s ORDER BY due_date NULLS LAST, sort_order""", (user_id,))
        user_data["checklist_items"] = cur.fetchall()

        cur.execute(
            """SELECT reminder_id, user_id, learning_activity_id, reminder_type,
                      message, deduplication_key, is_viewed, created_at
               FROM reminders WHERE user_id = %s ORDER BY created_at""", (user_id,))
        user_data["reminders"] = cur.fetchall()
        return user_data
    except Exception as e:
        raise RuntimeError(f"Export Error: {e}") from e
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def delete_user_account_safe(user_id: str) -> dict:
    """Delete account data in the DB, then delete its physical files.

    Database deletion is committed before any physical file is removed. If the
    DB transaction fails, rollback occurs and no files are deleted.

    Returns {"account_deleted": bool, "files_deleted": int, "files_failed": list}.
    """
    conn = None
    cur = None
    stored_paths = []

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT f.stored_path
            FROM submission_files f
            JOIN submissions s ON s.submission_id = f.submission_id
            WHERE s.user_id = %s
            """,
            (user_id,),
        )
        stored_paths = [row[0] for row in cur.fetchall()]

        cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        account_deleted = cur.rowcount > 0
        conn.commit()
    except Exception as e:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f"Delete Error: {e}") from e
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()

    files_deleted = 0
    files_failed = []
    for path in stored_paths:
        if delete_physical_file(path):
            files_deleted += 1
        else:
            files_failed.append(path)

    return {
        "account_deleted": account_deleted,
        "files_deleted": files_deleted,
        "files_failed": files_failed,
    }


if __name__ == "__main__":
    print("--- KIỂM TRA LUỒNG EXPORT (Chỉ đọc) ---")
    test_uid = "00000000-0000-0000-0000-000000000001"
    try:
        data = export_user_data(test_uid)
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        print("OK: Luồng Export chạy thành công.")
    except Exception as e:
        print(f"FAILED: {e}")
