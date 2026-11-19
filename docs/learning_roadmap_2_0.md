# Learning Roadmap 2.0: khảo sát, thiết kế và báo cáo

Ngày: 11/11/2026. Sao lưu trước khi sửa: `CareerAdapt_AI_backup_truoc_roadmap_2_0_20261111` (cùng cấp thư mục dự án).

## Phase 1. Khảo sát hệ thống hiện tại

Kiến trúc: FastAPI + SQLite (`backend/database.py`, migration chỉ thêm, có sao lưu tệp trước khi nâng cấp), frontend ES module thuần không có bước build (`frontend/js`), router hash trong `frontend/js/main.js`, i18n hiển thị qua `translate.js` + `frontend/js/lang/en.json`. Trạng thái lộ trình của người học nằm trong `learner_state` (JSON: `roadmap.activity_plan`, `roadmap.activity_progress`), lịch sử ở các bảng `progress_records`, `micro_assessments`, `learning_checkins`, `skill_evidence`, `roadmap_versions`.

### 1. Đã có và đang hoạt động

| Chức năng | Nơi xử lý |
| --- | --- |
| Lập lộ trình từ mức đã xác thực, trọng số JD, quỹ giờ và hạn chót; ưu tiên khoảng cách lớn, thêm học phần nền khi thiếu bằng chứng, không dùng mức tự khai | `backend/api/roadmaps.py` `build_roadmap`, `backend/engine/roadmap_planner.py`, `dag_scheduler.py` |
| Xếp lịch theo tuần, tách học phần dài qua nhiều tuần, ghi lý do khi không xếp được | `dag_scheduler.py` |
| Cập nhật tiến độ thủ công (Chưa bắt đầu / Đang học / Đã học xong) | `PATCH /activities/{id}/progress` |
| Bài kiểm tra hoàn thành học phần (lesson check) rút từ ngân hàng câu hỏi, ngưỡng 80, chấm phía máy chủ, chỉ bài đạt mới thành bằng chứng | `backend/lesson_checks.py`, `POST /activities/{id}/knowledge-check`, `POST /micro-tests/{id}/submissions` |
| Trạng thái học phần suy ra (không lưu): NOT_STARTED, IN_PROGRESS, PENDING_ASSESSMENT, VERIFIED, NEEDS_REVIEW | `lesson_checks.task_state` |
| Lịch kiểm tra lại (check-in), nhắc nhở, mini-test ôn tập; mini-test không bao giờ hạ mức | `backend/learning_cycle_service.py`, `backend/api/learning_cycle.py` |
| Bài kiểm tra Career Adapt (một lần mỗi quy trình), bàn làm bài SQL/Python/báo cáo, chấm bằng test case, chống gian lận (rời màn hình 3 lần tự nộp, chặn sao chép) | `backend/exam_service.py`, `backend/engine/exam_grader.py`, `frontend/js/pages/exam.js`, `workspaces.js` |
| Báo cáo năng lực in được | `frontend/js/pages/report.js` |

### 2. Đang hoạt động nhưng cần cải thiện

- Trang lộ trình hiển thị toàn bộ học phần của mọi tuần trên một trang dài; chi tiết học phần là hộp thoại nhỏ.
- Thời gian học chỉ là số giờ người học tự nhập, không có đồng hồ.
- Lịch ôn tập được tạo ngay khi đánh dấu "đã học xong", trước khi qua bài kiểm tra, và có thể đổi bất cứ lúc nào. Chu kỳ có sẵn là 3, 7, 14, 30 ngày.
- Trạng thái ôn tập và trạng thái học tập không tách rời trên giao diện.

### 3. Chưa tồn tại

- Trang tuần, chủ đề và trang chi tiết bài học riêng.
- Đồng hồ học có phiên, tạm dừng, khôi phục, lưu ở máy chủ.
- Chọn chu kỳ ôn tập (1, 3, 7, 14 ngày) một lần khi bắt đầu học và khóa sau đó.
- Bài thực hành gắn với từng bài học.
- Bài đánh giá tổng hợp cuối lộ trình và trang hoàn thành.

### 4. File và module cần chỉnh

