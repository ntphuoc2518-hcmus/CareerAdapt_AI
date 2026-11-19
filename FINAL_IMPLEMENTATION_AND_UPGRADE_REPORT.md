# CareerAdapt AI: báo cáo kiểm định, sửa chữa và nâng cấp toàn diện

Ngày thực hiện: 17/11/2026. Phiên bản trước: 5.45.1. Phiên bản sau: **5.46.0**.

Sao lưu trước khi sửa (mã nguồn, dữ liệu, `.env`, không gồm `.venv`): thư mục `CareerAdapt_AI_backup_truoc_kiem_dinh_master_20261117`, nằm cạnh thư mục dự án.

---

## A. Tổng quan

### Cách làm

- Đọc `CAREERADAPT_AI_FULL_SYSTEM_AUDIT_REPORT.md` (15/11, ưu tiên), `AUDIT_REPORT.md` (12/11) và lịch sử 5.33–5.45.1 trong `UPGRADE_REPORT.md`.
- Không mặc định trạng thái nào trong báo cáo cũ. Mỗi mục P1–P3 được xác nhận lại bằng mã nguồn và bằng phép thử thật (bài làm dựng sẵn để lách bộ chấm, code tấn công sandbox, máy chủ uvicorn thật, trình duyệt Edge thật).
- Mọi phép thử chạy trên cơ sở dữ liệu tạm. Cơ sở dữ liệu thật chỉ được mở ở chế độ chỉ đọc để đối chiếu; bảng `meta` trước và sau giống hệt nhau.
- Thứ tự ưu tiên: độ chính xác → ổn định → bảo mật → UX → hiệu năng → tính năng mới.

### Kết quả

| | Trước (5.45.1) | Sau (5.46.0) |
|---|---|---|
| Bộ test | 1185 passed, 11 skipped | **1284 passed, 11 skipped, 0 failed** |
| Lỗi mới tìm thấy và sửa | – | 6 (2 HIGH, 2 MEDIUM, 2 LOW) |
| Mục P1–P3 đã xử lý | – | 12 mục (chi tiết ở B) |
| Nâng cấp | – | 3: bảng độ tin cậy đánh giá, lỗi thực tế trên trang bài học, chính sách ngưỡng hiển thị cho người học |
| Thay đổi cấu trúc cơ sở dữ liệu | – | Không có. Không migration, không xóa dữ liệu |

### Phân biệt AI thật, luật và dự phòng

| Loại | Thành phần | Ghi chú |
|---|---|---|
| **AI thật (Gemini)** | Tóm tắt JD, nhận xét bài đã chấm, Trợ lý, vector kho kiến thức | Chỉ giải thích. Số trong câu trả lời bị đối chiếu; sai thì loại. Không chạy với Gemini thật trong đợt này (xem F). |
| **Luật tất định** | Chấm bài (test case, rubric, cổng lỗi trọng yếu), mức kỹ năng, khoảng cách, readiness, lộ trình, nhắc nhở, **bảng độ tin cậy (mới)**, **lỗi thực tế (mới)**, **chống nhồi từ khóa (mới)** | Cùng dữ liệu luôn cho cùng kết quả. AI và giao diện không quyết định điểm hay mức. |
| **Dự phòng** | Khi không có khóa AI hoặc AI lỗi: tóm tắt và giải thích theo luật, Trợ lý chế độ tra cứu | Giao diện ghi rõ nguồn là luật. Kết quả chấm không phụ thuộc AI. |

---

## B. Danh sách lỗi và vấn đề đã xác nhận

### B1. Ưu tiên P1

