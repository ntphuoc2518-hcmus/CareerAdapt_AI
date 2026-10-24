# CareerAdapt AI --- Tài liệu Kiến trúc & API Contract (TV3 Backend / Tech Lead)

**Người phụ trách:** Hà Xuân Tỉnh (TV3 --- Backend Developer + Tech Lead kỹ thuật)  
**Công nghệ:** FastAPI + Python 3.12 + Pydantic v2 + PostgreSQL / Thread-safe Memory Store  
**Nhánh Git:** `tv3-backend`  

---

## 1. Tổng quan kiến trúc & Quy chuẩn kỹ thuật

### 1.1. Module Boundaries
Cấu trúc mã nguồn backend được phân tách rõ ràng theo ranh giới mô-đun:
- `src/main.py`: Khởi chạy ứng dụng FastAPI, cấu hình CORS, xử lý ngoại lệ chuẩn hóa và gắn kết các router.
- `src/auth.py`: Quản lý xác thực danh tính server-side (`get_current_user`), kiểm tra quyền Admin (`require_admin_user`) và quyền sở hữu tài nguyên (`check_resource_ownership`).
- `src/schemas/models.py`: Khai báo Pydantic schemas cho toàn bộ các chức năng từ F01 đến F10.
- `src/domain/evaluation.py`: Hàm thuần tính toán Gap, Coverage, Readiness, Attainment và Priority.
- `src/domain/scheduler.py`: Bộ lập lịch Roadmap theo đồ thị có hướng không chu trình (DAG), phát hiện chu trình, kiểm soát quỹ thời gian tuần và lưu vết hoạt động chưa xếp được.
- `src/services/store.py`: Kho dữ liệu trung tâm hỗ trợ cả chạy offline (memory seeded) lẫn tích hợp PostgreSQL.
- `src/services/assessment_orchestrator.py`: Điều phối luồng chấm bài, kiểm tra bằng chứng (`verify_evidence_quote`), che giấu PII (`redact_pii`) và phân nhánh trạng thái `ACCEPTED`, `NEEDS_REVIEW`, `RETRYABLE_ERROR`.
- `src/api/v1/`: Chứa các endpoint nghiệp vụ theo từng chức năng F01–F10.

### 1.2. Chuẩn mã phản hồi lỗi (Error Format)
Mọi phản hồi lỗi (4xx, 5xx) tuân thủ cấu trúc thống nhất:
```json
{
  "error": {
    "code": "HTTP_401",
    "message": "Token xác thực không hợp lệ hoặc đã hết hạn.",
    "details": null
  }
}
```

---

## 2. Chi tiết API Contract theo chức năng (F01 – F10)

### Xác thực & Danh tính (Authentication)
* **`POST /api/v1/auth/login`**
  * *Body:* `{"email_or_token": "token_student_1"}` hoặc `{"email_or_token": "admin@test.local"}`
  * *Response 200:* Trả về `access_token`, `token_type: "bearer"`, cùng thông tin danh tính `user_id`, `email`, `role`, `full_name`.
* **`GET /api/v1/auth/me`**: Lấy thông tin tài khoản hiện tại từ token.
* **`GET /api/v1/auth/demo-tokens`**: Danh sách demo tokens phục vụ kiểm thử nhanh.

### F01: Hồ sơ & Mục tiêu nghề nghiệp
* **`GET /api/v1/profiles/me`**
  * *Header:* `Authorization: Bearer <token>`
  * *Mục đích:* Lấy hồ sơ người dùng hiện tại (tự khởi tạo nếu chưa có).
  * *Response 200:* Trả về thông tin mục tiêu nghề nghiệp, quỹ giờ học mỗi tuần, thời hạn mục tiêu.
* **`PUT /api/v1/profiles/me`**
  * *Body:*
    ```json
    {
      "target_career_id": "DATA_ANALYST",
      "weekly_hours_budget": 12.0,
      "target_timeline_weeks": 8,
      "self_reported_skills": [
        {"skill_id": "SQL", "claimed_level": 2},
        {"skill_id": "PYTHON", "claimed_level": 1}
      ]
    }
    ```
  * *Nguyên tắc:* Các kỹ năng tự khai được gắn cờ `is_self_reported: true` và tuyệt đối không tính làm bằng chứng năng lực.

---