`backend/database.py` (bảng mới), `backend/lesson_checks.py`, `backend/api/learning_tasks.py`, `backend/api/learning_cycle.py`, `backend/api/roadmaps.py`, `backend/career_process.py` (reset), `backend/ai_service/guardrails.py` (khóa trợ lý khi đang thi), `frontend/js/main.js`, `frontend/js/pages/plan.js`, `frontend/js/pages/roadmap.js`, `frontend/js/pages/exam.js`, `frontend/js/workspaces.js`, `frontend/css/app.css`. Thêm mới: `backend/learning_journey.py`, `backend/final_assessment.py`, `backend/api/journey.py`, `data/practice_items_v1.json`.

### 5. Rủi ro

- Đổi thời điểm bắt đầu lịch ôn tập làm thay đổi kỳ vọng của 3 test cũ (đã ghi lại ở phần quyết định).
- Bàn làm bài và đồng hồ thi đang gắn cứng với API của bài Career Adapt; phải tham số hóa mà không đổi hành vi cũ.
- Reset quy trình và quyền xóa dữ liệu phải bao gồm các bảng mới.
- Khóa trợ lý AI phải tính cả bài đánh giá cuối.

## Phase 2. Thiết kế

### Dữ liệu (migration `roadmap_schema_version` = 1, sao lưu `*.pre-roadmap1.bak` trước khi tạo)

| Bảng | Mục đích |
| --- | --- |
| `lesson_plans` | Chu kỳ ôn tập người học chọn khi bắt đầu bài lần đầu. Một dòng cho mỗi người học và bài học, không sửa được qua API. |
| `study_sessions` | Từng phiên học: RUNNING, PAUSED, ENDED; thời gian cộng dồn do máy chủ tính. Chỉ một phiên RUNNING cho mỗi người dùng (unique index), một phiên mở cho mỗi bài. |
| `practice_attempts` | Lần nộp bài thực hành của bài học (không phải bằng chứng năng lực). |
| `final_attempts` | Bài đánh giá tổng hợp cuối lộ trình; câu trả lời và sự kiện dùng lại `exam_responses`, `exam_events`. |

Thời gian học và kết quả đánh giá là hai loại dữ liệu riêng: thời gian nằm ở `study_sessions`, kết quả ở `micro_assessments`, `final_attempts`, `skill_evidence`.

### Trạng thái bài học (hai trường tách biệt)

- `learning_state`: NOT_STARTED, STUDYING, PAUSED, PENDING_CHECK, NEEDS_REVIEW (chưa đạt bài kiểm tra hoàn thành), COMPLETED (đã đạt).
- `review_state`: NONE, SCHEDULED, DUE, PASSED, RELEARN (ôn tập định kỳ chưa đạt).

### Quyết định nghiệp vụ

1. Lịch ôn tập bắt đầu đếm từ ngày đạt bài kiểm tra hoàn thành, theo chu kỳ đã chốt khi bắt đầu học. Đánh dấu "đã học xong" không còn tạo lịch ôn tập. Ba test cũ mô tả quy tắc cũ được cập nhật theo yêu cầu mới.
2. Chu kỳ ôn tập đã chốt không sửa được (API trả 409). Bài cũ chưa có chu kỳ chốt vẫn dùng cơ chế cũ.
3. Đồng hồ: máy chủ ghi mốc thời gian, trình duyệt chỉ gửi nhịp (heartbeat) mỗi 60 giây. Không có nhịp quá 5 phút thì phiên tự tạm dừng tại nhịp cuối (mất kết nối, ngủ máy), người học tiếp tục lại được. Một đoạn chạy liên tục tối đa 4 giờ. Nhiều tab dùng chung một phiên nên không tính trùng.
4. Ôn tập định kỳ dùng lại mini-test hiện có: câu hỏi tránh câu đã gặp gần đây, không bao giờ hạ mức. Quy tắc cũ "đạt có thể xác nhận thêm tối đa một bậc, không vượt mức của bài học" được giữ nguyên.
5. Bài đánh giá cuối dùng ngân hàng đề Career Adapt ở độ khó bằng mức JD yêu cầu, ưu tiên biến thể dữ liệu chưa làm. Chấm hoàn toàn bằng test case. Đạt khi: điểm tổng từ 70, mọi kỹ năng cốt lõi đạt mức JD, tỷ lệ trọng số kỹ năng đạt mức JD từ 80%, không bỏ trống bài nào, không mắc lỗi trọng yếu. Kết quả được lưu làm bằng chứng; mức chỉ được nâng, không hạ.