| Mã | Vấn đề | Kiểm chứng trước khi sửa | Trạng thái |
|---|---|---|---|
| P1-1 | Ngân hàng chỉ có 1 câu cho mỗi ô kỹ năng × độ khó | Đếm `data/exam_items_v5.json`: 18 câu = 6 kỹ năng × 3 độ khó, mỗi ô 1 câu. Mức kỹ năng được ghi kèm `confidence: 0.9` cố định, không phụ thuộc bằng chứng | **Xử lý phần mã:** độ tin cậy tính theo loại bằng chứng và bảng độ tin cậy cho người học (D). **Phần nội dung chưa làm:** cần chuyên gia viết câu qua quy trình đóng góp 5.35; theo yêu cầu, không dùng AI viết câu |
| P1-2 | Bài viết đạt điểm bằng nhồi từ khóa | **Lỗi HIGH, tái hiện được.** Câu chỉ gồm khái niệm kèm một câu đệm chung chung lặp lại: STAT-3 được 70/100, WC-2 70/100, VIZ-1 100/100. Có thêm số liệu đúng: STAT-3 và WC-3 đạt **mức 3** | **Đã sửa** (C). Sau sửa, bài chỉ có từ khóa được 0–25 điểm, mức 0–1; có số liệu đúng cộng câu đệm thì STAT-3 còn mức 1, WC-3 và VIZ-3 mức 2. Ngoại lệ còn lại: DQ-3 (một câu liệt kê quy tắc kèm 3 số liệu đúng) vẫn 100, vì liệt kê quy tắc là cách trả lời hợp lệ của câu này. Mọi đáp án mẫu vẫn 100/100 trên cả 4 bộ dữ liệu |
| P1-3 | Điều kiện hoàn thành bài học và kiểm tra kiến thức | Đọc `lesson_checks.py`, `learning_tasks.py`: hoàn thành cần bài kiểm tra đạt 80 và mức đã xác nhận; trắc nghiệm tối đa mức 2; trượt chờ 6 giờ; bài trống 0 điểm; trạng thái suy ra, không lưu. Test sẵn có đều đạt | **Không có lỗi.** Gom ngưỡng về một chính sách (P3, C-08) |
| P1-4 | Đổi JD mục tiêu mà giữ năng lực đã xác thực | Giữ mức đúng (test sẵn có). **Lỗi MEDIUM mới:** đã bấm "Đổi JD mục tiêu" thì không có cách hủy; quy trình kẹt ở bước JD, trạng thái "đang làm", cho đến khi chọn một JD nào đó | **Đã sửa:** thêm "Hủy đổi mục tiêu" (E) |

### B2. Ưu tiên P2

| Mã | Vấn đề | Kiểm chứng | Trạng thái |
|---|---|---|---|
| B-02 | Giám sát rời màn hình do trình duyệt tự báo | Đúng: sự kiện rời màn hình và chặn dán đều ở phía trình duyệt | **Bổ sung tín hiệu phía máy chủ:** một lần lưu làm đáp án dài thêm từ 300 ký tự (tự lưu chạy sau 1,5 giây ngừng gõ, trang chặn dán) được ghi nhận; hiện ở kết quả, **không trừ điểm** |
| B-03 | Trạng thái trong bộ nhớ | Bản 5.34 đã có bộ đếm phiên bản và khóa theo người học. Rà mọi biến toàn cục: còn bộ chặn "mỗi người một lần chạy code" chỉ có hiệu lực trong một tiến trình | **Đã sửa:** thêm lease `code-run:<user>` trong SQLite, có hiệu lực giữa các tiến trình |
| B-04 | Chấm bài nền | Đã có từ 5.19, kiểm lại `grading_queue.recover` | **Không có lỗi** |
| — | Khôi phục khi máy chủ dừng giữa chừng | **Lỗi MEDIUM mới:** tác vụ nền chỉ tự nộp bài kiểm tra đầu vào hết giờ. Bài đánh giá tổng hợp bỏ dở quá giờ nằm mãi ở "đang làm" và chặn "Đổi JD mục tiêu" cho tới khi học viên mở lại trang | **Đã sửa:** tác vụ nền tự nộp và chấm cả bài tổng hợp; đổi mục tiêu xử lý bài hết giờ trước khi kiểm tra |
| B-05 | Sandbox Python | Thử 21 đoạn code tấn công ở chế độ `process`: đọc `.env` (đường dẫn tuyệt đối, pathlib, pandas, numpy), `os.system`, `subprocess`, socket, urllib, ctypes, `__import__`, `__subclasses__`, `eval`, `importlib`, pickle, multiprocessing, ghi tệp ra ngoài thư mục, vòng lặp vô hạn, cấp phát 2 GB. Tất cả bị chặn hoặc dừng; không tệp nào bị tạo ngoài thư mục tạm | **Không có lỗi** ở chế độ process. Chế độ Docker: BLOCKED (máy không có Docker) |
| B-06/B-07 | Host header, proxy tin cậy | Cấu hình đã có từ 5.18 nhưng **chưa có test** | **Đã kiểm trên máy chủ uvicorn thật:** Host lạ bị 400; 30 lần đăng nhập sai từ một IP sau proxy khóa đúng IP đó, IP khác vẫn đăng nhập được |
| — | Nhiều tab | **Lỗi LOW mới:** mở bài thi ở hai tab, tab cũ tự lưu sẽ ghi đè đáp án mới hơn của tab kia mà không báo | **Đã sửa:** lưu kèm thời điểm lưu đã biết; khác thì 409 và giao diện báo "bài đang mở ở tab khác" |

