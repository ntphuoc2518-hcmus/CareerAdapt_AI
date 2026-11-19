# Phần D. Danh sách vấn đề chi tiết (P0 → P3)

Thuộc bộ báo cáo kiểm định ngày 12/11/2026. Tài liệu chính: [AUDIT_REPORT.md](../../AUDIT_REPORT.md).

Mỗi vấn đề có một **loại**:

- **Lỗi đã xác nhận:** đã tái hiện bằng chạy thật.
- **Rủi ro có bằng chứng:** thấy trong mã hoặc cấu hình nhưng chưa tái hiện trọn vẹn.
- **Hạn chế thiết kế:** hệ thống chạy đúng như thiết kế nhưng thiết kế chưa đáp ứng tốt bài toán.
- **Đề xuất cải tiến:** không phải lỗi.

## P0 – Critical

**Không phát hiện vấn đề P0.** Không thấy mất dữ liệu, lộ dữ liệu giữa tài khoản, sai công thức cốt lõi hay chức năng chính không dùng được. Căn cứ: 898/898 test đạt, thăm dò truy cập chéo, CSRF và phân quyền đều chặn đúng (Phần B, kịch bản 7).

## P1 – High

### A-01. Mức tự khai quyết định mức tối đa có thể chứng minh trong bài kiểm tra đầu vào

| Trường | Nội dung |
|---|---|
| Loại | Lỗi đã xác nhận (nghiệp vụ) |
| Module | Đánh giá năng lực, Khoảng cách kỹ năng |
| Hiện trạng | Độ khó của câu hỏi lấy từ mức tự khai: không khai hoặc khai 0–1 → câu Cơ bản; khai 2 → Trung bình; khai 3 → Khó. Câu Cơ bản chỉ chứng minh tối đa mức 1, kể cả khi đúng 100% |
| Bằng chứng | `backend/engine/exam_grader.py:33` `tier_for_level`, `:38` `verified_level`, `:72` `plan_questions`. Tái hiện trên bản sao (Phần B, kịch bản 5): đúng 100/100 nhưng chỉ khai SQL=1 → mức 1 ở cả 5 kỹ năng, JD yêu cầu mức 2 → thiếu 1 mức ở 4 kỹ năng, readiness 57,5; khai 3 → mức 3 |
| Nguyên nhân gốc | Mỗi kỹ năng chỉ có 1 câu, nên phải chọn độ khó trước khi biết năng lực. Hệ thống dùng mức tự khai để chọn. Mức tự khai tuy không được tính là bằng chứng nhưng vẫn quyết định kết quả |
| Hậu quả nếu không sửa | Người khiêm tốn bị đánh giá thấp và phải học lại thứ đã biết. Người khai cao không bị thiệt nên hệ thống khuyến khích khai cao. Kết quả "100 điểm nhưng đáp ứng 1/5 kỹ năng" gây mất tin tưởng |
| Giải pháp | Chọn độ khó theo **mức JD yêu cầu** chứ không theo mức tự khai (mức tự khai chỉ dùng để sắp thứ tự câu). Tốt hơn nữa là thi thích ứng 2 nấc: câu ở mức mục tiêu; đạt thì có thể thêm câu cao hơn, trượt thì thêm câu thấp hơn để biết đang ở mức nào |
| Phạm vi thay đổi | `engine/exam_grader.py` (`plan_questions`), `exam_service.py` (`start`, `_conclusion`), có thể cả thời lượng bài; test `test_v5_exam_bank.py`, `test_v5_process.py` |
| Độ phức tạp | Trung bình (phương án theo mức JD); Cao (thi thích ứng) |
| Điều kiện nghiệm thu | Test mới: không khai kỹ năng nào, nộp đáp án mẫu đúng → mức xác thực ≥ mức JD ở mọi kỹ năng. Test: khai 3 nhưng làm sai → không vượt quá mức chứng minh được. Các test cũ vẫn đạt (sửa kỳ vọng cũ chỉ khi nó đang khẳng định hành vi sai này, và ghi lý do) |

### A-02. Bài viết được chấm bằng từ khóa nên có thể đạt mức cao mà không lập luận