## Báo cáo hoàn thành (phiên bản 5.15.0)

### 1. Chức năng cũ được bảo toàn

- Công thức khoảng cách kỹ năng, trọng số JD, thang mức 0-3 và cách lập lộ trình không đổi. Lộ trình vẫn chỉ dùng mức đã xác thực, không dùng mức tự khai.
- Bài kiểm tra Career Adapt, chấm điểm, bằng chứng kỹ năng, mini-test và nhắc nhở giữ nguyên quy tắc. API cũ (`PATCH /activities/{id}/progress`, `POST /activities/{id}/knowledge-check`, `/me/learning-tasks`, `/micro-tests/...`) vẫn hoạt động.
- Đánh dấu học xong, thời gian học và ôn tập không bao giờ nâng hay hạ mức năng lực. Kết quả chưa đạt không xóa thời gian học hay lịch sử.
- Reset quy trình và quyền xóa dữ liệu đã bao gồm các bảng mới.

### 2. Chức năng mới

| Phần | Nội dung |
| --- | --- |
| Tổng quan lộ trình | Bốn thông tin chính: ngày dự kiến hoàn thành, tiến độ (số bài đạt kiểm tra), số bài đang chờ kiểm tra lại, bài học tiếp theo. Tuần hiển thị dạng thẻ, bấm vào để mở trang tuần. Thanh phiên học đang chạy. |
| Trang tuần | Mục tiêu tuần, số chủ đề, số bài, tiến độ; chủ đề (theo kỹ năng) mở rộng/thu gọn; mỗi bài có thời lượng, thời gian đã học, ngày kiểm tra lại, trạng thái học và trạng thái ôn tập riêng. |
| Trang bài học | 5 tab: Tổng quan, Nội dung (từng phần theo mục tiêu), Học liệu (nguồn đã duyệt, loại, trình độ, mô tả), Thực hành, Tiến độ và ôn tập. Cột bên: đồng hồ học, kiểm tra hoàn thành, ôn tập định kỳ. |
| Đồng hồ học | Bắt đầu, tạm dừng, tiếp tục, kết thúc; thời gian do máy chủ tính; tải lại trang, nhiều tab, đăng nhập lại không mất hay nhân đôi thời gian; mất kết nối thì tự tạm dừng tại nhịp cuối và tiếp tục lại được; một đồng hồ chạy cho mỗi tài khoản. |
| Lịch ôn tập | Chọn 1, 3, 7, 14 ngày hoặc tùy chỉnh (1-90) khi bắt đầu bài lần đầu, sau đó khóa. Ngày ôn tập tính từ lúc đạt bài kiểm tra hoàn thành. Ôn tập chưa đạt chuyển sang "Cần ôn tập lại", chỉ ra phần cần củng cố và cho đặt lại lịch. |
| Bài thực hành | 13 bài (một bài cho mỗi bài học), chạy SQL/Python trên dữ liệu mẫu bằng môi trường sandbox sẵn có, chấm bằng test case. Không dùng câu của bài kiểm tra, không phải bằng chứng năng lực. |
| Bài đánh giá tổng hợp | Mở khi mọi bài học đạt bài kiểm tra hoàn thành. Mỗi kỹ năng JD một bài thực hành ở độ khó của mức JD, có giới hạn thời gian, chống gian lận như bài Career Adapt, khóa trợ lý AI khi đang làm. Đạt khi đủ 5 điều kiện. Trang kết quả có tổng thời gian học, số bài hoàn thành, mức khi bắt đầu lộ trình, trước và sau bài này, khoảng cách còn lại, bài cần học lại, liên kết báo cáo năng lực. Chưa đạt thì làm lại sau 24 giờ. |

### 3. File tạo mới hoặc chỉnh sửa

Tạo mới: `backend/learning_journey.py`, `backend/practice.py`, `backend/final_assessment.py`, `backend/api/journey.py`, `data/practice_items_v1.json`, `tests/test_learning_roadmap_2.py`, tài liệu này.