### B3. Ưu tiên P3

| Mã | Vấn đề | Trạng thái |
|---|---|---|
| C-01 | README cũ | **Đã cập nhật** lên 5.46.0: quy tắc chống lách mới, API mới, bảng test, cài khóa phiên bản |
| C-02 | Ghim phiên bản thư viện | So `pip freeze` với `requirements.lock`: khớp hoàn toàn với thư viện máy chủ. Thêm `requirements-dev.lock` cho 3 gói test giao diện (playwright, greenlet, pyee). Cảnh báo `httpx` → `httpx2` vẫn còn (đổi thư viện cần nhóm đồng ý) |
| C-03 | Router gắn hai lần | Đã xử lý ở 5.18; test `test_every_operation_is_documented_once` vẫn đạt. Không đổi |
| C-04 | GET có tác dụng phụ | **Đánh giá lại, giữ nguyên có lý do.** `GET /me/gap` chỉ "xác nhận lại" mức từ bài đã chấm theo quy tắc sửa 11/2026, chạy lại không đổi gì thêm, và có test ghi lại báo lỗi của người dùng ngày 12/11 yêu cầu thấy ngay khi mở trang. Tự nộp bài hết giờ khi đọc là cách xử lý trễ có chủ đích. Chuyển sang POST sẽ đổi hành vi đã được người dùng yêu cầu, nên không sửa kỳ vọng test |
| C-08 | Ngưỡng rải nhiều nơi | **Đã sửa:** `backend/assessment_policy.py` là nơi duy nhất; 4 module lấy số từ đây; `GET /me/assessment-policy` trả đúng số đang áp dụng; ngân hàng đề lệch ngưỡng thì `validate_bank` báo lỗi |

### B4. Lỗi tìm thấy trong lúc rà giao diện

| Lỗi | Mức | Sửa |
|---|---|---|
| Bảng độ tin cậy (vừa thêm) ghi SQL bỏ trống là "Trung bình", loại "Chạy code" | LOW | Mức 0 luôn là "Thấp"; bài trống hoặc không phần nào đạt có loại riêng "Bỏ trống hoặc không phần nào đạt" |
| Bảng độ tin cậy trên điện thoại phải cuộn ngang trong bảng | LOW | Dưới 640px hiện thành thẻ xếp dọc |

---

## C. Danh sách tệp đã chỉnh sửa