| Trường | Nội dung |
|---|---|
| Loại | Lỗi đã xác nhận (độ chính xác đánh giá) |
| Module | Đánh giá năng lực, bộ chấm bài viết |
| Hiện trạng | Loại kiểm tra `text_regex` chỉ cần có từ khóa ở bất kỳ đâu. Bài STAT-3, VIZ-1, WC-2, WC-3 phần lớn điểm đến từ regex |
| Bằng chứng | `exam_grader.py:275` (`text_regex`). Thử nghiệm G (Phần B, kịch bản 6): STAT-3 (Khó) với 2 số đúng và "Mẫu nhỏ. t-test. Ngẫu nhiên, nhóm đối chứng." → 100/100, **mức 3**. WC-3 (Khó) chỉ có tiêu đề và từ khóa, không có số → 60/100, **mức 2** |
| Nguyên nhân gốc | Không kiểm tra cấu trúc lập luận (câu chứa từ khóa có nối với số liệu hay lý do không). Lớp duy nhất có thể phát hiện là AI, mà AI chỉ chuyển bài đi duyệt khi lệch ≥2 mức và chỉ chạy khi có khóa |
| Hậu quả | Không phân biệt được người hiểu với người thuộc từ khóa, tức đúng điểm yếu mà đề bài kiểm định nêu. Mức 3 có thể đạt bằng một câu trả lời dài 1 dòng |
| Giải pháp | (1) Giới hạn tổng điểm từ regex trong mỗi câu (ví dụ ≤40%). (2) Thêm loại kiểm tra "từ khóa trong câu có lý do": câu chứa khái niệm phải đủ dài và có từ nối nguyên nhân (vì, do, nên, because) hoặc con số. (3) Câu khó dạng viết bắt buộc qua AI chấm theo rubric có trích dẫn; khi AI tắt thì đưa vào hàng chờ duyệt thay vì cho mức 3 ngay. (4) Thêm ý "phản ví dụ" (ví dụ hỏi điều gì làm kết luận sai) mà từ khóa không trả lời được |
| Phạm vi | `engine/exam_grader.py`, `data/exam_items_v5.json` (cases), `ai_service/llm_grader.py` (chính sách duyệt), test mới chống lách |
| Độ phức tạp | Trung bình |
| Nghiệm thu | Bộ "câu trả lời lách" (từ khóa trần, chỉ tiêu đề, rải số) cho mọi câu viết không vượt mức 1. Đáp án mẫu hiện có vẫn 100. Thêm vào `tests/test_v5_exam_bank.py` |

### A-03. Bài kiểm tra hoàn thành bài học (trắc nghiệm, làm lại ngay) có thể xác nhận tới mức 3

| Trường | Nội dung |
|---|---|
| Loại | Rủi ro có bằng chứng (chưa tái hiện trọn vòng làm lại đến khi đạt) |
| Module | Lộ trình học tập, kiểm tra hoàn thành |
| Hiện trạng | Bài 3–8 câu đóng (chọn một, chọn nhiều, số, sắp xếp), đạt ≥80%. Từ 5.16.2, đạt thì mức = min(ước lượng, mức mục tiêu bài học), không còn giới hạn +1. Làm lại ngay, không giới hạn số lần. Mỗi kỹ năng chỉ khoảng 20 câu, kèm giải thích sau mỗi lần |
| Bằng chứng | `lesson_checks.py:27` (`LESSON_CHECK_MAX_ITEMS = 8`), `:41` `select_lesson_items` (ưu tiên câu chưa gặp nhưng vẫn lặp khi hết); `api/learning_cycle.py:311-322` (cách nâng mức). Thống kê ngân hàng: 6–7 câu cho mỗi kỹ năng × mức |
| Nguyên nhân gốc | Thay đổi ở 5.16.2 sửa đúng lỗi "học xong mà khoảng cách vẫn còn", nhưng làm cho bằng chứng trắc nghiệm ngang hàng bằng chứng thực hành |
| Hậu quả | Mức 3 có thể đạt bằng cách làm đi làm lại và nhớ đáp án. Độ tin cậy của mức sau lộ trình thấp hơn mức ở bài đầu vào |
| Giải pháp | (1) Thời gian chờ giữa hai lần làm (ví dụ 12 giờ) hoặc bắt buộc bộ câu khác hoàn toàn. (2) Bài học có mục tiêu mức ≥2 phải có 1 câu thực hành ngắn (tận dụng `practice_items_v1.json` + sandbox). (3) Hoặc chỉ cho trắc nghiệm xác nhận tối đa mức 1, mức 2–3 do bài đánh giá tổng hợp cuối lộ trình xác nhận. Cách này cần thay đổi cách tính "học xong" |
| Phạm vi | `lesson_checks.py`, `api/learning_cycle.py`, `api/learning_tasks.py`, `data/question_bank_v1.json`, test nhóm A–G |
| Độ phức tạp | Trung bình |
| Nghiệm thu | Làm lại ngay sau khi trượt bị từ chối hoặc nhận bộ câu không trùng. Mức 3 không thể đạt chỉ bằng câu đóng. Test hiện có về "học xong thì hết khoảng cách" vẫn đạt |

