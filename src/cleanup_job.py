"""CareerAdapt AI - Data Retention Cleanup Job (T5.4)."""
from user_data_lifecycle import get_db_connection
from file_storage_service import delete_physical_file


def run_cleanup(only_file_ids: set[str] | None = None) -> dict:
    """Delete expired files from disk, then mark only successful deletions.

    A missing physical file counts as success because delete_physical_file returns
    True when the file is already absent. Failed file deletions remain unmarked
    and are eligible for retry on the next run.
    """
    conn = None
    cur = None
    files_deleted = 0
    files_failed = []
    candidates = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT purged_file_id, purged_path FROM purge_expired_submission_files();")
        expired_files = cur.fetchall()
        candidates = len(expired_files)

        for file_id, path in expired_files:
            if not delete_physical_file(path):
                files_failed.append(path)
                continue

            cur.execute(
                """UPDATE submission_files
                   SET deleted_at = now()
                   WHERE file_id = %s
                     AND deleted_at IS NULL
                     AND expires_at <= now()""",
                (file_id,),
            )
            if cur.rowcount != 1:
                # The file is already gone; rollback the DB transaction so a retry
                # can reconcile the missing file and update deleted_at safely.
                raise RuntimeError(f"Không thể đánh dấu deleted_at cho file_id={file_id}")
            files_deleted += 1

        conn.commit()
        return {
            "candidates": candidates,
            "files_deleted": files_deleted,
            "files_failed": files_failed,
        }
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    try:
        result = run_cleanup()
        print(f"Ứng viên hết hạn: {result['candidates']}")
        print(f"Đã xóa file vật lý và đánh dấu deleted_at: {result['files_deleted']}")
        print(f"File chưa xóa được (sẽ thử lại lần sau): {len(result['files_failed'])}")
        if result["files_failed"]:
            for path in result["files_failed"]:
                print(f"  - {path}")
    except Exception as exc:
        print(f"Cleanup Error: {exc}")
        raise