Chỉnh sửa: `backend/database.py`, `backend/career_process.py`, `backend/exam_service.py` (tách hàm chạy code dùng chung), `backend/api/roadmaps.py`, `backend/api/learning_cycle.py`, `backend/api/learning_tasks.py`, `backend/ai_service/guardrails.py`, `backend/main.py`, `backend/config.py`, `frontend/js/pages/roadmap.js` (viết lại), `frontend/js/pages/exam.js`, `frontend/js/workspaces.js`, `frontend/js/pages/plan.js`, `frontend/js/main.js`, `frontend/js/core.js`, `frontend/js/icons.js`, `frontend/css/app.css`, `frontend/js/lang/en.json`, `scripts/i18n_extract.py`, `frontend/index.html`, `frontend/landing.html`, 3 test cũ (xem mục 8).

### 4. Migration

`roadmap_schema_version` 1: tạo 4 bảng mới `lesson_plans`, `study_sessions`, `practice_attempts`, `final_attempts` và chỉ mục duy nhất. Không sửa bảng hay dòng cũ. Trước khi tạo, tệp database được sao lưu thành `data/careeradapt.sqlite3.pre-roadmap1.bak`.

Lưu ý: migration này đã chạy trên database thật trong lúc kiểm tra (khi import module backend để kiểm tra cú pháp). Bản sao lưu đã được tạo trước, 4 bảng mới đang trống, không dòng cũ nào bị đổi. Đây đúng là việc ứng dụng sẽ làm ở lần khởi động tiếp theo.

### 5. API mới hoặc thay đổi

Mới: `GET /me/journey`, `GET /me/journey/weeks/{n}`, `GET /me/journey/lessons/{activity_id}`, `GET /me/study/current`, `POST /me/study/start`, `POST /me/study/{session_id}` (pause, resume, end, heartbeat), `POST /me/practice/{exercise_id}/run`, `POST /me/practice/{exercise_id}/check`, `POST /activities/{id}/review/reschedule`, `GET /me/final-assessment`, `POST /me/final-assessment/start`, `PUT /me/final-assessment/responses/{question_id}`, `POST /me/final-assessment/run`, `POST /me/final-assessment/events`, `POST /me/final-assessment/submit`, `GET /me/final-assessment/{attempt_id}/review`.

Thay đổi hành vi: `PATCH /activities/{id}/progress` với COMPLETED không còn tạo lịch ôn tập; `POST /micro-tests/{id}/submissions` của bài kiểm tra hoàn thành đạt thì tạo lịch ôn tập (trả thêm `review_due_at`); `PATCH /activities/{id}/schedule` SET_CYCLE trả 409 khi chu kỳ đã khóa; `POST /activities/{id}/knowledge-check` kết thúc phiên học đang mở của bài đó; `/assistant/status` khóa trợ lý khi đang làm bài đánh giá tổng hợp.

### 6. Kết quả kiểm thử

Toàn bộ: **888 passed, 10 skipped** (10 test bỏ qua là `test_ai_live.py`, cần khóa Gemini thật, như trước). Trước khi sửa: 867 passed, 10 skipped, không có lỗi sẵn.

| Nhóm | Test tự động (`tests/test_learning_roadmap_2.py`, 21 test) | Kiểm tra trên trình duyệt (bản sao dữ liệu) |
| --- | --- | --- |
| A. Đồng hồ | Bắt đầu, tạm dừng, tiếp tục, kết thúc; tải lại và tab thứ hai không nhân đôi; mất kết nối tự dừng tại nhịp cuối rồi tiếp tục; một đồng hồ mỗi tài khoản; người khác không thao tác được; lịch sử còn sau đăng nhập lại; giới hạn 4 giờ | Chọn chu kỳ, bắt đầu, tạm dừng giữ nguyên giờ, tiếp tục, tải lại trang vẫn chạy, kết thúc có hộp xác nhận và lưu giờ |
| B. Tiến độ bài học | Trạng thái theo phiên học và bài kiểm tra; đủ giờ không tự hoàn thành; kiểm tra chưa đạt giữ thời gian, lịch sử; làm lại đạt; bài bị khóa tiên quyết không bắt đầu được; tổng quan và tuần đúng số liệu | Trang tổng quan, trang tuần, trang bài học, chuyển tab |
| C. Ôn tập | Lịch tính từ ngày đạt với chu kỳ đã khóa; đến hạn mở bài ôn tập; chưa đạt không hạ mức, chuyển "Cần ôn tập lại", đặt lại lịch; đạt chuyển "Ôn tập đạt" | Hiển thị chu kỳ đã chốt |
| D. Đánh giá tổng hợp | Chưa xong bài học thì không mở; mở khi xong; một bài mỗi kỹ năng ở độ khó JD; khóa trợ lý; đạt ghi bằng chứng và trang hoàn thành; chưa đạt giữ mức, chỉ bài cần học lại, chờ 24 giờ; phán quyết cần đủ mọi điều kiện, không chỉ điểm tổng | Trang giới thiệu bài đánh giá khi còn bài chưa xong |
| E. Hồi quy | Toàn bộ test cũ: quy trình Career Adapt, JD, đánh giá, khoảng cách kỹ năng, lộ trình, kiểm tra kiến thức, bảng điều khiển, xác thực, i18n | Sáng/tối, tiếng Việt/tiếng Anh, 1280px và 375px không cuộn ngang |
| Cá nhân hóa | Hai người cùng mục tiêu, mức SQL/Python ngược nhau, nhận lộ trình khác nhau | |
| Thực hành | Chấm bằng test case, không thành bằng chứng; mọi bài thực hành nhận đáp án đúng | Chạy SQL và chấm 100/100 |