### A-04. Ngân hàng đề đầu vào quá nhỏ và đáp án lộ sau khi chấm

| Trường | Nội dung |
|---|---|
| Loại | Hạn chế thiết kế |
| Module | Đánh giá năng lực |
| Hiện trạng | 18 câu (6 kỹ năng × 3 độ khó, mỗi ô 1 câu) × 2 bộ dữ liệu (`orders_da01a.csv`, `orders_da01b.csv`, mỗi bộ 10 dòng). Mọi người ở cùng độ khó nhận cùng một đề, chỉ khác bộ dữ liệu. Trang xem lại ghi "Đáp án đúng: …" |
| Bằng chứng | Thống kê `data/exam_items_v5.json` (bank EX-DA-1.2). P: trang xem lại có 2 ý "Đáp án đúng" chỉ với 1 câu đã làm. `exam_grader.py:90` chỉ đổi bộ dữ liệu khi đã gặp; sau 2 lần reset thì lặp lại |
| Nguyên nhân gốc | Ngân hàng 5.x mới được xây; đáp án tính từ dữ liệu bằng SQL tin cậy (tốt), nhưng chưa có cơ chế sinh dữ liệu |
| Hậu quả | Đáp án lan giữa người học. Người reset làm lại gặp đúng đề đã biết đáp án. Kết quả kém tin cậy theo thời gian |
| Giải pháp | (1) Sinh bộ dữ liệu ngẫu nhiên cho mỗi lượt làm theo cùng lược đồ. Đáp án đã tính bằng `expected_sql` nên không cần sửa bộ chấm. (2) ≥3 câu cho mỗi ô kỹ năng × độ khó. (3) Trang xem lại chỉ ra phương pháp đúng và chỗ sai, không in con số đáp án khi câu còn trong ngân hàng hoạt động |
| Phạm vi | `engine/exam_grader.py`, `engine/sql_sandbox.py` (`load_dataset`), `data/exam_items_v5.json`, `exam_service.review`, test bank |
| Độ phức tạp | Cao (nội dung) / Trung bình (sinh dữ liệu) |
| Nghiệm thu | Hai lượt làm liên tiếp có số liệu khác nhau. Mọi đáp án mẫu vẫn 100 trên 50 bộ dữ liệu ngẫu nhiên. `validate_bank` yêu cầu ≥3 câu mỗi ô |

### A-05. Đổi JD hoặc nghề mục tiêu buộc reset toàn bộ và mất năng lực đã xác thực

| Trường | Nội dung |
|---|---|
| Loại | Hạn chế thiết kế (hành vi đã xác nhận) |
| Module | Quy trình Career Adapt, Hồ sơ nghề nghiệp, Khoảng cách, Lộ trình |
| Hiện trạng | Sau bước JD không đổi được JD. Sau khi hoàn tất chỉ có reset. Reset đặt `assessed_skills={}` |
| Bằng chứng | `career_process.py:102` `_archive_learning_state`, `:123`; P: kịch bản 4 → 409 "…Muốn làm lại, hãy reset quy trình" |
| Nguyên nhân gốc | Quy trình được thiết kế một chiều để chống sửa kết quả. Bằng chứng kỹ năng (`skill_evidence`) không phụ thuộc JD nhưng bị gom chung vào cùng một lần reset |
| Hậu quả | Kịch bản 4 của đề bài (đổi mục tiêu → cập nhật gap → điều chỉnh lộ trình) không thực hiện được nếu không làm lại bài thi. Người học bị phạt khi đổi định hướng |
| Giải pháp | Thêm hành động "Đổi mục tiêu": tạo phiên bản mục tiêu mới (`target_versions` đã có), **giữ** mức đã xác thực, tính lại gap theo JD mới, replan (đã có `replan`). Chỉ những kỹ năng JD mới cần mà chưa đo mới phải thi. Reset toàn bộ vẫn giữ cho ai muốn làm lại từ đầu |
| Phạm vi | `career_process.py`, `api/career_process.py`, `api/jds.py` (`guard_step`), `api/roadmaps.py`, `exam_service.py` (bài thi bổ sung), giao diện `process.js`/`plan.js` |
| Độ phức tạp | Cao |
| Nghiệm thu | Đổi JD sau khi hoàn tất: mức cũ giữ nguyên, gap tính theo JD mới, lộ trình mới có `change_reason`. Lịch sử ghi sự kiện đổi mục tiêu. Reset cũ vẫn chạy như trước |

