# BÀN GIAO MẢNG DATA & SECURITY (TV5)

## 1. THREAT MODEL & SECURITY CHECKLIST (T5.5)
* **Prompt Injection:** Áp dụng `redact_pii()` loại bỏ PII và `normalize_nfc()` trước khi nạp payload.
* **Evidence Fabrication:** Hàm `verify_evidence_quote()` đối chiếu trích dẫn nguyên văn với bài nộp.
* **IDOR/BOLA:** Mọi endpoint bắt buộc kiểm tra `verify_ownership(resource_owner_id, user_id_from_token)`.
* **Path Traversal & Malicious File (T5.3):** Đổi tên file thành UUID, chặn file thực thi, giới hạn size 5MB.

## 2. DATA DICTIONARY & SCHEMA CONSTRAINTS (T5.1)
* **Immutable Content:** `career_versions`, `task_versions` bị khóa bằng trigger khi `status='published'`.
* **Idempotency:** Bảng `submissions` có `UNIQUE(user_id, idempotency_key)`.
* **Roadmap DAG:** Trigger `trg_activity_prerequisites_guard` tự động chặn chu trình đệ quy vòng lặp.

## 3. RETENTION & LIFECYCLE (T5.4)
* **Right to Erasure:** `DELETE FROM users` kích hoạt `ON DELETE CASCADE` xóa toàn bộ dữ liệu cá nhân.
* **90-Day Retention:** Script `cleanup_job.py` gọi hàm SQL dọn dẹp file vật lý và soft-delete trong database.