### F02: Khung kỹ năng & Danh mục bài thử
* **`GET /api/v1/catalog`**
  * *Mục đích:* Lấy danh mục khung kỹ năng chính thức và các bài thử DA01–DA03.
  * *Response 200:* Trả về 5 kỹ năng (tổng trọng số = 1.0; SQL và DATA_QUALITY là core) và 3 bài thử chuẩn.
* **`GET /api/v1/catalog/skills`**: Lấy danh sách kỹ năng, trọng số và nguồn tham khảo (O*NET / ESCO).
* **`GET /api/v1/catalog/tasks`**: Lấy danh sách bài thử với thời lượng và yêu cầu đầu ra.

---

### F03: Nộp bài thử & Upload tệp an toàn
* **`POST /api/v1/submissions`**
  * *Mục đích:* Nộp bài giải pháp dạng văn bản trực tiếp.
  * *Body:*
    ```json
    {
      "task_version_id": "DA01",
      "submission_text": "SELECT region, sum(revenue) FROM sales WHERE status = 'completed' GROUP BY region;",
      "mode": "ASSESSMENT",
      "idempotency_key": "unique_client_req_001"
    }
    ```
  * *Chống nộp trùng:* Nếu gửi lại cùng `idempotency_key`, server trả về kết quả bài nộp đã xử lý mà không tạo bản ghi mới.
* **`POST /api/v1/submissions/upload`**
  * *Content-Type:* `multipart/form-data`
  * *Fields:* `task_version_id`, `mode`, `idempotency_key` (tùy chọn), `file` (TXT, CSV, SQL).
  * *Bảo mật (TV5):* Giới hạn kích thước $\le 5\text{MB}$, bắt buộc UTF-8, chặn byte NUL, chặn path traversal.
* **`GET /api/v1/submissions/{submission_id}`**
  * *Kiểm tra quyền:* Kiểm tra server-side `user_id`. Nếu User A cố đọc bài nộp của User B $\rightarrow$ trả về **403 Forbidden**.
* **`GET /api/v1/submissions`**: Liệt kê toàn bộ các bài nộp của user hiện tại theo thứ tự thời gian.

---

### F04: Chấm & Phản hồi có bằng chứng
* **`GET /api/v1/assessments/by-submission/{submission_id}`**
  * *Response 200:*
    ```json
    {
      "assessment_id": "3fa85f64-...",
      "submission_id": "3fa85f64-...",
      "overall_level": 2,
      "status": "ACCEPTED",
      "scores": [
        {
          "criterion_id": "CRIT_SQL_SYNTAX",
          "criterion_name": "Cú pháp và logic truy vấn SQL",
          "level": 2,
          "evidence_quote": "SELECT",
          "rationale": "Thí sinh sử dụng đúng các mệnh đề SQL cơ bản.",
          "has_valid_evidence": true
        }
      ],
      "assessed_at": "2026-10-24T23:00:00Z",
      "model_version": "mock-llm-rubric-v3.0"
    }
    ```
  * *Bảo đảm bằng chứng:* Đoạn `evidence_quote` phải được xác thực tồn tại trong bài nộp thông qua `verify_evidence_quote`. Nếu không khớp, đánh dấu `has_valid_evidence: false` và chuyển trạng thái `NEEDS_REVIEW`.

---

### F05: Gap / Coverage / Readiness
* **`GET /api/v1/evaluation/summary`**
  * *Công thức chuẩn xác:*
    $$\text{gap} = \max(0, \text{target} - \text{level})$$
    $$\text{attainment} = \min(\text{level} / \text{target}, 1.0)$$
    $$\text{priority} = \text{weight} \times \frac{\text{gap} / \text{target}}{\text{estimated\_hours}}$$
    $$\text{coverage} = \sum \text{weight của các kỹ năng đã được đánh giá có bằng chứng}$$
  * *Cổng phát hành Readiness (Readiness Gate):*
    * **Chỉ phát hành điểm khi:** $\text{coverage} \ge 0.80$ **VÀ** toàn bộ kỹ năng cốt lõi (SQL, DATA_QUALITY) đã được đánh giá hợp lệ.
    * Khi chưa đủ điều kiện: `readiness_score = null`, `readiness_level` giải thích rõ nguyên nhân và liệt kê danh sách kỹ năng cốt lõi còn thiếu.

---