## P2 – Medium

### B-01. Lộ trình không phát hiện tuần trễ hạn và không tự dời lịch

- **Loại / module:** Lỗi đã xác nhận (nghiệp vụ, giao diện) / Lộ trình.
- **Hiện trạng và bằng chứng:**
  - U trên bản sao ngày 12/11: tuần 1 (2–8/11) và tuần 2 (9–15/11) có 0% nhưng hiện "Chưa bắt đầu", không có cảnh báo.
  - Không có logic "overdue" trong `learning_journey.py`; `meets_deadline` chỉ phản ánh lúc lập lịch.
- **Nguyên nhân:** lịch tính một lần khi lập lộ trình, theo ngày bắt đầu cố định.
- **Hậu quả:** ngày "dự kiến hoàn thành" sai và người học không biết mình đang chậm.
- **Giải pháp:**
  - Tính trạng thái tuần theo ngày hiện tại (Trễ N ngày).
  - Nút "Dời lịch từ hôm nay" gọi lại `dag_scheduler` với ngày bắt đầu mới và lưu thành phiên bản lộ trình mới (đã có `replan`).
  - Cảnh báo trên bảng điều khiển.
- **Phạm vi:** `learning_journey.journey`, `api/roadmaps.replan`, `pages/roadmap.js`, `pages/dashboard.js`.
- **Độ phức tạp:** Thấp–Trung bình.
- **Nghiệm thu:** test giả lập đồng hồ (`backend/clock.py`) qua ngày kết thúc tuần → tuần mang trạng thái trễ; dời lịch thì ngày tuần mới bắt đầu từ hôm nay.

### B-02. Giám sát rời màn hình do trình duyệt tự báo

- **Loại / module:** Hạn chế thiết kế / Bài thi.
- **Bằng chứng:** `exam_service.py:208` `record_event` chỉ đếm sự kiện client gửi lên; một client không gửi thì không có vi phạm.
- **Hậu quả:** dễ hiểu nhầm là chống gian lận thật.
- **Giải pháp:**
  - Ghi rõ đây là tín hiệu tham khảo.
  - Thêm tín hiệu phía máy chủ: thời gian giữa các lần lưu, kích thước thay đổi đột ngột của câu trả lời (dán), độ giống câu trả lời giữa các tài khoản.
  - Hiển thị cho admin, không tự trừ điểm.
- **Phạm vi:** `exam_service.py`, `final_assessment.py`, admin.
- **Độ phức tạp:** Trung bình.
- **Nghiệm thu:** báo cáo admin liệt kê được bài có câu trả lời trùng giữa hai tài khoản.

### B-03. Trạng thái người học nằm trong bộ nhớ tiến trình, chỉ chạy được 1 tiến trình

- **Loại / module:** Rủi ro có bằng chứng / Kiến trúc dữ liệu.
- **Bằng chứng:**
  - `store.py` (dict `profiles`, `roadmaps`) và `persist_user_runtime` ghi cả hồ sơ thành một JSON.
  - `database.py:272-274` dùng một kết nối với `RLock`.
- **Hậu quả:**
  - Chạy 2 worker sẽ khiến dữ liệu lệch nhau.
  - Hai tab cùng sửa hồ sơ có thể ghi đè nhau (chưa tái hiện).
- **Giải pháp:**
  - Ngắn hạn: ghi rõ chỉ chạy 1 worker; thêm cột phiên bản (optimistic lock) cho `learner_state`.
  - Dài hạn: tách hồ sơ thành bảng; đọc từ CSDL mỗi request; dùng kết nối theo request với WAL.
- **Phạm vi:** `store.py`, `database.py`, mọi nơi dùng `store.profiles`.
- **Độ phức tạp:** Cao.
- **Nghiệm thu:** test đồng thời 2 luồng cập nhật cùng hồ sơ không mất dữ liệu.

### B-04. Chấm bài đồng bộ trong request

