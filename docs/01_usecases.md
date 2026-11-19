# CareerAdapt AI – Use cases (CSC10014 Week 02, mục 4–5)

Phiên bản hệ thống: 5.9 · Cập nhật: 05/11/2026

| File | Nội dung |
| --- | --- |
| `01_usecases.puml` | Nguồn PlantUML của sơ đồ use case chính |
| `01_usecases.png`, `01_usecases.svg` | Ảnh sơ đồ chính, bố cục cố định |
| `01_misuse_cases.puml` | Nguồn PlantUML của sơ đồ misuse case (bảo mật) |
| `01_misuse_cases.png`, `01_misuse_cases.svg` | Ảnh sơ đồ misuse case |
| `uml/` | Sơ đồ MVP cũ ngày 22/10/2026, giữ nguyên để đối chiếu |

Ảnh PNG/SVG được dựng với bố cục cố định cho dễ đọc. Khi render lại file `.puml` bằng PlantUML, vị trí các hình có thể khác, nhưng use case và quan hệ vẫn giữ nguyên.

## 1. Tác nhân

| Tác nhân | Loại | Vai trò |
| --- | --- | --- |
| Người học | Chính | Khởi động mọi use case. |
| Gemini (dịch vụ LLM) | «system» | Viết nhận xét, tóm tắt JD, trả lời tư vấn. Chỉ là phần hỗ trợ, luôn có phương án dự phòng theo quy tắc. |
| Dịch vụ email (SMTP) | «system» | Gửi liên kết khôi phục mật khẩu. |
| Kẻ tấn công | Tác nhân lạm dụng | Chỉ xuất hiện trong sơ đồ misuse case. |

Quyết định mô hình hóa:
- **Không vẽ ô "Chat".** Khung trợ lý chỉ là một kênh. Mục tiêu đứng sau kênh này là UC-11 "Nhận tư vấn học tập": giải thích kết quả, khoảng cách kỹ năng và lộ trình.
- **Không có tác nhân quản trị nội dung**, theo quyết định của nhóm ở sơ đồ trước (`uml/README.md`). Trang quản trị vẫn có trong code nhưng nằm ngoài sơ đồ này.
- **"Làm lại quy trình" (reset)** là chức năng hỗ trợ, không phải mục tiêu chính, nên không vẽ để giữ đúng 12 mục tiêu.

## 2. Use case, mức ưu tiên và truy vết

Nhãn: **M**ust · **S**hould · **C**ould. Mọi use case dưới đây đã có trong bản 5.9.