### F06: Lập lịch Roadmap (DAG)
* **`POST /api/v1/roadmap/generate`**
  * *Mục đích:* Tự động lập lịch học tập theo tuần dựa trên cây phụ thuộc tiền quyết và quỹ giờ/tuần của người học.
  * *Body (tùy chọn):* `{"weekly_hours_budget": 12.0, "target_timeline_weeks": 8}` cho phép ghi đè linh hoạt và đồng bộ vào profile.
  * *Tính năng:*
    * Phát hiện chu trình (cycle detection): báo lỗi rõ ràng nếu có vòng lặp phụ thuộc.
    * Hoạt động không thể xếp (vượt giờ hoặc thiếu tiền quyết) được đưa vào danh sách `unscheduled` kèm lý do chi tiết, không âm thầm loại bỏ.
    * Tạo phiên bản roadmap mới độc lập, bảo toàn lịch sử.
* **`GET /api/v1/roadmap/latest`**: Lấy lộ trình mới nhất của người dùng, tự động đồng bộ trạng thái thực tế (`COMPLETED`, `IN_PROGRESS`) từ F07.
* **`GET /api/v1/roadmap/versions`**: Lấy danh sách các phiên bản lộ trình đã từng sinh.
* **`GET /api/v1/roadmap/{roadmap_version_id}`**: Lấy chi tiết phiên bản lộ trình cụ thể theo ID.

---

### F07: Theo dõi tiến độ
* **`PUT /api/v1/progress`** hoặc **`PATCH /api/v1/progress`**
  * *Body:* `{"activity_id": "ACT_SQL_01", "new_status": "COMPLETED", "hours_spent": 4.0}`
  * *Validation:* Kiểm tra trạng thái hợp lệ, mã hoạt động tồn tại và `hours_spent >= 0`.
  * *Nguyên tắc:* Hoàn thành hoạt động ghi nhận tỷ lệ % hoàn thành lộ trình nhưng **không** tự động nâng mức năng lực khi chưa có đánh giá lại.
* **`GET /api/v1/progress`**: Thống kê số lượng hoạt động đã hoàn thành, tổng số và tỷ lệ phần trăm.
* **`GET /api/v1/progress/history`**: Lấy toàn bộ nhật ký sự kiện chuyển đổi trạng thái (audit log) có timestamp phục vụ kiểm toán và báo cáo.


---

### F08: Đánh giá lại & So sánh tiến bộ
* **`GET /api/v1/reassessment/compare?previous_submission_id={id1}&current_submission_id={id2}`**
  * *Mục đích:* Đối chiếu kết quả 2 lần làm bài trên cùng một dạng nhiệm vụ.
  * *Đầu ra:* Trả về chênh lệch điểm (delta) theo từng tiêu chí; bảo lưu cả 2 bản ghi đánh giá cũ và mới.

---

### F09: Quản trị nội dung (Admin)
* **`POST /api/v1/admin/content/publish`**
  * *Phân quyền:* Chỉ tài khoản có `role: "ADMIN"` mới được gọi (User thường nhận 403 Forbidden).
  * *Nguyên tắc bất biến:* Phiên bản đã xuất bản không được ghi đè trực tiếp (nếu trùng $\rightarrow$ 409 Conflict).

---

### F10: Nhắc nhở trong ứng dụng
* **`POST /api/v1/reminders`**
  * *Body:* `{"reminder_type": "ACTIVITY_DUE", "message": "Nhắc nhở học tập", "target_id": "ACT_SQL_01"}`
  * *Chống trùng lặp (Deduplication):* Nếu đã có lời nhắc chưa đọc cùng loại và cùng mục tiêu, server không tạo bản ghi rác mới.
* **`GET /api/v1/reminders`**: Lấy danh sách nhắc nhở trong ứng dụng và số lượng chưa đọc.
* **`PATCH /api/v1/reminders/{reminder_id}/read`**: Đánh dấu đã đọc.

---

## 3. Danh sách Demo Tokens cho kiểm thử & Frontend
Frontend (TV2) và QA (TV6) có thể sử dụng các token sau trong header `Authorization: Bearer <token>`:
1. `token_student_1`: Học viên Nguyễn Văn A (ID: `11111111-1111-1111-1111-111111111111`).
2. `token_student_2`: Học viên Trần Thị B (ID: `22222222-2222-2222-2222-222222222222`).
3. `token_admin`: Giảng viên / Quản trị viên (ID: `99999999-9999-9999-9999-999999999999`, Role: `ADMIN`).