### 7. Lỗi phát hiện và cách khắc phục

- Huy hiệu trạng thái đồng hồ hiện mã thô "RUNNING": thêm RUNNING và ENDED vào bảng trạng thái dùng chung (`core.js`).
- Thanh tab bài học bị cuộn ngang ở bề rộng laptop: cho tab xuống dòng.
- Vài cụm số liệu nối bằng " · " chưa được dịch ở chế độ tiếng Anh: thêm bản dịch theo từng mảnh.
- Lỗi trong test (không phải lỗi sản phẩm): hai test đầu tiên không gửi nhịp nên máy chủ tạm dừng phiên đúng quy tắc; test đã được sửa để gửi nhịp như trang thật.

### 8. Test cũ được cập nhật theo quy tắc mới

Ba test mô tả quy tắc cũ "đánh dấu học xong thì tạo lịch ôn tập" được đổi kỳ vọng sang quy tắc mới mà yêu cầu nêu rõ: `test_v4_learning_cycle.py::test_marking_an_activity_studied_does_not_start_the_review_clock`, `test_learning_tasks.py::test_the_old_progress_api_still_completes_and_leaves_the_check_pending`, `test_v5_process.py::test_progress_updates_after_completion_without_changing_levels`. Việc tạo lịch sau khi đạt được kiểm tra ở test mới.

### 9. Chưa hoàn thành

- (Đã làm ở 5.16.0, xem mục bổ sung bên dưới.) Lộ trình tự lập lại khi mức đã xác thực thay đổi.
- Nội dung bài học là các phần theo mục tiêu cùng học liệu đã duyệt; hệ thống chưa có bài giảng viết riêng hay video.
- Excel chưa phải kỹ năng có bài đo nên bài đánh giá tổng hợp không có phần Excel.
- Chưa có Skill Passport riêng; trang kết quả dẫn tới báo cáo năng lực in được sẵn có, báo cáo đó chưa có mục bài đánh giá tổng hợp.
- Vòng tiến độ trên Bảng điều khiển vẫn dùng phần trăm tiến độ cũ, chưa dùng số bài đạt kiểm tra.

### 10. Cần tiếp tục xử lý

- Giảng viên hoặc quản trị viên rà lại 13 bài thực hành và quy tắc đạt của bài đánh giá tổng hợp (70 điểm, 80% trọng số, chờ 24 giờ).
- Cân nhắc ôn tập giãn cách nhiều lần (sau khi đạt, lên lịch lần tiếp theo dài hơn).

## Hướng dẫn chạy và kiểm tra

1. Khởi động như thường lệ (`start.bat` hoặc `python run.py`). Lần đầu, ứng dụng tự tạo các bảng mới (đã sao lưu trước).
2. Mở trình duyệt, nhấn Ctrl+F5, vào Kế hoạch Career Adapt > Lộ trình học tập.
3. Bấm một tuần, mở một bài học, bấm "Bắt đầu học", chọn thời gian kiểm tra lại, thử Tạm dừng, Tiếp tục, tải lại trang, Kết thúc phiên.
4. Tab Thực hành: viết truy vấn, bấm "Chạy truy vấn" rồi "Kiểm tra bài làm".
5. "Làm bài kiểm tra hoàn thành": đạt thì bài chuyển "Đã hoàn thành" và có ngày ôn tập.
6. Khi mọi bài đã hoàn thành, mục "Bài đánh giá tổng hợp" trên trang tổng quan mở.
7. Chạy test: `.venv\Scripts\python.exe -m pytest tests -q` (riêng phần mới: `tests\test_learning_roadmap_2.py`).