| ID | Use case | Ưu tiên | Giao diện | Backend | Test tự động |
| --- | --- | --- | --- | --- | --- |
| UC-01 | Đăng nhập tài khoản | M | `login.html`, `login.js` | `api/auth_routes.py`, `accounts.py` | `test_auth_sessions.py` |
| UC-01.1 | Khôi phục mật khẩu («extend» UC-01) | S | `login.js` | `auth_routes.py` (`/password/forgot`, `/password/reset`), `mailer.py` | `test_reset_password_flow_single_use_and_revokes_sessions` |
| UC-02 | Khai báo kỹ năng hiện tại | M | `pages/flow.js` | `api/skill_report.py`, `engine/skill_report.py` | `test_skill_report.py` |
| UC-03 | Chọn JD mục tiêu | M | `pages/target.js`, `flow.js` | `api/jds.py`, `targeting.py` | `test_v4_jd.py`, `tests_jd.py` |
| UC-03.1 | Phân tích yêu cầu JD («include») | M | – | `engine/jd_parser.py` | `test_v4_jd.py` |
| UC-03.2 | Tóm tắt JD bằng AI («extend») | S | `pages/plan.js` (nút "AI tóm tắt") | `ai_service/task_engine.py` (`jd_analysis`) | `test_jd_summary_uses_ai_when_configured`, `test_jd_summary_is_labelled_rule_without_ai` |
| UC-04 | Làm bài kiểm tra năng lực | M | `pages/exam.js`, `workspaces.js` | `exam_service.py`, `engine/sql_sandbox.py`, `python_sandbox.py` | `test_v5_process.py`, `test_workspaces.py` |
| UC-04.1 | Chấm bài theo rubric («include») | M | – | `engine/exam_grader.py`, `rubric_engine.py` | `test_v5_exam_bank.py`, `test_v4_grading.py` |
| UC-AI | Viết nhận xét bằng AI («extend» UC-04.1, UC-08.1) | S | `exam.js`, `check.js` | `ai_service/llm_grader.py`, `guardrails.py`, `api/learning_tasks.py` | `test_ai_guardrails.py`, `test_ai_cannot_inflate_a_wrong_exam`, `test_ai_feedback_*` |
| UC-05 | Xem kết quả bài làm | M | `pages/plan.js` (tab Kết quả bài làm) | `exam_service.review` | `test_review_is_refused_before_submission` |
| UC-06 | Xem khoảng cách kỹ năng | M | `pages/gap.js`, `charts.js` | `engine/gap_coverage.py`, `targeting.py` | `test_engine_math.py`, `test_process_gap_uses_only_verified_levels` |
| UC-07 | Tạo lộ trình học tập | M | `flow.js`, `pages/roadmap.js` | `engine/roadmap_planner.py`, `dag_scheduler.py` | `test_v4_roadmap.py`, `test_dag_scheduler.py` |
| UC-08 | Hoàn thành học phần | M | `roadmap.js` | `api/learning_tasks.py`, `lesson_checks.py` | `test_learning_tasks.py` |
| UC-08.1 | Làm bài kiểm tra kiến thức («include») | M | `pages/check.js` | `api/learning_cycle.py` | `test_learning_tasks.py`, `test_v4_learning_cycle.py` |
| UC-09 | Ôn tập theo lịch nhắc | S | `pages/progress.js` (tab Nhắc nhở) | `learning_cycle_service.py` | `test_v4_learning_cycle.py` |
| UC-10 | Luyện tập kiểm tra kiến thức | S | `pages/tests.js` | `api/test_center.py`, `engine/test_engine.py` | `test_test_center.py` |
| UC-11 | Nhận tư vấn học tập | C | `assistant.js` | `ai_service/assistant.py`, `tool_registry.py` | `test_ai_assistant.py` |
| UC-12 | Xuất báo cáo năng lực | C | `pages/report.js` | dùng lại các API đọc dữ liệu | chưa có test tự động; đã kiểm tra trên trình duyệt |

