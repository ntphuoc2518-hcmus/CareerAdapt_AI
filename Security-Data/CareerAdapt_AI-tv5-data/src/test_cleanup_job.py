"""Integration test for expired-file cleanup; ONLY careeradapt_demo."""
import os
import uuid

os.environ["DB_NAME"] = "careeradapt_demo"

import cleanup_job
from user_data_lifecycle import get_db_connection, delete_user_account_safe
from file_storage_service import validate_and_save_file, delete_physical_file, STORAGE_ROOT

TASK_VERSION_ID = "20000000-0000-0000-0000-000000000001"


def _one(cur):
    row = cur.fetchone()
    assert row is not None, "Không tìm thấy dòng mong đợi"
    return row


def _abs_path(path):
    return os.path.join(STORAGE_ROOT, os.path.basename(path))


def run_tests():
    user_id = None
    paths = []
    original_delete = cleanup_job.delete_physical_file
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        database_name = cur.fetchone()[0]
        assert database_name == "careeradapt_demo", f"DỪNG: database hiện tại là {database_name!r}"

        email = f"cleanup_{uuid.uuid4().hex[:10]}@test.local"
        cur.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, 'learner') RETURNING user_id",
            (email, "DISABLED-NO-LOGIN"),
        )
        user_id = str(_one(cur)[0])
        cur.execute("INSERT INTO profiles (user_id, display_name) VALUES (%s, %s)", (user_id, "Cleanup test"))
        cur.execute(
            """INSERT INTO submissions (user_id, task_version_id, mode, submitted_text, idempotency_key)
               VALUES (%s, %s, 'PRACTICE', %s, %s) RETURNING submission_id""",
            (user_id, TASK_VERSION_ID, "bai lam gia cho cleanup test", uuid.uuid4().hex),
        )
        submission_id = str(_one(cur)[0])

        created = []
        for idx, content in enumerate((b"SELECT 1;", b"SELECT 2;"), start=1):
            ok, path, file_type, size, sha256, error = validate_and_save_file(f"expired{idx}.sql", content, submission_id)
            assert ok and path, error
            paths.append(path)
            created.append((path, file_type, size, sha256, f"expired{idx}.sql"))

        file_ids = []
        for path, file_type, size, sha256, original_name in created:
            cur.execute(
                """INSERT INTO submission_files
                   (submission_id, stored_path, original_name, file_type, size_bytes, sha256, uploaded_at, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, now() - interval '91 days', now() - interval '1 day')
                   RETURNING file_id""",
                (submission_id, path, original_name, file_type, size, sha256),
            )
            file_ids.append(str(_one(cur)[0]))
        conn.commit()
        cur.close()
        conn.close()
        cur = conn = None
        print("OK 1: Tạo user giả, bài nộp và 2 file đã hết hạn trong careeradapt_demo.")

        # Simulate a file-system failure for the second file. It must not be marked deleted.
        failed_path = paths[1]
        cleanup_job.delete_physical_file = lambda path: False if path == failed_path else original_delete(path)
        result = cleanup_job.run_cleanup()
        assert result["candidates"] >= 2, result
        assert result["files_deleted"] >= 1, result
        assert failed_path in result["files_failed"], result
        assert not os.path.exists(_abs_path(paths[0])), "File đầu tiên vẫn còn trên ổ đĩa"
        assert os.path.exists(_abs_path(failed_path)), "File mô phỏng lỗi phải còn trên ổ đĩa"
        print("OK 2: File xóa được đã bị xóa vật lý; file lỗi không bị đánh dấu/xóa nhầm.")

        cleanup_job.delete_physical_file = original_delete
        result2 = cleanup_job.run_cleanup(only_file_ids=set(file_ids))
        assert failed_path not in result2["files_failed"], result2
        assert not os.path.exists(_abs_path(failed_path)), "File hết hạn chưa bị xóa sau lần thử lại"
        print("OK 3: Lần chạy tiếp theo xử lý được file lỗi trước đó.")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT deleted_at FROM submission_files WHERE file_id = %s", (file_ids[0],))
        assert _one(cur)[0] is not None, "deleted_at của file đầu tiên chưa được đặt"
        cur.execute("SELECT deleted_at FROM submission_files WHERE file_id = %s", (file_ids[1],))
        assert _one(cur)[0] is not None, "deleted_at của file thứ hai chưa được đặt sau lần thử lại"
        cur.close()
        conn.close()
        conn = cur = None
        print("OK 4: deleted_at chỉ được đặt sau khi file đã vắng mặt trên ổ đĩa.")
        print("TẤT CẢ 4 TEST CLEANUP ĐỀU ĐẠT.")
    finally:
        cleanup_job.delete_physical_file = original_delete
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
        if user_id is not None:
            try:
                delete_user_account_safe(user_id)
            except Exception as exc:
                print(f"CẢNH BÁO: chưa dọn được user test {user_id}: {exc}")
        for path in paths:
            delete_physical_file(path)


if __name__ == "__main__":
    run_tests()