- **Loại / module:** Rủi ro có bằng chứng / Hiệu năng.
- **Bằng chứng:**
  - `exam_service.submit` → `_grade` → `verify_exam` chạy từng câu Python (≤20 s/câu, `python_sandbox.TIMEOUT_SECONDS`).
  - P: nộp 1 câu SQL mất 1,35 s.
- **Hậu quả:** nhiều người nộp cùng lúc thì request chờ lâu hoặc hết thread.
- **Giải pháp:**
  - Đưa chấm vào hàng đợi nền. Trạng thái `SUBMITTED → GRADING → GRADED` đã có sẵn nên giao diện chỉ cần thăm dò.
  - Giới hạn số sandbox chạy song song.
- **Phạm vi:** `exam_service.py`, `final_assessment.py`, `background.py`, giao diện thi.
- **Độ phức tạp:** Trung bình.
- **Nghiệm thu:** API nộp trả về <300 ms; 10 bài nộp đồng thời đều được chấm đúng.

### B-05. Sandbox Python trên Windows chưa phải ranh giới bảo mật

- **Loại / module:** Hạn chế thiết kế (đã tự ghi trong mã) / Thực thi mã.
- **Bằng chứng:** docstring `engine/python_sandbox.py`: "it is not a security boundary against a determined attacker". Lớp bảo vệ hiện có gồm danh sách cho phép import, chặn dunder, audit hook và Job Object.
- **Hậu quả:** an toàn cho đồ án chạy cục bộ; không đủ cho triển khai công khai.
- **Giải pháp:** khi triển khai, chạy worker trong container không mạng, người dùng không đặc quyền, hệ thống tệp chỉ đọc (ví dụ Docker `--network none --read-only`).
- **Phạm vi:** `python_sandbox.py`, hạ tầng.
- **Độ phức tạp:** Trung bình.
- **Nghiệm thu:** bộ test `test_workspaces.py` chạy trong container và vẫn đạt.

### B-06. Liên kết đặt lại mật khẩu dựng từ header Host

- **Loại / module:** Rủi ro có bằng chứng / Bảo mật tài khoản.
- **Bằng chứng:** `api/auth_routes.py:232` dùng `request.base_url`; không có `TrustedHostMiddleware` (grep không thấy).
- **Hậu quả:** khi triển khai sau proxy không kiểm Host, kẻ tấn công gửi yêu cầu quên mật khẩu với Host giả. Email thật chứa liên kết sang miền của họ; nạn nhân bấm vào là lộ token.
- **Giải pháp:** biến cấu hình `CAREERADAPT_PUBLIC_URL` dùng cho mọi liên kết trong email; thêm `TrustedHostMiddleware` ở production.
- **Phạm vi:** `auth_routes.py`, `main.py`, `config.py`, `.env.example`.
- **Độ phức tạp:** Thấp.
- **Nghiệm thu:** test gửi Host giả → liên kết vẫn dùng URL cấu hình.

### B-07. Giới hạn tần suất theo IP kết nối trực tiếp

- **Loại / module:** Rủi ro có bằng chứng / Bảo mật.
- **Bằng chứng:** `auth_routes.py` dùng `request.client.host` cho đăng nhập, đăng ký, quên mật khẩu.
- **Hậu quả:** sau proxy, mọi người dùng chung một IP. Vài lần sai là khóa đăng ký hoặc đăng nhập của cả hệ thống.
- **Giải pháp:** cấu hình danh sách proxy tin cậy và đọc `X-Forwarded-For` chỉ từ proxy đó (uvicorn `--forwarded-allow-ips`).
- **Phạm vi:** `run.py`, `auth_routes.py`.
- **Độ phức tạp:** Thấp.
- **Nghiệm thu:** test với header từ proxy tin cậy tách đúng hai IP.

### B-08. AI thật chưa được kiểm chứng trong lần kiểm định; là lớp duy nhất có thể bắt bài lách từ khóa

- **Loại / module:** Hạn chế (chưa xác minh) / AI.
- **Bằng chứng:** 10 test `test_ai_live.py` bị bỏ qua. `.env` cấu hình Gemini nhưng không gọi trong kiểm định.
- **Hậu quả:** chưa có số liệu về tỷ lệ AI bắt được bài lách, độ trễ hay độ ổn định nhận xét.
- **Giải pháp:**
  - Bộ đánh giá AI ngoại tuyến: 30–50 bài mẫu đã gán mức (kể cả bài lách), chạy định kỳ.
  - Ghi tỷ lệ đồng ý máy–AI–người.
  - Chạy `test_ai_live.py` với khóa test riêng.