Ngoài phạm vi (Won't, lúc này): tìm việc, tạo CV, nhập liệu bằng giọng nói, thông báo đẩy/email nhắc học, xếp hạng nhiều nghề.

## 3. Ma trận lớp (UI · AI · Data · Security)

| Use case | UI | AI | Data | Security |
| --- | :-: | :-: | :-: | :-: |
| UC-01 Đăng nhập tài khoản | ● | · | ● | ● |
| UC-03 Chọn JD mục tiêu (+ phân tích, tóm tắt AI) | ● | ● | ● | ● |
| UC-04 Làm bài kiểm tra năng lực (+ chấm, nhận xét AI) | ● | ● | ● | ● |
| UC-05 Xem kết quả bài làm | ● | · | ● | ● |
| UC-06 Xem khoảng cách kỹ năng | ● | · | ● | · |
| UC-07 Tạo lộ trình học tập | ● | · | ● | · |
| UC-08 Hoàn thành học phần (+ kiểm tra kiến thức) | ● | ● | ● | ● |
| UC-09 Ôn tập theo lịch nhắc | ● | · | ● | · |
| UC-10 Luyện tập kiểm tra kiến thức | ● | · | ● | ● |
| UC-11 Nhận tư vấn học tập | ● | ● | ● | ● |
| UC-12 Xuất báo cáo năng lực | ● | · | ● | · |

## 4. Đặc tả đầy đủ (hai use case Must)

### UC-04 · Làm bài kiểm tra năng lực · Người học

| Trường | Nội dung |
| --- | --- |
| Kích hoạt | Người học bấm bắt đầu bài kiểm tra trong Quy trình Career Adapt. |
| Tiền điều kiện | Đã khai báo kỹ năng (UC-02) và xác nhận JD (UC-03); tài khoản chưa có bài kiểm tra đã chấm trong quy trình hiện tại. |
| Hậu điều kiện | Điểm, mức đã xác thực của từng kỹ năng và giải thích được lưu làm bằng chứng; bài bị khóa, không sửa hay nộp lại được. |
| Chỉ số thành công | Điểm chỉ do bộ chấm theo rubric quyết định: câu bỏ trống luôn được 0, AI không làm tăng điểm (có test kiểm chứng). Thời gian chấm trên máy thật chưa được đo. |

Luồng chính:
1. Hệ thống tạo đề theo mức tự khai và các kỹ năng trong JD.
2. Người học trả lời từng câu; câu trả lời được lưu trên máy chủ mỗi lần chuyển câu.
3. Với câu SQL/Python, người học chạy thử trong sandbox để xem kết quả.
4. Người học nộp bài.
5. Hệ thống chấm theo rubric (UC-04.1). Nếu AI đang bật, AI viết thêm nhận xét có dẫn chứng (UC-AI).
6. Người học xem kết quả (UC-05).

Luồng thay thế:
- **2a.** Hết giờ: bài tự nộp với các câu đã lưu.
- **2b.** Rời màn hình lần thứ 3: bài tự nộp. Dán nội dung bị chặn chỉ được ghi nhận, không tính là vi phạm.
- **2c.** Câu trả lời quá dài hoặc không thuộc đề: bị từ chối, bài vẫn giữ nguyên.
- **5a.** Câu bỏ trống: 0 điểm.
- **5b.** AI quá thời gian chờ: vẫn có điểm cuối, không mất bài.
- **5c.** AI trích dẫn không có trong bài làm: nhận xét đó bị bỏ và gắn cờ, điểm không đổi.

Tiêu chí chấp nhận:
- **Given** bài kiểm tra bỏ trống mọi câu, **When** người học nộp, **Then** điểm là 0 và mức xác thực là 0 – `test_blank_exam_is_final_with_zero_and_level_zero`.
- **Given** một bài làm sai và AI trả về lời khen, **When** hệ thống chấm, **Then** điểm vẫn bằng điểm theo rubric – `test_ai_cannot_inflate_a_wrong_exam`.
- **Given** thời gian làm bài đã hết, **When** người học mở lại hoặc hệ thống kiểm tra bài, **Then** bài được nộp với các câu đã lưu trên máy chủ – `test_time_up_submits_what_was_saved_on_the_server`.

### UC-08 · Hoàn thành học phần (bao gồm UC-08.1 Làm bài kiểm tra kiến thức) · Người học

| Trường | Nội dung |
| --- | --- |
| Kích hoạt | Người học chọn "Hoàn thành" khi cập nhật tiến độ một học phần trong lộ trình. |
| Tiền điều kiện | Học phần thuộc lộ trình hiện tại và chưa được xác minh. |
| Hậu điều kiện | Tiến độ học phần là "đã học xong". Kết quả kiểm tra được lưu. Mức kỹ năng chỉ thay đổi khi bài kiểm tra đạt. |
| Chỉ số thành công | Không có bằng chứng kỹ năng nào được ghi nếu bài chưa đạt ngưỡng 80/100; mỗi lần đạt chỉ ghi bằng chứng một lần (có test kiểm chứng). |

Luồng chính:
1. Người học chọn "Hoàn thành". Hệ thống nhắc rằng học xong chưa phải là thành thạo, và người học xác nhận.
2. Hệ thống ghi tiến độ, rồi tạo bài kiểm tra 3–8 câu từ ngân hàng câu hỏi đã duyệt, theo mục tiêu của học phần.
3. Người học làm bài; bản nháp được tự lưu.
4. Người học nộp bài và máy chủ chấm điểm.
5. Đạt từ 80/100: học phần chuyển sang "Đã xác minh" và bằng chứng kỹ năng được ghi.
6. Người học có thể yêu cầu AI nhận xét bài đã chấm (UC-AI).

Luồng thay thế:
- **1a.** Không xác nhận: không thay đổi gì.
- **2a.** Ngân hàng câu hỏi không đủ: bài kiểm tra ở trạng thái "không có sẵn", mức kỹ năng không đổi.
- **2b.** Đã có bài đang mở: hệ thống trả về đúng bài đó, không tạo thêm bài mới.
- **4a.** Câu bỏ trống được tính 0 điểm.
- **5a.** Dưới 80/100: học phần ở trạng thái "Cần ôn tập" kèm các chủ đề yếu. Lần làm lại tạo một lượt mới và giữ lượt cũ.
- **6a.** AI lỗi, hoặc nhận xét chứa con số không có thật: nhận xét bị từ chối hoặc loại bỏ, điểm không đổi.

Tiêu chí chấp nhận:
- **Given** một học phần chưa xác minh, **When** người học chọn hoàn thành và xác nhận, **Then** học phần ở trạng thái "Chờ kiểm tra" và chưa có bằng chứng – `test_completing_needs_confirmation_and_moves_to_pending_assessment`.
- **Given** bài kiểm tra kiến thức đang mở, **When** người học nộp bài đạt ngưỡng, **Then** học phần được xác minh và bằng chứng được ghi đúng một lần – `test_passing_verifies_the_task_and_records_evidence_once`.
- **Given** bài kiểm tra kiến thức đang mở, **When** người học nộp bài chưa đạt, **Then** học phần cần ôn tập và không có bằng chứng – `test_failing_needs_review_without_evidence`.

## 5. Misuse case và biện pháp giảm thiểu

| Misuse case | Đe dọa | Biện pháp («include» trong use case gốc) | Bằng chứng kiểm thử |
| --- | --- | --- | --- |
| M1 Dò mật khẩu | UC-01 | S1 Giới hạn đăng nhập sai: 6 lần mỗi email và 30 lần mỗi IP trong 15 phút, trả lỗi 429 | `test_repeated_wrong_passwords_lock_the_email_for_a_while` (`test_audit_hardening.py`) |
| M2 Chạy mã độc trong bài làm | UC-04 | S2 Chạy mã trong sandbox, ngoài tiến trình API, chỉ đọc dữ liệu bài | `test_sandbox_blocks_anything_but_reading_the_dataset`, `test_sandbox_runs_outside_the_api_process` (`test_v4_grading.py`) |
| M3 Chèn lệnh vào bài làm để lái AI chấm | UC-04.1 | S3 Kiểm chứng nhận xét AI: bài làm chỉ là dữ liệu; trích dẫn và con số phải có thật; AI không đổi được điểm | `test_sec01_injection_in_answers_is_only_data`, `test_sec01_ai_receives_injection_only_as_student_data`, `test_ai_guardrails.py` |
| M4 Xem kết quả của người khác | UC-05 | S4 Kiểm tra quyền truy cập: dữ liệu luôn gắn với tài khoản đang đăng nhập; truy cập sai bị từ chối và ghi nhật ký | `test_accounts_do_not_see_each_others_exam`, `test_assessment_of_another_learner_is_refused_and_logged`, `test_another_learner_cannot_touch_a_test_attempt` |
| M5 Hỏi trợ lý dữ liệu của người khác | UC-11 | S4: công cụ của trợ lý chỉ đọc dữ liệu của tài khoản trong phiên, không nhận mã tài khoản hay câu SQL từ AI | `test_a_tool_call_reads_the_session_account_whatever_the_model_asks`, `test_no_tool_accepts_an_account_id_or_sql` (`test_ai_assistant.py`) |