| Tệp | Thay đổi | Lý do |
|---|---|---|
| `backend/engine/exam_grader.py` | Chống nhồi từ khóa (`_padding_ngrams`, `_own_words`, `_explaining`); `confidence` theo loại bằng chứng; ngưỡng lấy từ chính sách; `validate_bank` kiểm ngưỡng | P1-2, P1-1, C-08 |
| `backend/assessment_reliability.py` (mới) | Bảng độ tin cậy từng kỹ năng | P1-1, nâng cấp |
| `backend/assessment_policy.py` (mới) | Mọi ngưỡng đạt và thời gian chờ | C-08 |
| `backend/mistakes.py` (mới) | Test case đã trượt theo kỹ năng, gắn vào bài học | Nâng cấp |
| `backend/career_process.py` | `cancel_goal_change`; lưu vị trí trước khi đổi; xử lý bài tổng hợp hết giờ trước khi đổi mục tiêu | P1-4, khôi phục |
| `backend/api/career_process.py` | `POST /change-goal/cancel`; `base_saved_at` | P1-4, nhiều tab |
| `backend/exam_service.py` | `write_response` dùng chung có kiểm tra tab; tín hiệu dán; `integrity` trong kết quả; lease chạy code; `saved_at` từng câu | Nhiều tab, B-02, B-03 |
| `backend/final_assessment.py` | `finish_expired`; lưu đáp án qua `write_response`; ngưỡng từ chính sách | Khôi phục, nhiều tab, C-08 |
| `backend/background.py` | Tác vụ nền nộp cả bài tổng hợp hết giờ | Khôi phục |
| `backend/api/journey.py` | `base_saved_at` cho bài tổng hợp | Nhiều tab |
| `backend/api/profiles.py`, `backend/api/reference_apis.py` | `GET /me/assessment-reliability`, `GET /me/assessment-policy` (cả đường `/api/v1` và đường gốc) | Nâng cấp, C-08 |
| `backend/lesson_checks.py`, `backend/learning_cycle_service.py` | Ngưỡng từ chính sách | C-08 |
| `backend/learning_journey.py` | Trang bài học trả thêm `mistakes` | Nâng cấp |
| `backend/config.py`, `frontend/index.html`, `frontend/login.html` | Phiên bản 5.46.0 | Phiên bản |
| `frontend/js/pages/flow.js` | Nút "Hủy đổi mục tiêu, giữ JD đang dùng" kèm hộp xác nhận | P1-4 |
| `frontend/js/pages/gap.js`, `frontend/js/pages/plan.js` | Thẻ "Độ tin cậy đánh giá" (nút riêng trong mục Khoảng cách kỹ năng) kèm ngưỡng máy chủ áp dụng | Nâng cấp |
| `frontend/js/pages/roadmap.js` | Thẻ "Lỗi bạn đã mắc ở kỹ năng này" trên trang bài học | Nâng cấp |
| `frontend/js/pages/exam.js` | Gửi `base_saved_at`; báo khi bài mở ở tab khác | Nhiều tab |
| `frontend/css/app.css` | Kiểu cho các thẻ mới, bản điện thoại | UI |
| `frontend/js/lang/en.json` | 57 chuỗi tiếng Anh mới | Song ngữ |
| `tests/test_audit_2026_11_17.py` (mới) | 97 test | Bằng chứng |
| `tests/test_proxy_and_hosts.py` (mới) | 2 test trên máy chủ uvicorn thật | B-06/B-07 |
| `README.md`, `requirements-dev.lock` (mới), `UPGRADE_REPORT.md` | Tài liệu, khóa phiên bản | C-01, C-02 |

Không sửa: cơ sở dữ liệu thật, `.env`, dữ liệu khởi tạo trong `data/`, ngân hàng đề, kỳ vọng của test cũ, đăng nhập, đăng ký, phân quyền.

---

## D. Nâng cấp đã triển khai

| Nâng cấp | Vì sao chọn | Cách làm |
|---|---|---|
| **Bảng độ tin cậy đánh giá** | Gắn thẳng vào điểm yếu lớn nhất còn lại (1 câu mỗi ô). Không thêm được câu thì ít nhất phải nói rõ mức dựa trên bao nhiêu bằng chứng | Đọc bằng chứng đã lưu, phân loại từng nguồn (chạy code, số liệu tự tính, chỉ cụm từ khóa, câu hỏi đóng, người duyệt, bỏ trống), xếp Cao / Trung bình / Thấp kèm lý do và việc nên làm. Không đổi mức |
| **Lộ trình theo lỗi thực tế** | Hai người sai khác chỗ phải thấy việc khác nhau; trước đây trang bài học chỉ nêu mục tiêu chung | Trang bài học liệt kê test case đã trượt ở bài thực hành gần nhất của đúng kỹ năng, xếp theo độ gần với mục tiêu bài học. Không đổi lịch hay mức |
| **Chính sách ngưỡng hiển thị** | Người học thấy đúng số máy chủ áp dụng; tránh lệch giữa tài liệu và mã | Một module, một API, hiện trong thẻ độ tin cậy |

Đã có sẵn nên không làm lại: lịch sử tiến bộ từng kỹ năng (5.30, `GET /me/skill-progress`). Chưa làm: hồ sơ năng lực công khai có kiểm chứng, phỏng vấn thử, trải nghiệm làm bài SQL/Python/viết mới (xem I).

---

## E. Chức năng mới

| Chức năng | Đường dẫn | Ai dùng |
|---|---|---|
| Hủy đổi mục tiêu | `POST /api/v1/career-process/change-goal/cancel`; nút ở bước Chọn JD khi đang đổi mục tiêu | Học viên |
| Độ tin cậy đánh giá | `GET /me/assessment-reliability` (cả `/api/v1`); Kế hoạch → Khoảng cách kỹ năng → nút "Độ tin cậy đánh giá" | Học viên |
| Chính sách đánh giá | `GET /me/assessment-policy`; mục "Ngưỡng đánh giá máy chủ đang áp dụng" trong thẻ trên | Học viên |
| Lỗi bạn đã mắc | Trường `mistakes` của `GET /me/journey/lessons/{id}`; thẻ trên tab Tổng quan của bài học | Học viên |
| Tín hiệu toàn vẹn bài thi | Trường `integrity` của `GET /career-process/exam/review`; dòng ghi chú ở tab Kết quả bài làm | Học viên, người duyệt |
| Bảo vệ nhiều tab | Trường `base_saved_at` khi lưu đáp án, `saved_at` từng câu khi mở bài | Tự động |