- **Phạm vi:** `tests/`, `ai_service/llm_grader.py`.
- **Độ phức tạp:** Trung bình.
- **Nghiệm thu:** báo cáo có tỷ lệ phát hiện bài lách ≥ ngưỡng nhóm đặt ra.

### B-09. Không có khóa ngoại; dữ liệu nghiệp vụ nằm trong JSON

- **Loại / module:** Hạn chế thiết kế / CSDL.
- **Bằng chứng:**
  - 43 bảng, 0 khóa ngoại.
  - `learner_state.payload`, `career_runs.payload` chứa hồ sơ, lộ trình, ảnh chụp lưu trữ.
  - Tài khoản ở CSDL khác.
- **Hậu quả:** dữ liệu mồ côi khó phát hiện; thống kê phải đọc JSON trong Python.
- **Giải pháp:**
  - Script kiểm tra nhất quán chạy định kỳ: bản ghi trỏ tới user không tồn tại, attempt không có run…
  - Dần tách các trường hay truy vấn ra cột hoặc bảng.
- **Phạm vi:** `database.py`, `scripts/`.
- **Độ phức tạp:** Trung bình.
- **Nghiệm thu:** script trả về 0 bất thường trên bản sao dữ liệu thật.

## P3 – Low

| Mã | Vấn đề | Loại | Bằng chứng | Giải pháp | Độ phức tạp |
|---|---|---|---|---|---|
| C-01 | README ghi V5.3, ứng dụng 5.17 | Đã xác nhận | `README.md:1`, `config.py` `APP_VERSION` | Cập nhật README: tính năng 5.11–5.17, cách chạy, giới hạn | Thấp |
| C-02 | Phụ thuộc không ghim phiên bản; cảnh báo `httpx` → `httpx2` | Đã xác nhận | `requirements.txt`; cảnh báo pytest | Thêm tệp khóa phiên bản (`requirements.lock`) đúng các bản đang chạy; nâng cấp có kiểm soát | Thấp |
| C-03 | Router gắn hai lần, trùng `operationId` | Đã xác nhận | `main.py:138-155`; cảnh báo OpenAPI | Giữ một tiền tố; đường cũ trả 308 về `/api/v1` hoặc ẩn khỏi schema | Thấp |
| C-04 | GET có tác dụng phụ (chấm bài, xác nhận lại mức, replan) | Đã xác nhận | `exam_service.current_attempt`, `/me/gap` → `reconfirm_levels` | Chuyển việc ghi sang tác vụ nền hoặc POST tường minh | Trung bình |
| C-05 | Gửi email đồng bộ trong `/password/forgot` → thời gian phản hồi lộ email có tồn tại | Rủi ro | `auth_routes.py:221-234`, `mailer.py` timeout 10 s | Gửi email ở nền | Thấp |
| C-06 | JD thư viện cũ ghi "Thống kê… chưa có bài đo" dù đã có kỹ năng Thống kê | Quan sát (chưa xác định nguyên nhân) | U: trang Khoảng cách, JD Google | Công cụ admin ánh xạ lại JD thành phiên bản mới | Thấp |
| C-07 | Nghề mô phỏng hiện như lựa chọn bấm được | Đã xác nhận | P: 409 khi chọn QA Tester | Làm mờ, nhãn "Sắp có" | Thấp |
| C-08 | Ngưỡng đạt rải ở nhiều tệp (70/80/70) | Đã xác nhận | `exam_items_v5.json`, `learning_cycle_service.py:28`, `lesson_checks.py:29` | Gom vào một cấu hình chính sách đánh giá, hiển thị cho người học | Thấp |
| C-09 | Xếp hạng "năng lực hiện tại" tính trên 5 kỹ năng khung, không theo JD từng người | Hạn chế thiết kế | `insights.framework_skills` | Thêm lựa chọn xếp theo mức đáp ứng JD (readiness) khi đủ người cùng JD | Thấp |
| C-10 | Kết quả chạy Python được cache theo nội dung code, nên code dùng `random` trả kết quả cũ | Rủi ro thấp | `python_sandbox._run_cached` (`lru_cache`) | Bỏ cache khi code import `random`, hoặc ghi chú trong đề | Thấp |