## Bổ sung 5.16.0: lập lại lộ trình khi mức đã xác thực thay đổi

Sao lưu trước khi sửa: `CareerAdapt_AI_backup_truoc_lap_lai_lo_trinh_20261111`.

- Tự động: sau bài kiểm tra hoàn thành, bài ôn tập hoặc bài đánh giá tổng hợp làm thay đổi mức đã xác thực, hệ thống so danh sách bài còn cần với danh sách bài còn lại. Chỉ khi hai danh sách khác nhau (có bài mới cần học hoặc bài không còn cần) thì lộ trình mới được xếp lại, nên một lần đạt bình thường không làm xáo trộn các tuần.
- Thủ công: nút "Cập nhật lộ trình" trên trang tổng quan (`POST /me/journey/replan`) xếp lại các bài còn lại từ hôm nay.
- Bài đã đạt kiểm tra được giữ trong lộ trình ("Đã hoàn thành ở phiên bản trước"), vẫn tính tiến độ và giữ lịch ôn tập. Bài không còn cần được liệt kê kèm lý do; phiên học đang mở của bài đó được kết thúc. Thời gian học, kết quả, chu kỳ ôn tập và phiên bản lộ trình cũ không bị xóa.
- Chỉ bài đã **đạt** kiểm tra mới được coi là xong khi xếp lại; bài mới đánh dấu "đã học" mà chưa đạt vẫn được xếp lịch.
- Test mới: 3 test trong `tests/test_learning_roadmap_2.py` (mục F). Toàn bộ: 891 passed, 10 skipped.

## Sửa lỗi 5.16.2: hoàn thành lộ trình nhưng vẫn còn khoảng cách kỹ năng

Nguyên nhân: quy tắc "mỗi bài kiểm tra ngắn chỉ nâng tối đa một bậc" (viết cho bài ôn tập) cũng áp vào bài kiểm tra hoàn thành. Người học ở mức 0 làm bài học mức 2, đạt 100/100 nhưng chỉ được mức 1; bài học vẫn được tính là hoàn thành nên lộ trình báo xong trong khi khoảng cách còn. Test cũ không phát hiện vì luôn bắt đầu từ mức 1.

Sửa:
- Bài kiểm tra hoàn thành có câu ở mọi mức tới mức của bài, nên xác nhận được mức đó ngay (không vượt mức của bài, không hạ mức). Bài ôn tập định kỳ vẫn giữ giới hạn một bậc.
- Bài học chỉ hoàn thành khi đạt ngưỡng điểm **và** đạt mức của bài. Điểm đủ nhưng các câu ở mức của bài chưa đủ đúng thì tính là chưa đạt và được làm lại.
- Bài đã "đạt" theo quy tắc cũ mà mức còn thiếu hiện "Cần xác nhận mức" và cho làm "bài kiểm tra xác nhận". Kết quả cũ không bị sửa; bài đánh giá tổng hợp chờ tới khi xác nhận xong.
- Test mới: 3 test trong `tests/test_learning_roadmap_2.py` (mục G).

## Bổ sung 5.16.3: tự xác nhận lại mức từ bài đã chấm

Bản 5.16.2 không đổi kết quả cũ nên khoảng cách vẫn còn cho tới khi người học làm bài xác nhận. Nay, khi mở trang Khoảng cách kỹ năng hoặc Lộ trình, hệ thống đọc lại câu trả lời **đã chấm** của bài kiểm tra hoàn thành đạt theo quy tắc cũ. Nếu các câu đó chứng minh đủ mức của bài (cùng cách ước lượng như bài mới), mức được nâng lên. Thao tác ghi thêm một dòng bằng chứng ghi rõ "Tính lại theo quy tắc đã sửa" và một sự kiện lịch sử, rồi kiểm tra lại lộ trình. Kết quả bài cũ không bị chấm lại hay sửa; mức không bao giờ hạ; chạy lại không tạo thêm gì. Nếu câu trả lời cũ chưa chứng minh đủ mức thì vẫn yêu cầu bài kiểm tra xác nhận. Test: 895 passed, 10 skipped.