Mọi đường mới đều yêu cầu đăng nhập; test quét toàn bộ đường dẫn (`test_audit_2026_11_15.py`) vẫn đạt.

---

## F. Kết quả kiểm thử

Lệnh: `.venv/Scripts/python -m pytest -q -p no:cacheprovider` (chạy ngày 17/11/2026, khoảng 6 phút, gồm test trình duyệt Edge).

| Nhóm | Tổng | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|---:|
| Bộ test có sẵn (5.45.1) | 1196 | 1185 | 0 | 11 |
| Mới `tests/test_audit_2026_11_17.py`: chống nhồi từ khóa, đáp án mẫu (64 ca: 16 câu × 4 bộ dữ liệu), quy tắc độ tin cậy, hủy đổi mục tiêu, nhiều tab, tín hiệu dán, nộp nền bài tổng hợp, chính sách, lỗi thực tế | 97 | 97 | 0 | 0 |
| Mới: Host và proxy trên máy chủ thật | 2 | 2 | 0 | 0 |
| **Tổng** | **1295** | **1284** | **0** | **11** |

**Các test BLOCKED (bị bỏ qua) và lý do:**

| Test | Số lượng | Lý do |
|---|---:|---|
| `tests/test_ai_live.py` | 10 | Cần `CAREERADAPT_LIVE_AI=1` và gửi dữ liệu thử tới Gemini thật. Không chạy vì việc gửi dữ liệu ra dịch vụ ngoài cần người dùng đồng ý; lần chạy thật gần nhất là 01/11/2026 (9/9 đạt) |
| `tests/test_container_sandbox.py` (container thật) | 1 | Máy không cài Docker. Chế độ container vẫn được kiểm qua bản thay thế lệnh docker |

**Kiểm thử ngoài bộ test tự động (bằng chứng thật, môi trường tạm):**

| Loại | Nội dung | Kết quả |
|---|---|---|
| Bảo mật, chấm bài | 14 bài làm nhồi từ khóa trên 6 câu viết, trước và sau sửa | Trước: bài chỉ có từ khóa 25–100 điểm; có số liệu đúng thì STAT-3, WC-3, DQ-3, VIZ-3 lên mức 3. Sau: bài chỉ có từ khóa 0–25 điểm; chỉ DQ-3 có đủ số liệu đúng còn mức 3 |
| Bảo mật, sandbox | 21 đoạn code tấn công (mục B2) | Tất cả bị chặn |
| Bảo mật, hạ tầng | Host lạ, X-Forwarded-For qua proxy tin cậy, trên uvicorn thật | Đúng |
| End-to-end | Edge thật, 13 trang × 2 kích thước (1360px, 375px) trên dữ liệu tạm | 0 lỗi console, 0 yêu cầu lỗi, 0 tràn ngang |
| End-to-end | Đổi mục tiêu rồi hủy qua giao diện, ở 375px và 1360px | Về đúng "Hoàn tất", JD giữ nguyên, không lỗi |
| Edge case | Mức 0, bài bỏ trống, lưu lại đúng nội dung đã lưu, client cũ không gửi `base_saved_at`, hủy khi không có gì để hủy, tài khoản khác hủy hộ | Đều đúng như mong đợi (có test) |

---

## G. Bảo mật và dữ liệu

- **Dữ liệu thật:** không tệp nào trong `data/` bị ghi. Mọi phép thử dùng thư mục tạm qua `CAREERADAPT_DB` / `CAREERADAPT_ACCOUNTS_DB`. Bảng `meta` của `data/careeradapt.sqlite3` đọc chỉ-đọc trước và sau: giống hệt (`schema_version 2`, `ai 1`, `roadmap 1`, `runtime 1`, `fk 1`, `contrib 2`). Tệp WAL có thay đổi giờ là do máy chủ của người dùng đang chạy ở cổng 8000.
- **Không migration:** 5.46.0 không thêm bảng hay cột. Dữ liệu mới (tín hiệu dán, lease chạy code) dùng bảng sẵn có `exam_events`, `work_leases`. Máy chủ đang chạy cần khởi động lại để dùng mã mới.
- **`.env` và khóa API:** không đọc, không in. Máy chủ thử đặt `LLM_PROVIDER=mock`, nên không có dữ liệu nào gửi ra Gemini trong đợt này.
- **Tài khoản thử:** chỉ tồn tại trong cơ sở dữ liệu tạm; mật khẩu sinh ngẫu nhiên, lưu trong thư mục tạm, không nằm trong mã hay báo cáo.
- **Đăng nhập, đăng ký, phân quyền:** không đổi. Đường mới đều cần đăng nhập và chỉ đọc dữ liệu của chính tài khoản (có test tài khoản khác nhận "Chưa có", hủy hộ bị 409).
- **Điểm và mức:** không có thay đổi nào để AI hay giao diện quyết định. Bảng độ tin cậy, lỗi thực tế, tín hiệu dán đều chỉ đọc và ghi rõ "không ảnh hưởng điểm hay mức".
- **Câu hỏi:** không thêm câu nào vào ngân hàng chính thức, không dùng AI sinh câu.

---

## H. UI/UX

- Rà 13 trang của học viên (Bảng điều khiển, Quy trình, 7 mục Kế hoạch, Học liệu, Kiểm tra kiến thức, Hồ sơ, Báo cáo năng lực) ở 1360px và 375px bằng Edge thật: không lỗi script, không yêu cầu lỗi, không tràn ngang, không lộ mã thô (chữ `ROW_NUMBER` xuất hiện là tên hàm SQL trong tiêu đề học liệu).
- Phần mới theo đúng bố cục 5.45: thẻ độ tin cậy nằm sau nút "Độ tin cậy đánh giá" (phần phụ), không đẩy biểu đồ chính xuống.
- Đã xem ảnh chụp và sửa 2 điểm (mục B4). Nhãn "Gần với bài này" không còn kéo giãn hết chiều ngang trên điện thoại.
- Không dùng style inline ở trang đăng nhập (trang này không đổi); mọi kiểu mới nằm trong `app.css` và dùng biến màu nên đúng cả giao diện tối.
- Song ngữ: 57 chuỗi mới có bản tiếng Anh; `tests/test_i18n.py` đạt 38/38.

---

## I. Hướng tiếp theo

| Ưu tiên | Việc | Cần gì |
|---|---|---|
| 1 | Thêm 2–3 câu cho mỗi ô kỹ năng × độ khó qua quy trình đóng góp có duyệt (5.35) | Chuyên gia viết câu và người duyệt; không dùng AI. Bảng độ tin cậy sẽ tự lên mức "Cao" khi có thêm nguồn |
| 2 | Chạy `tests/test_ai_live.py` với khóa thật | Người dùng đồng ý gửi dữ liệu thử tới Gemini |
| 3 | Chạy sandbox Docker thật | Máy có Docker; test container tự chạy khi có |
| 4 | Người đọc lại phần lập luận của bài viết được chấm bằng cụm từ khóa | Quy trình duyệt; bảng độ tin cậy đã đánh dấu các bài này |
| 5 | Hồ sơ năng lực có thể kiểm chứng (liên kết công khai chỉ đọc) | Quyết định của nhóm về quyền riêng tư |
| 6 | Phỏng vấn thử (chỉ luyện tập, không ghi bằng chứng) | Kịch bản câu hỏi do người viết |

Giới hạn còn lại: luật chống nhồi từ khóa chặn câu đệm lặp, chép đề và danh sách từ khóa; một người viết nhiều câu khác nhau trông như lời giải thích vẫn qua được phần khái niệm. Đó là giới hạn của chấm tất định với văn bản, nên phần này được đánh dấu "kiểm bằng cụm từ khóa" trong bảng độ tin cậy.

---

## J. Hướng dẫn chạy

```bash
pip install -r requirements.lock
```

```bash
python run.py
```

Mở `http://127.0.0.1:8000/login`. Máy chủ đang chạy cần khởi động lại để dùng bản 5.46.0; không có migration.

Chạy toàn bộ test (cần `pip install -r requirements-dev.lock` cho test trình duyệt):

```bash
python -m pytest -q -p no:cacheprovider
```

Chạy riêng các test của đợt này:

```bash
python -m pytest -q tests/test_audit_2026_11_17.py tests/test_proxy_and_hosts.py
```

Kiểm thử giao diện thủ công trên dữ liệu tạm, không đụng `data/`:

```bash
python scripts/dev_server_isolated.py
```
