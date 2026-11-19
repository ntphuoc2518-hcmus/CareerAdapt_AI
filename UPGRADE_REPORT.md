# Báo cáo kiểm toán và nâng cấp CareerAdapt AI

Ngày: 04/11/2026 · Phiên bản sau nâng cấp: **5.9.0** (`backend/config.py`, `frontend/index.html`).

Thư mục dự án không phải là repository Git, nên không có `git status` để đối chiếu. Thay vào đó, mã nguồn được sao lưu vào các thư mục cùng cấp với dự án trước mỗi đợt thay đổi. Bản sao lưu trước đợt kiểm toán này là `CareerAdapt_AI_backup_truoc_kiem_toan_20261104`, gồm backend, frontend, tests, scripts và docs. Thư mục `data/` (database thật) không bị đọc ghi hay sửa trong đợt này; bộ test chạy trên database trong bộ nhớ (`:memory:`).

## 1. Tổng quan chất lượng ban đầu

| Hạng mục | Trạng thái trước kiểm toán |
| --- | --- |
| Bộ test | **781 passed, 10 skipped**. 10 test bỏ qua nằm trong `test_ai_live.py`, gọi Gemini thật. Có 22 cảnh báo deprecation. |
| Kiến trúc | FastAPI + SQLite. Frontend dùng ES module thuần, không có bước build. Router hash `#/…` trong `frontend/js/main.js`; mỗi trang nằm trong `frontend/js/pages/`. |
| Xác thực | Cookie phiên `HttpOnly` + `SameSite=Strict`, CSRF double-submit, giới hạn đăng nhập sai theo email + IP. Token demo chỉ hoạt động khi chạy test hoặc khi bật rõ `CAREERADAPT_DEMO_AUTH` ngoài production. |
| Phân quyền dữ liệu | Mọi API có ID trong đường dẫn đều kiểm tra chủ sở hữu (trả 404 hoặc 403 kèm ghi nhật ký bảo mật). |
| Chấm điểm | Câu trống tính 0. AI không đổi được điểm. Trích dẫn giả bị loại. AI trả sai cấu trúc thì bài được giữ để chấm lại, số lần chấm lại có giới hạn. Có chống nộp trùng. SQL và Python chạy trong sandbox ngoài tiến trình API. Phần này đã được test rất kỹ. |
| XSS | Dữ liệu chèn vào HTML đều qua `esc()`. Markdown của học viên đi qua DOMPurify với danh sách thuộc tính chặt. CSP chỉ cho phép `'self'`. |
| Hiệu năng | Các API đọc chính phản hồi trong 3–6 ms (median, đo bằng TestClient trên DB trong bộ nhớ). |

## 2. Lỗi phát hiện trong đợt kiểm toán

| Mã | Mức | Mô tả | Cách phát hiện |
| --- | --- | --- | --- |
| F1 | P1 | Test Center: gửi đáp án dạng danh sách hoặc đối tượng cho câu chọn một đáp án làm máy chủ lỗi **500** (`TypeError: unhashable type`). | Probe dữ liệu sai kiểu |
| F2 | P2 | Test Center: câu dạng số nhận cả đối tượng, danh sách và `true/false` rồi lưu lại. Không sai điểm (đều chấm 0), nhưng lưu dữ liệu rác và không báo lỗi cho người dùng. | Probe dữ liệu sai kiểu |
| F3 | P1 nghiệp vụ | `PATCH /activities/{id}/progress` mặc định `status = COMPLETED`, `progress_percent = 100`. Một body rỗng hoặc sai định dạng âm thầm đánh dấu học phần **hoàn thành 100%** và lên lịch kiểm tra lại. Gửi `{"status": "IN_PROGRESS"}` không kèm phần trăm cũng thành hoàn thành. Mức kỹ năng không bị cộng, vì chỉ bài kiểm tra đạt mới cộng, nhưng tiến độ bị ghi sai. | Fuzz các API ghi dữ liệu |
| F4 | P2 | API admin tạo/sửa học phần không giới hạn `target_level`, `estimated_hours` (có thể âm hoặc 0, trong khi bộ xếp lịch chia theo giờ), không kiểm tra `target_skill` có trong danh mục, và không giới hạn độ dài các trường. | Đọc mã |
| F5 | P3 | Hằng số mã lỗi đã lỗi thời (`HTTP_422_UNPROCESSABLE_ENTITY`, `HTTP_413_REQUEST_ENTITY_TOO_LARGE`) sinh 21 cảnh báo deprecation, sẽ thành lỗi khi nâng cấp Starlette. | Kết quả chạy test |

Không phát hiện: lỗ hổng truy cập chéo giữa tài khoản, SQL injection (mọi truy vấn đều dùng tham số; sandbox chỉ đọc), XSS, liên kết chết, hay nút giao diện không có hàm xử lý. Việc kiểm tra liên kết và nút được làm bằng một script quét tĩnh mọi `href="#/…"` và `data-act` / `data-form`.

## 3. Lỗi đã sửa

- **F1, F2** – `backend/api/test_center.py`: câu chọn một đáp án chỉ nhận chuỗi thuộc danh sách lựa chọn; câu số chỉ nhận số hoặc chuỗi tối đa 40 ký tự. Sai kiểu trả **422** kèm thông báo rõ ràng.
- **F3** – `backend/api/roadmaps.py`:
  - `status` trở thành bắt buộc.
  - Khi thiếu `progress_percent`, phần trăm được suy ra từ trạng thái: hoàn thành là 100, chưa bắt đầu là 0, đang học/tạm dừng giữ phần trăm đã lưu (tối đa 99).
  - Frontend và luồng "Hoàn thành → bài kiểm tra kiến thức" luôn gửi đủ trường, nên không bị ảnh hưởng.
- **F4** – `backend/api/admin_crud.py`:
  - Mã học phần phải 2–60 ký tự, gồm chữ, số, `_` hoặc `-` (cả 10 học phần hiện có đều hợp lệ).
  - `target_level` từ 1 đến 3; giờ học lớn hơn 0 và tối đa 200; các danh sách và chuỗi có giới hạn độ dài.
  - `target_skill` phải có trong danh mục kỹ năng.
- **F5** – thay hằng số lỗi thời bằng mã số tương ứng (422, 413) ở 6 file backend. Hành vi giữ nguyên; số cảnh báo giảm từ 22 xuống 1. Cảnh báo còn lại nằm trong thư viện `fastapi.testclient`.

## 4. Chức năng đã thêm

- **Báo cáo năng lực** (`#/report`, `frontend/js/pages/report.js`):
  - Gồm một trang tổng hợp: kết quả bài kiểm tra năng lực; độ phủ và mức đáp ứng mục tiêu (kèm lý do nếu đang khóa); bảng kỹ năng (tự khai, đã xác thực, mục tiêu, còn thiếu, trọng số, bằng chứng, trạng thái thành thạo); tiến độ lộ trình và 5 việc tiếp theo.
  - Nút "In hoặc lưu PDF" dùng chức năng in của trình duyệt. CSS in ẩn thanh bên, thanh trên, các nút và nền chuyển động.
  - Chỉ dùng dữ liệu từ `/me/gap`, `/me/skill-mastery`, `/career-process/exam/review`, `/me/roadmap` và `/me/learning-tasks`; không tự tính mức hay điểm.
  - Mở từ nút "Báo cáo năng lực" ở tab Khoảng cách kỹ năng.
  - Trước đây nút "Xuất báo cáo" bị bỏ ở v5.5.1 vì thiếu dữ liệu; giờ dữ liệu đã đủ.

## 5. Chức năng đã nâng cấp trong chuỗi phiên bản 5.5 → 5.9

| Phiên bản | Nội dung |
| --- | --- |
| 5.5.0 – 5.5.1 | Giao diện navy/xanh kiểu SaaS theo mock-up của nhóm; bảng điều khiển dựng từ API thật. |
| 5.6.0 – 5.6.1 | Lộ trình học tập: bấm "Hoàn thành" thì mở bài kiểm tra kiến thức; trạng thái học phần được suy ra, không lưu cứng; sửa lỗi câu sắp xếp chưa đổi thứ tự bị tính là đã trả lời. |
| 5.7.0 | Nền gradient xanh chuyển động (`frontend/css/ambient.css`), có hỗ trợ giảm chuyển động, tương phản cao và in. |
| 5.7.1 | Thiết kế lại tab Kết quả bài làm. |
| 5.8.0 | Thiết kế lại tab Khoảng cách kỹ năng: biểu đồ ngang có tooltip, ngăn bằng chứng, thẻ JD và kỹ năng ưu tiên. |
| 5.8.1 | Tab "Tiến độ và nhắc nhở" đổi thành "Nhắc nhở" và được làm gọn. |
| 5.8.2 | Lộ trình học tập: thẻ Tổng quan, thẻ Việc tiếp theo, mỗi học phần chỉ một nút chính. |
| 5.8.3 – 5.8.4 | Thẻ kỹ năng tự khai và thẻ JD dạng lưới thẻ. |
| 5.9.0 | Đợt kiểm toán này: sửa F1–F5, thêm Báo cáo năng lực. |

## 6. Chức năng loại bỏ hoặc thay thế

Không loại bỏ chức năng nào trong đợt này. Trong chuỗi 5.5 → 5.9 có thay thế:
- biểu đồ SVG `skillBullets` được thay bằng `gapChart` (chỉ trang Khoảng cách kỹ năng dùng);
- trang mini-test cũ trong `progress.js` được thay bằng `check.js`.

## 7. Thay đổi UI/UX trong đợt này

- Thêm trang Báo cáo năng lực (bản màn hình và bản in) cùng nút mở ở tab Khoảng cách kỹ năng.
- Các thông báo lỗi mới ở API đều có bản dịch tiếng Anh; test i18n đạt.

## 8. Kiến trúc và hiệu suất

- Không đổi kiến trúc, database hay thư viện.
- Các thay đổi đều nằm ở tầng kiểm tra dữ liệu đầu vào của API, không thay đổi công thức nghiệp vụ.
- Hiệu suất đã đo như ở mục 1, không cần tối ưu thêm.

## 9. Kết quả kiểm thử

| | Trước | Sau |
| --- | --- | --- |
| Toàn bộ bộ test | 781 passed, 10 skipped, 22 warnings | **815 passed, 10 skipped, 1 warning** |
| Test mới | — | `tests/test_audit_hardening.py` (33 test: dữ liệu sai kiểu ở Test Center; truy cập chéo vào lượt làm bài và JD; ID không tồn tại trả 404; cập nhật tiến độ sai; ràng buộc học phần ở admin; tiêu đề JD chứa HTML) và `tests/test_input_fuzz.py` (20 kiểu body sai × 18 API ghi dữ liệu: không có lỗi 500 nào) |

Kiểm tra trên trình duyệt (server thử với bản sao dữ liệu trong scratchpad, không phải `data/`): trang Báo cáo năng lực ở chế độ màn hình và chế độ in, với một tài khoản đã hoàn tất quy trình. Số liệu khớp với tab Khoảng cách kỹ năng.

**Chưa chạy được:** 10 test gọi Gemini thật trong `tests/test_ai_live.py` bị bỏ qua. Lý do là bộ test cố ý không đọc file `.env` của máy dev, nên không có cấu hình Gemini thật. Các test này cần được chạy riêng khi có API key.

## 10. Vấn đề còn tồn tại

- Dự án chưa dùng Git: lịch sử thay đổi chỉ có trong các thư mục sao lưu và báo cáo này. Nên khởi tạo repository để theo dõi thay đổi.
- Học liệu và JD mẫu được duyệt bởi tài khoản `seed-import`; cần người thật kiểm tra lại nội dung.
- Ngân hàng câu hỏi cho bài kiểm tra kiến thức chưa có câu đúng/sai, câu trả lời ngắn hay bài tập SQL. Nếu muốn AI sinh câu hỏi thì cần thêm bước admin duyệt trước khi dùng.
- Báo cáo năng lực dùng chức năng in của trình duyệt; chưa có xuất PDF phía máy chủ.
- Một số nhánh giao diện mới chỉ được kiểm tra qua code hoặc dữ liệu giả lập ngay trong trình duyệt, chưa thấy trên dữ liệu thật:
  - nút nhảy tới phần "Chưa xếp được" ở tab Lộ trình;
  - trạng thái "JD chưa được phân tích" ở tab Khoảng cách kỹ năng.
- Độ mượt khung hình của nền chuyển động chưa được đo trên máy thật.

## 11. Hướng phát triển tiếp theo

1. Khởi tạo Git và chuyển các bản sao lưu thành commit.
2. Thêm dạng câu hỏi mới vào ngân hàng câu hỏi, kèm quy trình admin duyệt cho câu hỏi do AI đề xuất.
3. Biểu đồ tiến bộ theo thời gian trong Báo cáo năng lực (dữ liệu đã có ở `/me/skill-history`).
4. Chạy lại các test Gemini thật khi có API key, và thử nghiệm với nhóm học viên thật để đo độ ổn định của AI.


---

## Bổ sung 11/11/2026 · Phiên bản 5.11.0: nâng cấp theo góp ý

Sao lưu trước khi sửa: `CareerAdapt_AI_backup_truoc_gop_y_20261111` (cùng cấp thư mục dự án). Không đổi cấu trúc bảng; database thật không bị sửa.

| Góp ý | Đã làm | Nơi xem |
| --- | --- | --- |
| Làm sao để mọi người biết đến nền tảng | Trang giới thiệu công khai `/gioi-thieu` (song ngữ, sáng/tối, không gọi API). Người chưa đăng nhập mở `/` sẽ vào trang này. Nút "Sao chép để chia sẻ" tạo câu giới thiệu kèm trình độ của chính người dùng. | `frontend/landing.html`, mục Xếp hạng và lương |
| Lương theo mức độ tăng để khuyến khích người dùng | Thẻ "Lương tham khảo trên thị trường": lương trung vị theo năm kinh nghiệm và phần trăm tăng, kèm nguồn, thời gian khảo sát và ngày kiểm tra. Admin sửa được ở Quản trị nội dung > Lương tham khảo; máy chủ từ chối số liệu không có nguồn. | `data/salary_reference_v1.json`, `backend/insights.py` |
| Nguồn chất lượng đầu ra | Thẻ "Kết quả này dựa trên gì" dưới trang kết quả: khung kỹ năng, nguồn JD, cách chấm, học liệu, nguồn lương. | Kết quả bài làm |
| Hơi rối kết quả đầu ra | Bảng kết quả còn 4 cột, lý do gập dưới từng kỹ năng ("Vì sao"), thêm dòng "Việc nên làm tiếp" và tên mức bên cạnh số mức. | Kết quả bài làm |
| Mức độ cạnh tranh, bảng xếp hạng | Mục mới "Xếp hạng và lương": hạng, "Top X%" (chỉ khi có từ 5 người), bảng 10 dòng. Người khác ẩn danh, mỗi người tự bật hiện tên. | `#/plan/da/rank` |
| Cách phân bậc kỹ năng | Giữ thang 0-3, đặt tên theo bậc nghề: Chưa bắt đầu, Nền tảng, Sẵn sàng thực tập (Intern), Sẵn sàng đầu nghề (Fresher). Hộp thoại "Cách phân bậc" giải thích ý nghĩa, cách chứng minh và tiêu chí từng kỹ năng. | `backend/levels.py` |

Số liệu lương lấy từ Báo cáo Lương và Thị trường tuyển dụng IT Việt Nam 2025-2026 của ITviec (nhóm Data Analyst / Data Scientist / BI Analyst, lương trung vị): 1-2 năm 23,8 triệu, 5-8 năm 42,5 triệu, mọi mức 40,65 triệu. Báo cáo không có số cho nhóm dưới 1 năm, 3-4 năm và trên 8 năm, nên giao diện ghi rõ điều này và không gắn lương với từng mức 0-3.

Quy tắc xếp hạng: mỗi người tính bài kiểm tra Career Adapt gần nhất đã chấm; xếp theo tổng mức đã xác thực, rồi đến điểm; đồng hạng dùng chung vị trí.

Kiểm thử: thêm `tests/test_insights.py` (12 test). Toàn bộ: **830 passed, 10 skipped**. Đã kiểm tra trên trình duyệt với bản sao dữ liệu: trang giới thiệu, kết quả, hộp thoại phân bậc, xếp hạng, bật/tắt hiện tên, form lương của admin, bề rộng 375px.

Việc còn mở cho nhóm:
- Database thật hiện có 3 người đã chấm bài, nên "Top X%" chưa hiện cho tới khi đủ 5 người.
- Trang giới thiệu chỉ có ích khi ứng dụng được triển khai ở địa chỉ công khai; hiện vẫn chạy trên máy cá nhân.
- Lương mới có một nguồn và không có số cho người dưới 1 năm kinh nghiệm. Nên bổ sung khi có báo cáo khác.
- Mức 3 gắn với "Fresher" là đề xuất, nhóm cần thống nhất với giảng viên.


---

## Bổ sung 11/11/2026 · Phiên bản 5.12.0: mở rộng dữ liệu nội dung

Sao lưu trước khi sửa: `CareerAdapt_AI_backup_truoc_mo_rong_du_lieu_20261111`. Không đổi cấu trúc bảng. Database thật không bị sửa trực tiếp: khi khởi động lại, ứng dụng tự nạp phần nội dung mới còn thiếu và giữ nguyên mọi dòng đã có.

| Hạng mục | Trước | Sau | Tệp |
| --- | --- | --- | --- |
| Học liệu | 16 | 46 | `data/learning_resources_v4.json` |
| Học phần có dưới 2 học liệu | 5 (trong đó `ACT_DQ_02` có 0) | 0 | `data/activities_v1.json` |
| Câu hỏi kiểm tra kiến thức | 60 (4 câu mỗi kỹ năng, mỗi mức) | 100 (ít nhất 6 câu mỗi kỹ năng, mỗi mức) | `data/question_bank_v1.json`, `data/i18n/sensitive_en.json` |
| Yêu cầu JD "Ngoài danh mục" trong lộ trình | Chỉ có lý do | Có thêm học liệu tự học gợi ý | `data/supplementary_topics_v1.json`, `backend/supplementary.py` |
| Kho kiến thức của trợ lý | Không có thông tin thị trường và ngành | Thêm 2 tài liệu | `backend/ai_service/knowledge.py`, `data/knowledge/chi_so_theo_nganh.md` |

Chi tiết:

- **Học liệu**: 20 học liệu gắn vào học phần (SQL nâng cao, kiểm tra chất lượng tự động, pandas, biểu đồ, Power BI, viết báo cáo) và 10 học liệu tự học cho các chủ đề hệ thống chưa đo (Excel / Google Sheets, thống kê, Power Query / DAX, Power BI, mô hình hóa dữ liệu, tiếng Anh, kiến thức miền). Mỗi đường dẫn được kiểm tra ngày 11/11/2026: phản hồi HTTP 200 và đúng tiêu đề trang. Ba đường dẫn không xác minh được đã bị loại.
- **Mục "Chưa xếp được"**: học phần `ACT_DQ_02` trước đây bị loại vì thiếu học liệu, nay có 3 học liệu. Các yêu cầu JD ngoài danh mục vẫn không được xếp lịch và không được chấm (chưa có rubric), nhưng hiện kèm tối đa 4 học liệu tự học. Yêu cầu không khớp chủ đề nào (ví dụ số năm kinh nghiệm) không có gợi ý.
- **Câu hỏi**: 40 câu mới, 8 câu mỗi kỹ năng, đủ bốn dạng (một đáp án, nhiều đáp án, số, sắp xếp), có giải thích và bản dịch tiếng Anh. Số liệu trong câu hỏi không trùng với đề thi Career Adapt.
- **Thông tin ngành**: tài liệu "Thị trường Data Analyst" được sinh từ tệp lương có nguồn và thư viện JD đã duyệt (trạng thái đã duyệt). Tài liệu "Chỉ số thường gặp theo ngành" do nhóm phát triển soạn, nên ở trạng thái **nháp** theo đúng quy tắc hiện có; trợ lý chỉ dùng sau khi quản trị viên duyệt ở Quản trị nội dung > Kho kiến thức AI.

Kiểm thử: thêm `tests/test_content_expansion.py` (9 test). Đã kiểm tra trên trình duyệt với bản sao dữ liệu: trang Học liệu hiện 46 mục, lộ trình hiện học liệu tự học dưới yêu cầu ngoài danh mục.

Việc còn mở cho nhóm:
- Học liệu mới được đánh dấu đã duyệt theo cách của bộ học liệu khởi tạo (đã kiểm tra đường dẫn, chưa có người đọc lại nội dung). Quản trị viên nên rà lại.
- Lộ trình đã lưu của người dùng giữ nguyên danh sách học phần cũ; học phần mới có học liệu chỉ vào lịch khi lộ trình được tạo lại.
- Phiên bản ngân hàng câu hỏi vẫn là `QB-DA-1.0`.
- Cần duyệt tài liệu "Chỉ số thường gặp theo ngành" để trợ lý sử dụng.


---

## Bổ sung 11/11/2026 · Phiên bản 5.14.0: kỹ năng Thống kê & Thử nghiệm A/B

Sao lưu trước khi sửa: `CareerAdapt_AI_backup_truoc_ky_nang_thong_ke_20261111`. Không đổi cấu trúc bảng; database thật không bị sửa trực tiếp. (Phiên bản 5.13.0 cùng ngày chỉ sửa CSS về khả năng tiếp cận: chữ 15px, không còn chữ dưới 12px, chữ mờ đạt tương phản, nút 44px trên màn hình cảm ứng.)

Yêu cầu "Thống kê / A-B testing" trong JD trước đây nằm ở mục "Chưa xếp được" vì hệ thống không có kỹ năng, rubric và bài đo tương ứng. Nay đã có đủ:

| Thành phần | Nội dung | Tệp |
| --- | --- | --- |
| Kỹ năng và rubric | `STATISTICS`, 4 mức 0-3, nguồn tham chiếu OpenStax Introductory Statistics 2e và Kohavi, Tang & Xu (2020). Trọng số 0: **kỹ năng tùy chọn**, chỉ đo khi JD yêu cầu, nên bộ mục tiêu mặc định vẫn là 5 kỹ năng. | `data/skills_v1.json` |
| Nhận diện trong JD | Các từ: statistics, thống kê, A/B testing, hypothesis testing, kiểm định giả thuyết... Mức mục tiêu: 1 (thực tập), 2 (junior). Nhóm "Thống kê / A-B testing" bị gỡ khỏi danh sách chưa đo. Phiên bản mapping `MAP-4.1`. | `data/skill_mapping_v4.json` |
| Bài kiểm tra Career Adapt | 3 câu theo 3 độ khó, mỗi câu 2 biến thể dữ liệu, chấm bằng đáp án tính từ bộ dữ liệu: số đo mô tả; trung bình và trung vị bằng Pandas; so sánh hai tháng và thiết kế thử nghiệm. Ngân hàng đề `EX-DA-1.2`. | `data/exam_items_v5.json` |
| Kiểm tra kiến thức | 18 câu (6 câu mỗi mức) và đề "Kiểm tra nhanh: Thống kê". | `data/question_bank_v1.json` |
| Học phần | 3 học phần cho mức 1, 2, 3 (10 giờ) với 8 học liệu đã kiểm tra đường dẫn. | `data/activities_v1.json`, `data/learning_resources_v4.json` |
| Tự khai, giao diện | Lựa chọn tự khai 0-3, tên, biểu tượng và màu của kỹ năng; bản dịch tiếng Anh. | `data/skill_level_options_v5.json`, `frontend/js` |

Quy tắc giữ nguyên: kỹ năng không có bài đo thì không thành tiêu chí xác thực. Kỹ năng tùy chọn được coi là có bài đo khi mang cờ `assessed_by: EXAM` và có câu trong ngân hàng đề.

Kiểm thử: thêm `tests/test_statistics_skill.py` (9 test, gồm một lượt chạy trọn quy trình với JD có yêu cầu thống kê). Toàn bộ: **867 passed, 10 skipped**. Bốn test cũ được cập nhật theo dữ liệu mới: số câu của ngân hàng đề (15 thành 18) và danh sách kỹ năng của nó, số tài liệu kiến thức (5 thành 6 kỹ năng, 10 thành 13 học phần), và mã kỹ năng mẫu trong test CRUD của admin (trùng với mã `STATISTICS` nên đổi thành `FORECASTING`).

Việc còn mở cho nhóm:
- Kết quả và lộ trình đã có vẫn gắn với JD cũ. Muốn được đo Thống kê, người dùng cần làm lại quy trình và nhập lại JD để hệ thống phân tích theo mapping mới.
- JD trong thư viện (ví dụ JD Google) vẫn ghi thống kê là yêu cầu ngoài danh mục, vì JD đã nạp không bị ghi đè. Cần tạo phiên bản JD mới nếu muốn đo.
- Rubric, câu hỏi và mức mục tiêu của kỹ năng mới là đề xuất khởi tạo, cần giảng viên hoặc quản trị viên rà lại.


---

## Bổ sung 11/11/2026 · Phiên bản 5.15.0: Learning Roadmap 2.0

Khảo sát, thiết kế, danh sách file, migration, API, kết quả kiểm thử và hướng dẫn chạy nằm ở `docs/learning_roadmap_2_0.md`. Sao lưu trước khi sửa: `CareerAdapt_AI_backup_truoc_roadmap_2_0_20261111`. Toàn bộ test: 888 passed, 10 skipped.

---

## Bổ sung 13/11/2026 · Phiên bản 5.18.0: sửa theo kiểm định 12/11/2026

Chi tiết từng mục, bằng chứng và phần còn mở ở cuối `AUDIT_REPORT.md` (mục "Tình trạng sau khi sửa").

**Đánh giá năng lực**
- Độ khó theo mức JD yêu cầu, không theo mức tự khai.
- Chống lách bài viết bằng từ khóa.
- Câu viết không có số liệu đúng tối đa mức 1.
- Ngân hàng 4 bộ dữ liệu.

**Lộ trình**
- Trắc nghiệm hoàn thành bài học xác nhận tối đa mức 2.
- Trượt thì chờ 6 giờ mới làm lại.
- Báo tuần trễ hạn và dời lịch từ hôm nay.

**Quy trình**
- Đổi JD mục tiêu mà vẫn giữ mức đã xác thực.

**Chức năng mới**
- So khớp năng lực với mọi JD đã duyệt.

**Triển khai**
- Liên kết email theo địa chỉ cấu hình, kiểm tra Host và proxy tin cậy.
- `requirements.lock`.
- Tài liệu API không còn đường trùng.

Sao lưu: `CareerAdapt_AI_backup_truoc_sua_kiem_dinh_20261113`. Toàn bộ test: 1029 passed, 10 skipped.

---

## Bổ sung 13/11/2026 · Phiên bản 5.19.0: chấm bài chạy nền (kiểm định B-04)

Nộp bài chỉ khóa câu trả lời rồi đưa bài vào hàng đợi chấm `backend/grading_queue.py`, nên yêu cầu nộp trả về ngay.

- **Cách chấm:** một nhóm luồng cố định chấm bài (mặc định 2, chỉnh bằng `CAREERADAPT_GRADING_WORKERS`), nên số sandbox chạy cùng lúc có giới hạn.
- **Không chấm hai lần:** trạng thái `SUBMITTED → GRADING → GRADED` vẫn là nguồn sự thật.
- **Khi máy chủ dừng giữa chừng:** bài đang chấm dở được đưa lại hàng đợi ở lần quét nền kế tiếp.
- **Phạm vi:** áp dụng cho bài kiểm tra đầu vào và bài đánh giá tổng hợp.
- **Giao diện:** có màn hình "Đang chấm bài" tự mở kết quả. Danh sách bài đánh giá có nhãn "Đã nộp, chờ chấm" và "Đang chấm".
- **Kiểm thử:** dưới pytest, hàng đợi mặc định chấm ngay trong yêu cầu nên các test cũ giữ nguyên. `tests/test_background_grading.py` chạy đúng đường chấm nền. `CAREERADAPT_SYNC_GRADING=true` trả về cách chấm cũ khi cần gỡ lỗi.
- **Đo trên máy chủ thật** (bản sao dữ liệu): nộp bài trả về sau 9 ms, chấm xong ở nền sau 3,7 giây.

Sao lưu: `CareerAdapt_AI_backup_truoc_cham_nen_20261113`. Toàn bộ test: 1036 passed, 10 skipped.

---

## Bổ sung 13/11/2026 · Phiên bản 5.20.0: logo của nhóm

Logo được gắn vào các vị trí sau:

| Vị trí | Logo dùng |
|---|---|
| Thanh bên ứng dụng (nền tối) | Logo trắng |
| Khung giới thiệu trang đăng nhập (nền tối) | Logo trắng |
| Trang đăng nhập trên điện thoại | Logo xanh ở giao diện sáng, logo trắng ở giao diện tối |
| Trang giới thiệu `/gioi-thieu`: đầu trang, và logo đầy đủ kèm khẩu hiệu ở phần mở đầu | Logo xanh ở giao diện sáng, logo trắng ở giao diện tối |
| Bìa Báo cáo năng lực | Logo xanh khi in |
| Biểu tượng trên tab trình duyệt và trên màn hình chính điện thoại | Logo xanh |

**Tệp logo**
- Tệp nằm trong `frontend/img/`, được phục vụ tại `/img/`.
- Logo trắng được tạo lại từ kênh trong suốt của logo xanh. Tệp logo trắng nhóm gửi đã dính sẵn nền ô vuông trong ảnh, không trong suốt, nên không dùng được.

**Sửa kèm**
- Câu mô tả bước 1 trên trang giới thiệu vẫn ghi "chọn độ khó theo mức tự khai", không còn đúng kể từ 5.18. Đã sửa thành "độ khó theo mức JD yêu cầu".

---

## Bổ sung 13/11/2026 · Phiên bản 5.21.0: linh vật CareerAdapt AI

Hình robot của nhóm được cắt ra từ ảnh minh họa. Không giữ chữ, bong bóng thoại hay các thẻ chức năng; vùng bong bóng còn sót được làm mờ.

**Hai tệp ảnh trong `frontend/img/`**
- `ai-avatar.webp`: ảnh tròn phần đầu, 10 KB.
- `ai-mascot.webp`: nửa người, mờ dần ra viền, 55 KB.

**Ảnh chỉ đặt ở những nơi AI thật sự làm việc**
- Thẻ "Khám phá tiềm năng cùng Trợ lý AI" ở thanh bên.
- Nút nổi "Trợ lý".
- Tiêu đề khung trò chuyện.
- Màn hình chào của Trợ lý.
- Mỗi câu trả lời của Trợ lý.
- Nút "AI tóm tắt" JD.
- Khung "Nhận xét bằng AI" của mini-test.
- Nhận xét AI trong trang xem lại bài kiểm tra.
- Nhận xét AI tổng thể ở trang Kết quả.

Các nhận xét do quy tắc tạo (không qua AI) giữ biểu tượng cũ, để người học phân biệt được đâu là AI và đâu là máy chấm.

**Sửa kèm:** câu "Chỉ để chọn độ khó" dưới mức tự khai ở trang Kết quả không còn đúng kể từ 5.18, nay đổi thành "Chỉ để so sánh với kết quả bài làm".

---

## Bổ sung 13/11/2026 · Phiên bản 5.22.0: robot chớp mắt ở Bảng điều khiển

Đầu robot vẽ tay trong thẻ "Chào mừng trở lại" được thay bằng hai khung hình của nhóm. Thân "AI" và các biểu tượng xung quanh giữ nguyên.

**Hai khung hình**
- `frontend/img/ai-head-open.webp`: mở mắt.
- `frontend/img/ai-head-closed.webp`: nhắm mắt cười.

Hai khung chỉ khác nhau ở vùng mắt (đã kiểm tra từng điểm ảnh), nên khi đổi khung trông như robot chớp mắt, không bị giật.

**Nhịp chuyển động** (lặp lại mỗi 7 giây)
1. Mở mắt phần lớn thời gian.
2. Chớp nhanh một lần (khoảng 0,1 giây).
3. Chớp đôi.
4. Cười "^^" khoảng 0,6 giây, kèm nghiêng đầu nhẹ.

**Khi Windows tắt hiệu ứng chuyển động**
- Chớp mắt vẫn chạy, vì chỉ đổi đôi mắt, không có gì di chuyển trên màn hình.
- Riêng động tác nghiêng đầu và robot nhấp nhô ở thanh bên thì tắt.

---

## Bổ sung 13/11/2026 · Phiên bản 5.22.1: logo AI mới

Mọi biểu tượng AI dùng robot mới của nhóm: robot nháy mắt, giơ ngón cái. Các vạch trang trí và bóng dưới chân đã được bỏ, vì chúng là các mảng rời khỏi thân robot.

**Hai ảnh dùng chung**
- `ai-avatar.webp`: đầu robot (mũ, mặt, tai nghe) trên nền tròn xanh nhạt. Ảnh vẫn rõ khi thu nhỏ tới 20 px.
  - Dùng ở: nút Trợ lý, tiêu đề khung Trợ lý, mỗi câu trả lời của Trợ lý, nút "AI tóm tắt", nút và khung "Nhận xét bằng AI", nhận xét AI ở trang xem lại bài và trang Kết quả.
- `ai-mascot.webp`: robot nửa người, nền trong suốt, có quầng sáng nhẹ phía sau.
  - Dùng ở: màn hình chào của Trợ lý.

**Giữ nguyên**
- Thẻ AI ở thanh bên: robot toàn thân.
- Robot chớp mắt ở Bảng điều khiển.

---

## Bổ sung 13/11/2026 · Phiên bản 5.23.0: ảnh đại diện và quy tắc mật khẩu mới

### Ảnh đại diện

**Cách dùng.** Ở Hồ sơ → Tài khoản có các nút "Tải ảnh lên", "Đổi ảnh" và "Xóa ảnh". Ảnh hiện ở góc phải thanh trên. Chưa có ảnh thì hiện chữ cái đầu của tên như trước.

**Máy chủ xử lý ảnh trước khi lưu** (`backend/avatar.py`, dùng Pillow)
- Chỉ nhận ảnh PNG, JPG hoặc WebP thật, tối đa 3 MB.
- Kiểm tra số điểm ảnh trước khi giải nén, để chặn ảnh "bom giải nén".
- Xoay ảnh đúng chiều, cắt vuông ở giữa và lưu lại thành WebP 256×256.
- Việc lưu lại xóa mọi dữ liệu kèm theo ảnh, gồm cả vị trí GPS.

**Lưu trữ.** Ảnh nằm trong bảng mới `account_avatars` của `accounts.sqlite3`. Bảng được tạo bằng `CREATE TABLE IF NOT EXISTS`, không đụng dữ liệu cũ, và tự xóa theo tài khoản.

**API**
- `GET`, `PUT` và `DELETE` tại `/api/v1/auth/me/avatar`.
- Người dùng chỉ đọc được ảnh của chính mình. Thao tác ghi cần CSRF như mọi API khác.

**Phụ thuộc.** `requirements.txt` ghi rõ `pillow`. Thư viện này đã có sẵn trong môi trường qua matplotlib, không cài thêm gì.

### Mật khẩu

**Quy tắc mới:** chỉ cần ít nhất 8 ký tự. Bỏ các yêu cầu chữ hoa, chữ thường, chữ số và ký tự đặc biệt. Quy tắc áp dụng thống nhất ở máy chủ, danh sách kiểm tra trên giao diện, API `/auth/password-policy` và lệnh tạo admin. Tài khoản cũ không bị ảnh hưởng.

**Test cũ đã sửa theo yêu cầu đổi quy tắc của nhóm:** `test_password_policy_rules` và `test_register_rejects_weak_password_with_failed_rules`.

**Test mới:** `tests/test_avatar.py`.

Toàn bộ test: 1046 passed, 10 skipped.

---

## Bổ sung 13/11/2026 · Phiên bản 5.23.1: ảnh đại diện trên bảng xếp hạng

Mỗi dòng của bảng xếp hạng có ảnh tròn đặt cạnh tên.

**Ai hiện ảnh gì**

| Dòng | Ảnh hiển thị |
|---|---|
| Dòng "Bạn" | Ảnh của bạn. Chưa có ảnh thì hiện chữ cái đầu của tên |
| Học viên đã tự bật "Hiện tên tôi trên bảng xếp hạng" | Ảnh của họ (nếu họ đã tải ảnh) |
| Học viên ẩn danh | Biểu tượng người chung; ảnh thật không bao giờ được gửi về trình duyệt |

**Cách gửi ảnh.** Ảnh được thu nhỏ về 64 px và gửi kèm dữ liệu bảng xếp hạng. Vì vậy không có đường dẫn nào cho phép xem ảnh của người khác, và không lộ mã tài khoản.

**Không đổi.** Thứ tự xếp hạng, điểm và quy tắc ẩn danh giữ nguyên.

**Kiểm thử.** Test mới `test_board_pictures_follow_the_name_choice` kiểm tra ba trường hợp trên.

---

## Bổ sung 13/11/2026 · Phiên bản 5.24.0: quy tắc mật khẩu mở rộng và nút giao diện mới

### Mật khẩu

Vẫn không bắt buộc chữ hoa hay ký tự đặc biệt. Thêm các quy tắc chống mật khẩu dễ đoán, theo hướng NIST SP 800-63B. Có 3 quy tắc:

1. **Độ dài:** từ 8 đến 128 ký tự.
2. **Không dễ đoán:**
   - Không nằm trong danh sách mật khẩu phổ biến, gồm cả các mật khẩu tiếng Việt như "matkhau123" và "anhyeuem".
   - Không phải một ký tự lặp lại hoặc chỉ 2 ký tự khác nhau ("aaaaaaaa").
   - Không phải dãy liền như "12345678", "abcdefgh", "qwertyui", kể cả viết ngược.
   - Không phải một cụm ngắn lặp lại ("abababab", "abc1abc1").
3. **Không chứa thông tin cá nhân:** không chứa phần tên trong email (kể cả từng phần tách theo dấu chấm hoặc gạch) và không chứa tên của người dùng (cả tên ghép, từng tiếng, hay hai tiếng liền nhau). Phép so sánh không phân biệt dấu tiếng Việt.

**Phạm vi áp dụng:** đăng ký, đổi mật khẩu, đặt lại mật khẩu và lệnh tạo tài khoản quản trị.

**Danh sách kiểm tra trên giao diện:** hiện từng quy tắc và tự cập nhật khi người dùng gõ email hoặc tên. Danh sách mật khẩu phổ biến được lấy từ `GET /api/v1/auth/password-policy`, nên máy chủ và trình duyệt dùng chung một danh sách.

**Tài khoản cũ** không bị ảnh hưởng.

### Nút chọn giao diện

Nút tròn đổi vòng (bấm nhiều lần để chuyển) được thay bằng thanh 3 biểu tượng: mặt trời (Sáng), mặt trăng (Tối), màn hình (Theo hệ thống).

- **Kiểu dáng:** thanh viên thuốc giống nút VI/EN; lựa chọn đang dùng được tô màu.
- **Vị trí:** dùng chung ở thanh trên ứng dụng, trang đăng nhập và trang giới thiệu.
- **Đồng bộ:** đổi ở một nơi thì mọi nơi cập nhật theo.
- **Trợ năng:** nút có nhãn đọc màn hình bằng tiếng Việt và tiếng Anh.
- **Điện thoại:** đã kiểm tra trên bề rộng điện thoại, không bị tràn ngang.

### Kiểm thử

Có thêm test cho quy tắc mật khẩu mới. Ba test cũ dùng mật khẩu mẫu chứa tên hoặc email của chính tài khoản nên bị quy tắc mới chặn; tôi đã đổi mật khẩu mẫu trong các test đó, không đổi điều chúng kiểm tra.

Toàn bộ test: 1066 passed, 10 skipped.

---

## Bổ sung 13/11/2026 · Phiên bản 5.25.0: banner chào mừng mới ở Bảng điều khiển

Phần đầu Bảng điều khiển được làm lại theo mẫu của nhóm.

**Nền và chữ**
- Nền xanh navy đậm, có các vệt sáng xanh lơ và một tia sáng chéo.
- Nhãn trạng thái ở trên cùng, kèm chấm màu: xanh lá khi đã hoàn tất, vàng khi đang làm, xám khi chưa bắt đầu.
- Tiêu đề lớn, tên người dùng màu xanh lơ, kèm 👋.

**Nút**
- Nút trắng: "Xem kết quả và luyện tập".
- Nút viền: "Lộ trình kỹ năng". Nút này chỉ hiện khi đã hoàn tất quy trình.

**Phần hình bên phải**
- Robot đứng trong một tấm kính phát sáng, xung quanh có ô số liệu, ô trò chuyện, khiên tích xanh và các ngôi sao.
- Ô số liệu hiện mức đáp ứng JD thật lấy từ `/me/gap`. Khi chưa đủ bằng chứng, ô chỉ hiện biểu tượng, không bịa số.
- Robot chớp mắt mỗi 1,5 giây, mắt nhắm khoảng 0,14 giây.
- Robot và các ô nổi lên xuống nhẹ. Chuyển động này tắt khi máy bật chế độ giảm chuyển động, nhưng chớp mắt vẫn chạy.

**Màn hình nhỏ**
- Dưới 900 px: ẩn phần hình.
- Trên điện thoại: hai nút trải rộng hết chiều ngang.

---

## Bổ sung 13/11/2026 · Phiên bản 5.25.1: nút giao diện một nút

Thanh 3 nút sáng, tối, hệ thống được gộp lại thành **một nút tròn** dùng chung ở thanh trên ứng dụng, trang đăng nhập và trang giới thiệu.

- **Cách dùng:** mỗi lần bấm chuyển sang chế độ kế tiếp theo vòng Sáng → Tối → Theo hệ thống.
- **Hiển thị:** nút hiện biểu tượng của chế độ đang dùng (mặt trời, mặt trăng hoặc màn hình), có hiệu ứng xoay nhẹ khi đổi.
- **Nhãn và gợi ý:** khi rê chuột hoặc dùng trình đọc màn hình, nút cho biết chế độ hiện tại và chế độ sẽ chuyển sang, ví dụ "Giao diện: Sáng (bấm để chuyển sang Tối)". Có cả tiếng Việt và tiếng Anh.

---

## Bổ sung 13/11/2026 · Phiên bản 5.26.0: quy tắc mật khẩu theo yêu cầu nhóm

Quy tắc mật khẩu nay chỉ còn đúng hai điều, áp dụng cho đăng ký, đổi mật khẩu và đặt lại mật khẩu:

1. Ít nhất 8 ký tự (tối đa 128).
2. Có ít nhất 1 chữ cái in hoa **và** 1 ký tự đặc biệt.

- Máy chủ kiểm tra bằng `PASSWORD_RULES` trong `backend/accounts.py` (mã quy tắc `length`, `upper`, `special`). Giao diện chỉ hiện danh sách kiểm tra, không tự quyết định đạt hay không.
- Chữ có dấu tiếng Việt vẫn được nhận, ví dụ "Ánh@sáng".
- Các quy tắc thêm ở bản 5.24 (không chứa email, tên, mật khẩu phổ biến) đã bỏ theo yêu cầu.
- Kiểm thử: `tests/test_auth_sessions.py` có các ca mật khẩu thiếu từng điều kiện và ca hợp lệ.

---

## Bổ sung 13/11/2026 · Phiên bản 5.26.1: thân robot ở banner chào mừng

Phần thân bên dưới khuôn mặt robot ở banner Bảng điều khiển được vẽ lại:

- Cổ áo, màn hình ngực có chữ "AI" và dãy đèn nhỏ.
- Hai cánh tay; tay phải vẫy nhẹ.
- Bóng đổ dưới chân.

Khuôn mặt vẫn chớp mắt mỗi 1,5 giây như bản 5.25.

---

## Bổ sung 14/11/2026 · Phiên bản 5.27.0: giao diện Trợ lý AI mới, nhập bằng giọng nói, đính kèm ảnh

### Giao diện (theo mock-up của nhóm)

- **Khung:** nền chuyển màu tím nhạt sang xanh nhạt, có bản tối riêng.
- **Thanh trên:** các nút "+ Mới", "Lịch sử" (biểu tượng đồng hồ) và "✕ Đóng" màu đỏ, nằm cùng hàng với tên trợ lý. Trên điện thoại hai nút đầu chỉ còn biểu tượng.
- **Gợi ý:** mỗi tác vụ là một chip màu pastel có biểu tượng riêng:
  - 📄 Phân tích JD
  - 📊 Giải thích kết quả
  - 🧩 Phân tích kỹ năng
  - 🎓 Học gì tiếp theo
  - 🗺️ Giải thích lộ trình
  - 🏆 Tổng hợp hành trình
  - ⏱️ Tư vấn mức sẵn sàng

  Tên tác vụ vẫn lấy từ máy chủ.
- **Ô nhập:** thẻ trắng bo tròn. Góc dưới có nút ghim ảnh và nút micro. Nút gửi là nút tròn màu xanh lớn, có máy bay giấy và chữ "Gửi".
- **Ảnh đại diện AI:** `frontend/img/ai-avatar.webp` được dựng lại từ khuôn mặt robot nằm ngang, đặt trên nền tròn xanh nhạt. Ảnh này dùng cho nút nổi, thanh tiêu đề và từng câu trả lời.

### Nhập bằng giọng nói

- Dùng nhận dạng giọng nói có sẵn của trình duyệt (Chrome, Edge), tiếng Việt hoặc tiếng Anh theo ngôn ngữ đang chọn.
- Chữ nghe được điền vào ô câu hỏi. **Không tự gửi**: người dùng xem lại rồi bấm "Gửi".
- Lúc đang nghe, nút micro chuyển đỏ và nhấp nháy. Bấm lần nữa để dừng.
- Có thông báo rõ khi trình duyệt không hỗ trợ, chưa cho phép micro hoặc không nghe thấy gì.
- Lưu ý: Chrome gửi âm thanh tới dịch vụ nhận dạng của Google; máy chủ CareerAdapt không nhận âm thanh.
- Header `Permissions-Policy` đổi `microphone=()` thành `microphone=(self)`, nghĩa là chỉ chính trang này được xin micro. Camera và vị trí vẫn bị chặn.

### Đính kèm ảnh

- Bấm nút ghim hoặc dán ảnh vào ô câu hỏi.
- Định dạng nhận: PNG, JPG, WebP, tối đa 5 MB. Trước khi gửi có ô xem trước và nút bỏ ảnh.
- Endpoint mới: `POST /api/v1/assistant/conversations/{id}/messages/image` (multipart). Cũng cần đăng nhập, CSRF và chỉ chủ hội thoại được dùng.
- Máy chủ kiểm tra ảnh bằng Pillow (`backend/avatar.py: process_chat_image`): đúng định dạng thật, chặn ảnh quá lớn, xoay đúng chiều, xóa metadata (GPS…), thu về tối đa 1280 px và nén JPEG. Tệp giả mạo bị trả 422.
- Ảnh chỉ được gửi kèm câu hỏi tới Gemini (`inlineData`). Lời nhắn hệ thống dặn mô hình coi chữ trong ảnh là dữ liệu, không phải mệnh lệnh.
- **Máy chủ không lưu ảnh.** Cơ sở dữ liệu chỉ ghi `attachment: "image"`, nên khi mở lại hội thoại sẽ thấy nhãn "📎 Ảnh đính kèm" thay cho ảnh.
- Khi dịch vụ AI chưa cấu hình hoặc lỗi, câu trả lời ghi rõ là ảnh chưa được phân tích và chỉ dựa trên phần chữ.

### Kiểm thử

- Mới: `tests/test_assistant_image.py`, gồm:
  - ảnh tới mô hình và chỉ ghi chú được lưu;
  - làm phẳng nền trong suốt và thu nhỏ ảnh;
  - từ chối tệp rỗng, tệp giả, GIF, ảnh quá nhỏ;
  - 422 không lưu gì;
  - thông báo ở chế độ không AI;
  - tài khoản khác bị 404;
  - cần CSRF;
  - Permissions-Policy.
- Mới: `tests/test_ai_gateway.py::test_an_attached_image_is_sent_as_inline_data_after_the_text`.
- Đã kiểm tra trên bản sao dữ liệu trong trình duyệt:
  - giao diện sáng và tối;
  - màn hình 375 px không tràn ngang;
  - gửi ảnh và xem ảnh trong khung chat;
  - mở lại hội thoại thấy nhãn 📎.
- **Chưa kiểm tra:** giọng nói thật, vì trình duyệt kiểm thử chặn micro; chỉ kiểm tra được thông báo khi micro bị chặn. Nhóm cần thử trên Chrome hoặc Edge thật.

---

## Bổ sung 14/11/2026 · Phiên bản 5.27.1: hình chào mừng mới của Trợ lý AI

Phần lời chào của Trợ lý AI giờ dùng hình nhóm gửi: robot vẫy tay trong vòng sáng xanh tím.

- Tệp hình: `frontend/img/ai-welcome.webp`, giữ nguyên ảnh gốc 1024×572.
- Hình được hiển thị trọn vẹn, đúng tỉ lệ, bo góc nhẹ.
- Hình robot tròn cũ `ai-mascot.webp` vẫn được giữ cho các chỗ khác.

---

## Bổ sung 14/11/2026 · Phiên bản 5.27.2: màu Trợ lý AI theo màu chung của đồ án

Khung Trợ lý AI bỏ bảng màu tím pastel riêng và dùng lại các biến màu chung trong `app.css`, nên tự khớp ở cả giao diện sáng và tối.

| Thành phần | Màu dùng |
|---|---|
| Nền khung | `--navy-50`, `--canvas` |
| Thẻ, viền | `--surface`, `--border` |
| Chữ | `--text`, `--muted` |
| Thanh trên | `--bar` (giống thanh trên của ứng dụng) |
| Nút gửi, bong bóng câu hỏi | `--brand` (xanh thương hiệu) |
| Nút Đóng, micro đang nghe | `--bad` |
| Các nút gợi ý | sắc màu `--s1`…`--s5`, `--good`, `--brand` (cùng bộ màu với ô biểu tượng ở Bảng điều khiển) |

---

## Bổ sung 14/11/2026 · Phiên bản 5.27.3: hiệu ứng "AI đang trả lời"

Khi AI đang xử lý câu hỏi, bong bóng trả lời không còn vòng xoay và chữ "Đang xử lý..." nữa. Thay vào đó là **3 chấm nhấp nhô lần lượt như làn sóng**, giống Messenger.

- **Chuyển động:** mỗi chấm nảy lên rồi rơi xuống, chấm sau chậm hơn chấm trước 0,15 giây. Một vòng dài 1,2 giây.
- **Trình đọc màn hình:** vẫn đọc "Đang xử lý..." qua lớp `.sr-only` mới thêm.
- **Chế độ giảm chuyển động:** máy bật chế độ này thì 3 chấm vẫn nhấp nhô, chỉ nảy thấp hơn một nửa, để người dùng vẫn biết AI đang làm việc.

---

## Bổ sung 14/11/2026 · Phiên bản 5.27.4: hiệu ứng rê chuột ở thanh trên Trợ lý AI

- **Lỗi:** nút "+ Mới" không đổi gì khi rê chuột, vì quy tắc riêng của nút này ghi đè quy tắc rê chuột chung.
- **"+ Mới" khi rê chuột:** chuyển dần sang nền xanh thương hiệu, chữ trắng, có bóng đổ, nhích lên 1 px. Dấu + xoay 90°.
- **"Lịch sử", "Đóng":** khi rê chuột thì nhích lên nhẹ, đổi nền như trước. Khi bấm, nút hơi lún xuống.
- **Chế độ giảm chuyển động:** không nhích, không xoay, nhưng màu vẫn chuyển dần nên vẫn thấy rõ hiệu ứng.

---

## Bổ sung 14/11/2026 · Phiên bản 5.27.5: robot chớp mắt ở nút "Trợ lý"

Ảnh robot trên nút nổi "Trợ lý" (góc dưới bên phải) giờ chớp mắt, cùng nhịp với robot ở banner Bảng điều khiển.

- **Ảnh mới:**
  - `frontend/img/ai-avatar-open.webp`: mắt mở;
  - `frontend/img/ai-avatar-closed.webp`: mắt nhắm hình vòng cung.

  Hai ảnh được dựng từ cặp `ai-head-open/closed.webp` với cùng một khung cắt, nên chỉ có đôi mắt thay đổi. Cách dựng giống ảnh đại diện AI hiện có: khuôn mặt nằm ngang trên nền tròn xanh nhạt.
- **Hiệu ứng:** ảnh mắt nhắm hiện thoáng qua mỗi 1,5 giây (dùng lại keyframe `hero-blink`).
- **Chế độ giảm chuyển động:** hiệu ứng vẫn chạy, vì chỉ là đổi ảnh nhanh tại chỗ, không có vật thể di chuyển.
- Các chỗ khác (thanh tiêu đề, từng câu trả lời) vẫn dùng ảnh tĩnh `ai-avatar.webp`.

---

## Bổ sung 14/11/2026 · Phiên bản 5.27.6: thanh tiêu đề Trợ lý AI thẳng hàng với thanh điều hướng

- **Lỗi:** thanh tiêu đề khung chat AI thấp hơn thanh điều hướng của ứng dụng, nên hai đường viền dưới bị lệch nhau.
- **Cách sửa:**
  - `assistant.js` đo chiều cao thật của thanh điều hướng và ghi vào biến CSS `--topbar-h`.
  - Thanh tiêu đề khung chat dùng đúng chiều cao đó, cùng màu nền và đường viền.
  - Khi thanh điều hướng đổi kích thước (thu nhỏ cửa sổ, xuống dòng), số đo được cập nhật ngay (`ResizeObserver`).
- **Kết quả đo:** ở cửa sổ 1400 px, đáy hai thanh trùng nhau, cùng ở 70,25 px.

---

## Bổ sung 14/11/2026 · Phiên bản 5.28.0: trình bày câu trả lời và ô số liệu của Trợ lý AI

### Ô số liệu ("Skill Gap theo hệ thống", "Kỹ năng đã xác thực"…)

- **Lỗi cũ:** tên kỹ năng dài không được xuống dòng nên đẩy cột giá trị bị vỡ từng chữ ("Mứ / c 0 / mụ / c…") và gây thanh cuộn ngang.
- **Bố cục mới:**
  - Tên kỹ năng ở bên trái, được xuống dòng.
  - Giá trị ở bên phải, không bao giờ bị cắt.
  - Mỗi dòng có thanh nhỏ bên dưới:
    - Coverage và Readiness: thanh phần trăm.
    - Kỹ năng: 3 ô mức. Ô xanh đậm là mức đã đạt, ô viền là phần còn thiếu tới mục tiêu. Đạt mục tiêu thì chuyển xanh lá.
- **Thanh vẽ từ số thật:** `career_context._card` gửi kèm số gốc (`level`, `target`, `scale`, `percent`). Chữ hiển thị không đổi, giao diện không tự tính gì.
- **Tên kỹ năng:** "Kỹ năng đã xác thực" hiện tên kỹ năng thay vì mã (SQL, DATA_VIZ…).

### Cách trình bày câu trả lời

- **Bộ hiển thị mới:** nhận một tập Markdown nhỏ, an toàn:
  - tiêu đề in đậm;
  - gạch đầu dòng `- `;
  - danh sách đánh số `1.`;
  - đường kẻ ngang `---`;
  - chữ **đậm**, *nghiêng*, `mã`;
  - mã nguồn [S1].

  Văn bản luôn được escape trước, nên HTML trong câu trả lời không chạy được.
- **Bố cục câu trả lời tác vụ:** một câu mở đầu, phần **Điểm chính**, đường kẻ, rồi **Bước tiếp theo**. Khi chọn tiếng Anh thì dùng "Key points" và "Next steps".
- **Câu trả lời tra cứu (không qua AI):** mỗi ý mở đầu bằng tên kỹ năng in đậm. Trước đây 5 dòng giống hệt nhau, không biết dòng nào nói kỹ năng nào.
- **Chỉ dẫn cho AI:** yêu cầu dùng tiêu đề in đậm, gạch đầu dòng, đánh số cho các bước, in đậm từ khóa và `---` để ngăn phần; không viết đoạn dài liền.

### Kiểm thử

- 3 test mới trong `tests/test_ai_assistant.py`:
  - ô số liệu mang đúng số của `/me/gap`;
  - kỹ năng đã xác thực hiện tên, không hiện mã;
  - bố cục câu trả lời tác vụ.
- Đã kiểm tra trong trình duyệt hai tác vụ "Tư vấn mức sẵn sàng" và "Phân tích kỹ năng", ở giao diện sáng và tối: không còn thanh cuộn ngang.
- Đã kiểm tra bộ hiển thị bằng Node với danh sách số, chữ nghiêng, mã và thẻ HTML (bị escape).
- Toàn bộ test: 1067 passed, 10 skipped.

---

## Bổ sung 14/11/2026 · Phiên bản 5.28.1: AI nhắm mắt lâu hơn

Mọi khuôn mặt AI có hiệu ứng động giờ chớp mắt theo cùng một nhịp: **mở mắt khoảng 1,5 giây, nhắm mắt khoảng 1,5 giây**, một vòng 3 giây. Mỗi lần đổi có một nhịp mờ ngắn để không bị giật.

Áp dụng cho:
- robot ở banner Bảng điều khiển (`.hero-bot-blink`);
- robot trong các hình minh họa (`.il-bot-blink`, trước đây là vòng 7 giây);
- nút nổi "Trợ lý" (`.fab-blink-closed`).

Ghi chú kỹ thuật:
- Hiệu ứng dùng keyframe mới `ai-blink-slow`.
- Đo trong trình duyệt ở các mốc 0,7 s và 1,3 s thì mắt mở, ở 1,6 s và 2,8 s thì mắt nhắm.
- Vẫn chạy khi máy bật chế độ giảm chuyển động, vì chỉ là đổi hình tại chỗ.

---

## Bổ sung 14/11/2026 · Phiên bản 5.28.2: sửa ô "JD đang dùng" trong Phân tích JD

### Ô số liệu

- **Lỗi:** tên JD dài ở cột giá trị không được xuống dòng, làm chữ "Tên" bị ép thành từng chữ cái theo hàng dọc ("T / ê / n") và tên JD tràn ra ngoài ô.
- **Cách sửa:**
  - Giá trị dài hơn 24 ký tự (như tên JD) được đặt xuống dưới nhãn và trải hết chiều rộng ô.
  - Giá trị ngắn ("Có", "5", "Mức 0 / mục tiêu 3") vẫn nằm cùng hàng bên phải.
  - Cột nhãn luôn rộng tối thiểu khoảng 6,5 chữ, nên không còn bị bóp thành từng chữ cái.

### Tiêu đề trong câu trả lời

- Dòng ngắn kết thúc bằng dấu hai chấm (như "Bước tiếp theo:") nay hiển thị thành tiêu đề in đậm.
- `**Điểm chính:**` cũng được hiển thị thành tiêu đề.
- Câu dài có dấu hai chấm ở giữa vẫn là đoạn văn bình thường.

### Kiểm tra

- Trong trình duyệt, tác vụ "Phân tích JD của tôi" không còn thanh cuộn ngang và không có chữ nào tràn khỏi ô.

---

## Bổ sung 14/11/2026 · Phiên bản 5.28.3: AI mở mắt 1 giây, nhắm mắt 1 giây

- **Nhịp chớp mắt:** mở mắt khoảng 1 giây rồi nhắm mắt khoảng 1 giây, lặp lại mỗi 2 giây. Trước đây (5.28.1) là 1,5 giây mỗi trạng thái.
- **Áp dụng cho:** robot ở banner Bảng điều khiển, robot trong hình minh họa và nút "Trợ lý".
- **Đo trong trình duyệt:** cả ba đều mở mắt ở 0,5 s và 0,9 s, nhắm mắt ở 1,1 s và 1,9 s.
- **Chế độ giảm chuyển động:** hiệu ứng vẫn chạy.

---

## Bổ sung 14/11/2026 · Phiên bản 5.29.0: kiểm thử và làm lại phần Nhắc nhở

### Kết quả kiểm thử phần cũ

55 test có sẵn của phần nhắc nhở đều đạt. Thử thêm bằng các ca mới thì tìm ra 6 lỗi:

| # | Lỗi | Cách sửa |
|---|---|---|
| 1 | Một bài học hiện cùng lúc hai nhắc "Sắp đến hạn" và "Quá hạn" sau khi qua ngày dự kiến. | Khi quét, nhắc không còn đúng với kế hoạch được đóng lại (`SUPERSEDED`). |
| 2 | Lộ trình sang phiên bản mới nhưng nhắc của kế hoạch cũ vẫn nằm lại. | Cùng cơ chế trên: nhắc của phiên bản cũ được đóng. |
| 3 | Tắt một loại nhắc trong thiết lập nhưng nhắc loại đó đang hiện vẫn còn. | Tắt thì ẩn ngay (`MUTED`); bật lại thì hiện lại nếu còn đúng. |
| 4 | Nhắc đã bấm "Đã xem" vẫn bấm "Nhắc lại sau" được và tự sống lại. | Chỉ nhắc đang hiện hoặc đang hoãn mới thao tác được; còn lại trả 409. |
| 5 | Ngày trong nội dung viết kiểu `2026-11-15`. | Viết `15/11/2026`, kể cả nhắc cũ đã lưu. |
| 6 | Chỉ hoãn được đúng 1 ngày, không xem lại hay gọi lại được nhắc đã hoãn. | Thêm lựa chọn 1, 3, 7 ngày và nút "Nhắc lại ngay". |

Không lỗi: phân quyền (tài khoản khác nhận 404), giới hạn số ngày hoãn (1 đến 30), mini-test đến hạn không bỏ qua được, hoãn rồi quay lại đúng dòng cũ.

### Chức năng mới ở máy chủ

- `POST /me/reminders/{id}/resume`: đưa nhắc đang hoãn trở lại danh sách.
- `POST /me/reminders/dismiss-all`: đánh dấu đã xem tất cả, trừ mini-test đến hạn.
- `GET /me/reminders` trả thêm cho mỗi nhắc:
  - `state`: `OVERDUE`, `DUE_SOON`, `MINI_TEST` hoặc `UNSCHEDULED`;
  - `days`: số ngày còn lại (âm là quá hạn), tính theo múi giờ của người dùng;
  - `activity_id`, `activity_title`, `can_dismiss`.
- Danh sách được xếp sẵn: quá hạn, ôn tập đến hạn, sắp đến hạn, lịch cần xem lại.
- Thêm `counts` theo loại và `overdue_count`.
- Giao diện không tự tính ngày hay trạng thái.

### Giao diện mới

- **Dải tóm tắt:** một câu nói rõ còn bao nhiêu việc và bao nhiêu việc quá hạn, kèm 4 ô số (cần xử lý, tạm hoãn, lịch ôn sắp tới, mini-test chờ làm).
- **Hộp việc cần xử lý:**
  - Bộ lọc: Tất cả, Ôn tập, Hạn bài học, Lịch học, mỗi nhóm có số đếm.
  - Mỗi nhắc là một thẻ có màu theo mức gấp: đỏ là quá hạn, vàng là sắp đến hạn, xanh là ôn tập.
  - Nhãn trạng thái ghi rõ "Quá hạn 6 ngày", "Còn 1 ngày", "Đến hạn hôm nay".
  - Nút chính dẫn thẳng tới việc cần làm: "Mở bài học", "Làm ngay" hoặc "Xem lộ trình".
  - "Nhắc lại sau" mở danh sách chọn: ngày mai, sau 3 ngày, sau 1 tuần.
  - "Đã xem" cho từng nhắc và "Đánh dấu tất cả đã xem".
- **Đang tạm hoãn:** liệt kê từng nhắc, ngày sẽ nhắc lại và nút "Nhắc lại ngay".
- **Cột bên:** lịch ôn tập sắp tới, mini-test, và công tắc bật tắt từng loại nhắc (lưu ngay khi bấm).
- **Chuông ở thanh trên:** bấm vào mở danh sách nhanh 5 việc gấp nhất, mỗi dòng dẫn tới việc cần làm. Số trên chuông cập nhật ngay sau mỗi thao tác.
- Có giao diện tối, màn hình điện thoại và bản tiếng Anh (45 chuỗi mới trong `en.json`).

### Tệp chính

- `backend/learning_cycle_service.py`, `backend/api/learning_cycle.py`
- `frontend/js/pages/progress.js`, `frontend/js/reminders.js` (mới), `frontend/js/main.js`, `frontend/index.html`, `frontend/css/app.css`
- `tests/test_reminders_v529.py` (mới, 11 test)

### Kiểm thử

- Trình duyệt, trên bản sao dữ liệu có 3 nhắc thật: lọc, hoãn 3 ngày, nhắc lại ngay, tắt và bật một loại nhắc, đã xem, đã xem tất cả, chuông; giao diện sáng, tối và màn hình 375 px không tràn ngang.
- **Chưa thử trong trình duyệt:** thẻ ôn tập đến hạn ("Làm ngay") và thẻ lịch cần xem lại, vì bản sao không có nhắc loại này. Hai loại này được kiểm bằng test tự động.

---

## Bổ sung 14/11/2026 · Phiên bản 5.30.0: làm lại "Thay đổi mức kỹ năng" và "Nhật ký hoạt động"

### Kết quả kiểm thử phần cũ

Dữ liệu trả về đúng và đúng tài khoản, nhưng cách hiển thị có 7 lỗi:

| # | Lỗi | Cách sửa |
|---|---|---|
| 1 | Biểu đồ: các kỹ năng cùng mức ở cùng thời điểm vẽ chồng lên nhau, 5 kỹ năng chỉ thấy 1 điểm. | Bỏ biểu đồ đường; mỗi kỹ năng một dòng riêng có thanh mức. |
| 2 | Nhật ký hiện mã thô `GOAL_CHANGED`, `GOAL_CHANGE_STARTED`. | Thêm tên tiếng Việt. Sự kiện lạ vào nhóm "Khác", không bị mất. |
| 3 | Nguồn `FINAL_ASSESSMENT` hiện mã thô. | Hiện "Bài đánh giá tổng hợp". |
| 4 | Dòng nhật ký chứa mã bài và mã trạng thái: "ACT_SQL_01: IN_PROGRESS (1%)". | Hiện tên bài học và "đang học", cả dòng cũ lẫn dòng mới. |
| 5 | Nhật ký chỉ hiện 30 dòng mới nhất, không lọc, không xem tiếp được. | Lọc theo nhóm và nút "Xem thêm", mỗi lần 20 dòng. |
| 6 | Bảng mức kỹ năng hiện mã bài `EXAM-2ACC13DC`, không cho biết mức tăng hay giảm. | Mỗi lần ghi nhận hiện ngày, nguồn, điểm và bước "Mức 1 → 2". |
| 7 | Cả hai mục bị thu gọn ở cuối trang, phải bấm mới thấy. | Hai thẻ mở sẵn, đặt cạnh nhau. |

### Máy chủ

- `GET /me/skill-progress`: mỗi kỹ năng có mức hiện tại, mức đầu, thay đổi, mục tiêu JD, đạt hay chưa, và từng lần ghi nhận kèm bước so với lần trước.
- `GET /me/activity-log?group=&limit=&offset=`: mới nhất trước, lọc theo nhóm (Quy trình, Đánh giá, Học tập, Nhắc nhở, Khác), có số đếm từng nhóm và `has_more`.
- Hai đường dẫn cũ `/me/history` và `/me/skill-history` giữ nguyên.
- Giao diện không tự tính mức, bước hay số đếm.

### Giao diện

- **Thay đổi mức kỹ năng:**
  - Ba ô tóm tắt: số kỹ năng đã tăng mức, số kỹ năng đạt mục tiêu JD, số lần ghi nhận.
  - Mỗi kỹ năng một dòng: tên, "Mức 0 / mục tiêu 3", thanh 3 ô, nhãn "Tăng 1 mức", "Giảm 1 mức" hoặc "Chưa đổi".
  - Bấm vào dòng để xem từng lần ghi nhận.
- **Nhật ký hoạt động:**
  - Dòng thời gian gom theo ngày, mỗi nhóm một màu và biểu tượng.
  - Bộ lọc theo nhóm có số đếm; chỉ hiện nhóm có dữ liệu.
  - Cuối danh sách ghi "Đang hiện 20/45 hoạt động" và nút "Xem thêm".

### Kiểm thử

- `tests/test_history_v530.py` (mới, 15 test): thứ tự, số đếm cộng đúng tổng, phân trang không sót không lặp, sự kiện lạ, dòng cũ được làm sạch, truy vấn sai trả 422, phân quyền, mức khớp trang Khoảng cách kỹ năng, bước tăng giảm.
- Trình duyệt trên bản sao dữ liệu: 5 kỹ năng, mở chi tiết, lọc nhóm Học tập; giao diện sáng, tối, màn hình 375 px không tràn ngang.
- **Chưa thử trong trình duyệt:** nút "Xem thêm" (tài khoản thử chỉ có 10 hoạt động) và nhãn tăng, giảm mức (tài khoản thử chưa đổi mức). Cả hai được kiểm bằng test tự động.

---

## Bổ sung 14/11/2026 · Phiên bản 5.30.1: căn đều các ô trong phần Nhắc nhở

- **Cột thẳng hàng:** hai hàng (hộp việc cần xử lý + cột bên; nhật ký + mức kỹ năng) dùng chung tỉ lệ cột 3 : 2. Trước đây hàng trên chia 637/374 px, hàng dưới chia 506/506 px nên khe giữa hai hàng lệch nhau.
- **Đáy bằng nhau:** các ô trong cùng một hàng kết thúc trên cùng một đường. Đo ở cửa sổ 1360 px: hàng trên cùng kết thúc ở 1102 px, hàng dưới cùng ở 1922 px (trước đây lệch 62 px và 112 px).
- **Thứ tự hàng dưới:** Nhật ký hoạt động nằm ở cột rộng bên trái, Thay đổi mức kỹ năng ở cột hẹp bên phải.
- **Đồng bộ bên trong ô:** cùng lề 20 px, cùng cỡ tiêu đề 16 px, cùng chiều cao hàng tiêu đề, ô trống cùng chiều cao tối thiểu. Thẻ nhắc cao tối thiểu 148 px, hàng nút luôn nằm sát đáy thẻ.
- **Bốn ô số ở dải tóm tắt:** cùng rộng 132 px, cùng cao 108 px.
- Chỉ sửa CSS và thứ tự hai ô; không đổi chức năng.

---

## Bổ sung 14/11/2026 · Phiên bản 5.31.0: Nhật ký và Mức kỹ năng chỉ hiện khi bấm nút

- **Hai nút ở cuối phần Nhắc nhở:** "Nhật ký hoạt động" và "Thay đổi mức kỹ năng". Mỗi nút ghi sẵn số lượng (ví dụ "10 hoạt động", "5 kỹ năng") và chữ "Xem" hoặc "Ẩn".
- **Mặc định đóng cả hai.** Trang ngắn lại từ khoảng 2040 px xuống 1240 px ở cửa sổ 1360 px.
- **Bấm nút:** mục tương ứng hiện ra ngay bên dưới và trang cuộn tới đó. Bấm lần nữa để ẩn.
- **Mở một mục:** mục đó trải hết chiều ngang. **Mở cả hai:** nằm cạnh nhau theo tỉ lệ 3 : 2 như trước.
- **Giữ lựa chọn:** khi trang tự tải lại sau một thao tác (hoãn nhắc, đã xem…), mục đang mở vẫn mở. Tải lại cả trang thì về mặc định đóng.
- Nút có `aria-expanded` và `aria-controls` cho trình đọc màn hình.
- Chức năng bên trong hai mục (lọc, xem thêm, mở từng kỹ năng) không đổi.

---

## Bổ sung 15/11/2026 · Phiên bản 5.32.0: kiểm định toàn hệ thống

Báo cáo đầy đủ: `CAREERADAPT_AI_FULL_SYSTEM_AUDIT_REPORT.md`. Bản sao lưu: `CareerAdapt_AI_backup_truoc_kiem_dinh_toan_dien_20261115`.

Bảy lỗi đã sửa:

1. **HIGH:** code chỉ "chạy được" (`SELECT 1`, `print`) vẫn có điểm. Nay tiêu chí nền chỉ tính khi có tiêu chí về yêu cầu của đề đạt.
2. **HIGH:** `print(df)` qua tiêu chí "kết quả in ra đúng" và cho mức 1 Python. Nay con số chỉ tính trên dòng kết quả.
3. **HIGH:** tiến độ ở Bảng điều khiển, Báo cáo và trợ lý AI tính cả bài tự đánh dấu hoàn thành. Nay dùng `verified_progress_percent`.
4. **MEDIUM:** câu "chưa rõ… nên trả lời đại" có điểm ở bài viết. Nay bài chỉ nói không biết không được tính.
5. **MEDIUM:** `POST /me/final-assessment/start` lỗi 500 khi chưa có lộ trình. Nay trả 409.
6. **LOW:** lỗi form quá lớn và đường dẫn không tồn tại không theo khuôn lỗi chung.
7. **LOW:** nhật ký ghi trùng khi gửi lại cùng trạng thái tiến độ.

Test mới: `tests/test_audit_2026_11_15.py` (10 test, gồm 2 test quét toàn bộ đường dẫn API về đăng nhập và quyền quản trị). Toàn bộ: 1103 passed, 10 skipped.

---

## Bổ sung 15/11/2026 · Phiên bản 5.33.0: dải tiêu đề màu cho các mục của Kế hoạch Career Adapt

Năm mục đầu của Kế hoạch Career Adapt có dải tiêu đề màu xanh navy giống mục Nhắc nhở. Mỗi mục có một màu nhấn riêng ở vầng sáng góc phải, vạch trên cùng và nhãn nhỏ, để nhận ra ngay đang ở mục nào.

| Mục | Màu nhấn | Câu tóm tắt | Ô số |
|---|---|---|---|
| Khai báo và JD | Xanh dương | "Mục tiêu: tên JD" | Kỹ năng tự khai, Kỹ năng JD yêu cầu, Ngày hoàn tất |
| Kết quả bài làm | Tím | "Bạn được X/100 điểm, còn thiếu Y điểm để đạt." | Điểm bài làm, Ngưỡng đạt, Kỹ năng đạt JD, Bài đã chấm |
| Khoảng cách kỹ năng | Xanh ngọc | "Còn N kỹ năng chưa đạt mức JD yêu cầu." | Đạt mục tiêu, Còn thiếu, Độ phủ bằng chứng, Mức đáp ứng |
| Lộ trình học tập | Xanh lá | "Bạn đã hoàn thành X/Y bài học." | Tiến độ, Dự kiến hoàn thành, Chờ kiểm tra lại, Ngày chậm lịch |
| Xếp hạng và lương | Vàng | Thẻ xếp hạng hiện có được đổi sang kiểu dải màu | Giữ nguyên các ô và nút của thẻ |

Ghi chú:

- **Nguồn số liệu:** mọi số lấy từ dữ liệu trang đã tải sẵn; không thêm lời gọi API, không đổi máy chủ.
- **Lộ trình học tập:** ba chỉ số cũ chuyển lên dải màu. Thẻ bên dưới chỉ còn "Bài học tiếp theo" và nút mở bài, nên không lặp số.
- **Xếp hạng và lương:** chỉ đổi CSS. Nút "Sao chép để chia sẻ" và công tắc hiện tên vẫn như cũ.
- **Mã nguồn:** hàm dùng chung `pageHero()` nằm trong tệp mới `frontend/js/hero.js`.
- **Tiếng Anh:** thêm 19 chuỗi vào `en.json`.
- **Kiểm tra:** trình duyệt ở 1360 px và 375 px, giao diện sáng và tối; không lỗi script, không tràn ngang.

---

## Bổ sung 15/11/2026 · Phiên bản 5.34.0: nhiều tiến trình, sandbox container, khóa ngoại, test giao diện

Bản sao lưu trước khi đổi: `CareerAdapt_AI_backup_truoc_kien_truc_20261115`.

### 1. Chạy nhiều tiến trình máy chủ

- **Cách bật:** đặt `CAREERADAPT_WORKERS=4` rồi chạy `run.py`. Các tiến trình dùng chung một tệp SQLite.
- **Vấn đề trước đây:** mỗi tiến trình giữ bản sao dữ liệu người học trong bộ nhớ, nên tiến trình này không thấy thay đổi của tiến trình kia và có thể ghi đè lên nhau.
- **Cách giải quyết:**
  - **Bộ đếm phiên bản** (`sync_revisions`): mỗi lần ghi tăng bộ đếm của người học đó, hoặc của nội dung quản trị, hoặc của hàng chờ người duyệt. Đầu mỗi yêu cầu, tiến trình so bộ đếm và nạp lại nếu tiến trình khác vừa đổi.
  - **Khóa theo người học** (`user_locks`): giữ suốt yêu cầu, nên hai yêu cầu của cùng một người học ở hai tiến trình không áp thay đổi lên hai bản sao khác nhau. Trợ lý AI chỉ nạp lại mà không giữ khóa, vì phải chờ AI vài giây và chỉ đọc dữ liệu học viên.
  - **Chấm bài nền:** chỉ giữ khóa của người học lúc ghi kết quả vào hồ sơ; phần chạy code và gọi AI nằm ngoài khóa.
  - **Lease công việc nền** (`work_leases`): mỗi bài chỉ một tiến trình chấm, mỗi phút chỉ một tiến trình chạy việc định kỳ.
- **Khi khóa bận quá lâu:** chờ 25 giây rồi trả 503 kèm `Retry-After`. Tiến trình giữ khóa bị tắt đột ngột thì khóa tự hết hạn sau 120 giây.
- **Kiểm thử** (`tests/test_multiprocess.py`, chạy tiến trình thật):
  - 3 tiến trình cùng tăng một bộ đếm 15 lần: không có khóa thì mất cập nhật, có khóa thì đủ 45/45.
  - Hai máy chủ uvicorn thật dùng chung một cơ sở dữ liệu: ghi qua máy này, đọc qua máy kia thấy ngay, 10 lần ghi xen kẽ đều được giữ.

### 2. Sandbox chạy code trong container

- **Cách bật:** `CAREERADAPT_SANDBOX=docker`; image dựng từ `sandbox/Dockerfile`. Mỗi lần chạy là một container mới với:
  - không mạng, hệ thống tệp chỉ đọc;
  - giới hạn bộ nhớ không swap, CPU, tối đa 64 tiến trình;
  - bỏ mọi quyền Linux, chạy bằng người dùng không đặc quyền;
  - mã worker gắn chỉ đọc; chỉ thư mục tạm của lần chạy được ghi.
- **Fail closed:** chọn `docker` mà thiếu Docker hoặc image thì không chạy code của người học; bài được báo "sandbox chưa sẵn sàng" và chấm lại sau.
- **Các chế độ khác:** `auto` dùng container nếu có, không thì tiến trình con. Mặc định vẫn là `process` như cũ.
- **Kiểm tra lớp trong:** danh sách thư viện cho phép, móc kiểm soát trong worker và giới hạn thời gian vẫn áp dụng bên trong container.
- **Kiểm thử** (`tests/test_container_sandbox.py`):
  - kiểm lệnh `docker run` và hành vi khi thiếu Docker;
  - chạy SQL và Python thật qua một bản thay thế lệnh docker (`tests/fake_docker.py`).
- **Chưa kiểm:** máy phát triển không cài Docker nên chưa chạy container thật. Test container thật tự chạy khi có Docker và image.

### 3. Khóa ngoại cho cơ sở dữ liệu

10 khóa ngoại, tất cả `ON DELETE CASCADE` (giống cách `purge_user` đang xóa):

| Bảng con | Tham chiếu tới |
|---|---|
| `ai_messages` | `ai_conversations` |
| `exam_attempts` | `career_runs` |
| `submission_answers`, `test_case_results`, `rubric_scores`, `ai_feedback_traces`, `final_assessments` | `assessment_attempts` |
| `jd_versions` | `job_descriptions` |
| `jd_requirements` | `jd_versions` (cặp mã JD và phiên bản) |
| `knowledge_chunks` | `knowledge_documents` (cặp mã và phiên bản) |

- **Migration an toàn:**
  - đếm dòng sẽ vi phạm trước; nếu có thì không chạy và ghi lý do vào `meta`, không xóa dữ liệu nào;
  - sao lưu tệp (`.pre-fk1.bak`), dựng lại bảng giữ nguyên mọi dòng và rowid;
  - so số dòng trước và sau từng bảng, chạy `PRAGMA foreign_key_check`; lỗi thì hoàn tác toàn bộ;
  - chạy lại không làm gì thêm.
- **Đã thử trên bản sao của tệp dữ liệu thật:** không mất dòng nào, 0 vi phạm, dòng mồ côi bị từ chối, xóa cuộc trò chuyện thì tin nhắn đi theo.
- **Tệp thật:** sẽ được nâng cấp lần tới khi máy chủ khởi động.
- **Không có khóa ngoại:**
  - mã người dùng trỏ sang tệp `accounts.sqlite3` khác, nên SQLite không ràng buộc được;
  - `exam_responses`, `exam_events` chứa dòng của cả hai loại bài thi.
- **Hai test được sửa phần chuẩn bị dữ liệu, không đổi kỳ vọng:** trước đây chúng ghi bài nộp chỉ trong bộ nhớ (`test_ai_guardrails.py`) hoặc ghi kết quả thiếu dòng bài nộp (`test_insights.py`). Nay chúng ghi dữ liệu giống luồng thật.

### 4. Test giao diện tự động

- **Công cụ:** `tests/test_ui_e2e.py` chạy Microsoft Edge có sẵn qua Playwright, không cần tải trình duyệt. Cài bằng `pip install -r requirements-dev.txt`.
- **Môi trường:** máy chủ thật trên cổng trống với cơ sở dữ liệu tạm; không đụng dữ liệu trong `data/`.
- **23 test:**
  - đăng ký và đăng nhập qua biểu mẫu thật;
  - sai mật khẩu bị từ chối, mật khẩu yếu bị chặn;
  - đăng xuất thu hồi phiên;
  - 7 trang chính mở không lỗi script, không tràn ngang, trên máy tính và điện thoại;
  - nút giao diện quay vòng 3 chế độ; chuông mở và đóng bằng Esc;
  - Trợ lý mở và đóng; menu điện thoại;
  - bắt đầu quy trình Career Adapt.
- **Không có Playwright hoặc trình duyệt:** các test này tự bỏ qua.

### 5. Lỗi khởi động đồng thời (do test nhiều tiến trình phát hiện)

- **Lỗi:** khi hai máy chủ cùng khởi động trên một cơ sở dữ liệu mới:
  - một tiến trình bị lỗi "duplicate column" lúc thêm cột vào bảng tài khoản;
  - hoặc lỗi trùng khóa lúc nạp kho kiến thức mẫu;
  - hoặc lỗi "database is locked" lúc chuyển sang WAL.
- **Cách sửa:** thêm khóa tệp dùng chung giữa các tiến trình (`backend/filelock.py`). Bao quanh phần tạo bảng, migration, nạp dữ liệu mẫu và khởi tạo bảng tài khoản. Kho kiến thức mẫu được nạp trong một giao dịch.
- **Test:** `test_several_processes_can_start_on_a_new_database_at_once` cho 4 tiến trình cùng khởi động. Bộ test nhiều tiến trình chạy 5 lần liên tiếp đều đạt.

### Kết quả kiểm thử

- Toàn bộ: **1138 đạt, 11 bỏ qua** (10 test cần Gemini thật, 1 test cần Docker thật), 0 lỗi.
- **Tệp dữ liệu thật** (`data/careeradapt.sqlite3`) chưa được nâng cấp khóa ngoại, vì máy chủ đang chạy vẫn dùng code cũ. Lần khởi động lại tới, migration tự chạy và tự sao lưu `.pre-fk1.bak` trước khi đổi.

---

## Bổ sung 15/11/2026 · Phiên bản 5.34.1: màu nhấn cho dải tiêu đề Nhắc nhở

- **Thay đổi:** dải tiêu đề của mục Nhắc nhở nay có màu nhấn riêng (hồng san hô `#FB7185`). Màu hiện ở vầng sáng góc phải, vạch trên cùng và nhãn nhỏ, cùng kiểu với năm mục kia.
- **Bảng màu đủ sáu mục:** xanh dương, tím, xanh ngọc, xanh lá, vàng, hồng.
- **Phạm vi:** chỉ thêm lớp `page-hero is-rose` và một dòng CSS; không đổi chức năng.

## Bổ sung 15/11/2026 · Phiên bản 5.35.0: chuyên gia đóng góp câu hỏi

**Vấn đề:** mỗi kỹ năng chỉ có một câu cho mỗi độ khó, nên kết luận mức kỹ năng dựa vào rất ít câu. Chỉ quản trị viên thêm hoặc sửa được câu, và nhóm không muốn AI viết câu vì không kiểm chứng được đáp án.

**Đã thêm:**

- **Quyền đóng góp:** quản trị viên cấp quyền bằng email tài khoản ở tab "Người đóng góp" và thu hồi được bất kỳ lúc nào. Chỉ người được cấp quyền (và quản trị viên) thấy mục "Đóng góp câu hỏi".
- **Hai ngân hàng:** câu tự luận cho bài thi (SQL, Python hoặc bài viết, có test case, cổng lỗi trọng yếu và đáp án mẫu) và câu trắc nghiệm cho bài kiểm tra kiến thức (chọn một, chọn nhiều, số, sắp xếp).
- **Trang đóng góp:** danh sách câu của mình, độ phủ từng ô kỹ năng × độ khó của cả hai ngân hàng, trình soạn có mẫu test case và bản xem trước bộ dữ liệu.
- **Kiểm tra tự động trước khi gửi duyệt:** câu tự luận chạy đáp án mẫu trên 4 bộ dữ liệu A-D (phải đạt 100/100, không chạm cổng lỗi) và chạy các bài sai điển hình phải dưới 40 điểm (SQL: truy vấn không liên quan, lấy toàn bảng; Python: in một dòng chữ, in toàn bảng; bài viết: trả lời đại, chỉ liệt kê từ khóa). Biểu thức chính quy nguy hiểm bị từ chối. Câu trắc nghiệm dùng đúng bộ chấm của bài kiểm tra: đáp án đúng đạt trọn điểm, phương án sai được 0, không trùng phương án, câu sắp xếp đảo ngược không được trọn điểm. Câu trùng hoặc gần trùng câu đã có bị chặn hoặc cảnh báo.
- **Duyệt bốn mắt:** câu đã gửi chỉ quản trị viên duyệt được, và người duyệt phải khác người viết. Yêu cầu sửa hoặc không duyệt phải có nhận xét từ 10 ký tự. Khi duyệt, máy chủ kiểm tra lại toàn bộ rồi mới xuất bản. Mọi bước được ghi lịch sử.
- **Dùng trong bài thi:** bài thi vẫn 1 câu mỗi kỹ năng, rút ngẫu nhiên giữa câu gốc và các câu đã duyệt cùng ô, ưu tiên câu và biến thể người học chưa gặp. Người viết không bao giờ nhận câu của chính mình, cả ở bài thi lẫn bài kiểm tra kiến thức. Quản trị viên ngừng dùng được một câu mà không làm đổi bài đã làm.
- **Xóa tài khoản:** câu chưa xuất bản của người đó bị xóa; câu đã xuất bản được giữ nhưng bỏ tên người viết.

**Dữ liệu:** migration `contrib_schema_version = 1` chỉ thêm 4 bảng mới (`contributors`, `question_contributions`, `contribution_events`, `exam_bank_items`), không sửa bảng cũ. Không thêm câu hỏi nào vào ngân hàng thật; câu dùng khi kiểm thử chỉ nằm trong test và bản sao dữ liệu đã xóa.

**Kiểm chứng:**

- `tests/test_contributions.py`: 26 test.
- Toàn bộ bộ test: 1164 passed, 11 skipped (chạy ngày 15/11/2026, gồm 23 test giao diện trình duyệt). Các test bị bỏ qua là test gọi AI thật và test Docker thật.
- Đã thử trên trình duyệt với bản sao dữ liệu: viết câu, kiểm tra, gửi duyệt, quản trị viên duyệt và xuất bản (độ phủ SQL Cơ bản từ 1 lên 2), cấp và thu hồi quyền, giao diện điện thoại không tràn ngang.

**Chưa làm hoặc chưa kiểm chứng:**

- Ngân hàng thật chưa có câu đóng góp nào; độ tin cậy chỉ tăng khi chuyên gia thật viết câu.
- Câu đóng góp chưa có bản dịch tiếng Anh.
- Kiểm tra tự động chỉ chứng minh đáp án mẫu khớp test case; tính đúng chuyên môn của câu vẫn do người duyệt quyết định.

## Bổ sung 15/11/2026 · Phiên bản 5.36.0: tiếp các phần chưa làm của 5.35

**Kiểm chứng migration trên dữ liệu thật.** Khi kiểm tra, một lệnh đọc của Claude đã nạp mã máy chủ, và việc nạp này chạy migration khóa ngoại (5.34) cùng bảng đóng góp (5.35) lên `data/careeradapt.sqlite3` lúc 22:05 ngày 15/11/2026. Đây đúng là migration mà lần khởi động máy chủ kế tiếp sẽ chạy, và ứng dụng đã tự sao lưu trước tại `data/careeradapt.sqlite3.pre-fk1.bak`. So sánh từng bảng, từng dòng giữa bản sao lưu và cơ sở dữ liệu sau migration (chỉ đọc):

- 45 bảng cũ giống hệt nhau (cùng số dòng, cùng nội dung). Bảng `meta` chỉ thêm 2 khóa phiên bản.
- Thêm 4 bảng mới, đều rỗng.
- `PRAGMA integrity_check` = ok; `PRAGMA foreign_key_check` không có vi phạm; 13 bảng có khóa ngoại.

Migration 5.36 (thêm cột `review_checklist`) chưa chạy trên dữ liệu thật; nó sẽ chạy ở lần khởi động tới. Từ lần này, mọi thử nghiệm cần nạp mã máy chủ đều chạy trên bản sao dữ liệu.

**Bản tiếng Anh cho câu đóng góp (không bắt buộc):**

- Trình soạn có mục "Bản tiếng Anh" liệt kê đúng những chữ người học sẽ đọc: chủ đề, đề bài, gợi ý, mô tả tiêu chí chấm, nhãn lỗi trọng yếu, lựa chọn, giải thích, đơn vị. Mục không có chữ tiếng Việt (số, SQL, code) không bắt buộc dịch.
- Kiểm tra tự động: không có bản dịch thì chỉ cảnh báo. Có bản dịch thì phải đủ mọi mục cần dịch, không còn chữ tiếng Việt, không có mục không còn trong câu (ví dụ đổi mã tiêu chí), không dài bất thường. Sai một điều là không gửi duyệt được.
- Bản dịch chỉ được dùng sau khi duyệt. Máy chủ đọc bản dịch từ cơ sở dữ liệu và ghép vào danh mục tiếng Anh sẵn có; danh mục đã duyệt của nhóm luôn được ưu tiên khi trùng. Bài làm, chấm điểm và dữ liệu lưu vẫn dùng tiếng Việt.

**Sửa lỗi có sẵn:** ở giao diện tiếng Anh, nội dung lựa chọn của câu trắc nghiệm (ví dụ "Báo lỗi") không được dịch dù danh mục đã có bản dịch, vì máy chủ bỏ qua mọi trường `text` để không dịch chữ người học viết. Nay một lựa chọn dạng `{id, text}` được dịch; mọi trường `text` khác vẫn giữ nguyên.

**Danh sách xác nhận của người duyệt:** kiểm tra tự động chỉ chứng minh đáp án mẫu qua tiêu chí chấm, nên trước khi bấm duyệt, người duyệt phải đánh dấu: đã tự giải câu và đáp án đúng chuyên môn; đề rõ ràng, đủ dữ kiện; độ khó khớp mức; không lộ đáp án hay chứa thông tin cá nhân; và (nếu có) bản tiếng Anh cùng nghĩa. Máy chủ từ chối duyệt khi thiếu một mục, và lưu các mục đã xác nhận cùng người duyệt, thời điểm. Yêu cầu sửa hoặc không duyệt không cần danh sách này.

**Dữ liệu:** `contrib_schema_version = 2` chỉ thêm một cột cho phép rỗng; dòng cũ giữ nguyên. Có test dựng cơ sở dữ liệu phiên bản 1 có sẵn dòng rồi nâng cấp hai lần.

**Kiểm chứng:**

- `tests/test_contributions.py`: 40 test (thêm 14).
- Toàn bộ bộ test: 1178 passed, 11 skipped (bỏ qua: AI thật, Docker thật).
- Thử trên trình duyệt với bản sao dữ liệu (đã xóa): bản dịch thiếu bị chặn với thông báo rõ; dịch đủ thì qua; người duyệt bấm duyệt khi chưa đánh dấu thì bị nhắc; đánh dấu đủ thì xuất bản và lưu 5 xác nhận; một tài khoản khác tác giả làm bài kiểm tra kiến thức tiếng Anh và nhận đúng câu mới bằng tiếng Anh, kể cả lựa chọn "None of these clauses".

**Vẫn chưa làm được (cần người):**

- Ngân hàng thật chưa có câu đóng góp nào; chỉ chuyên gia thật mới bổ sung được.
- Hệ thống không tự đánh giá được bản dịch có đúng nghĩa hay câu có đúng chuyên môn; việc đó do người duyệt xác nhận.

## Bổ sung 16/11/2026 · Phiên bản 5.37.0: giao diện đăng nhập mới

**Sao lưu trước khi sửa:** `CareerAdapt_AI_backup_truoc_dang_nhap_20261115` (thư mục cùng cấp, không gồm `.venv`).

**Thay đổi giao diện (`frontend/login.html`, `frontend/css/login.css`):**

- Viết lại `login.css` thành một lớp duy nhất với bộ màu chung của ứng dụng (cùng xanh `#1D5BD8`, nền và viền như `app.css`), thay cho nhiều lớp CSS vá chồng qua các phiên bản. Chế độ sáng và tối dùng cùng một bộ biến.
- Chữ lớn hơn và dễ đọc hơn: chữ thường 15px, nhãn 13,5px, tiêu đề 28px (trước 11-12px). Ô nhập cao 48px, nút đăng nhập rộng hết khung, cao 50px.
- Biểu tượng SVG thật cho email, mật khẩu, họ tên, ẩn/hiện mật khẩu, thay cho các ký tự @ ⌑ ◉.
- Nút ẩn/hiện mật khẩu thành biểu tượng con mắt; nhãn "Hiện/Ẩn" vẫn có cho trình đọc màn hình.
- "Quên mật khẩu?" chuyển lên cạnh nhãn Mật khẩu.
- Nút gửi hiện vòng xoay trong lúc chờ máy chủ.
- Cảnh báo "Caps Lock đang bật" ở các ô mật khẩu.
- Cột giới thiệu: nền xanh navy như thanh bên của ứng dụng, lưới mờ vẽ bằng CSS, ba điểm nổi bật có biểu tượng. Điểm thứ ba ("Dữ liệu do bạn quản lý: tải về hoặc xóa hồ sơ bất cứ lúc nào") đúng với chức năng tải và xóa dữ liệu đã có.
- Nút giao diện và VI/EN nằm trong một thanh công cụ, không còn đặt vị trí tuyệt đối theo từng cỡ màn hình.
- Trên điện thoại: ẩn cột giới thiệu, hiện logo nhỏ ở thanh công cụ; nút đạt 44px trên màn hình cảm ứng.
- Tôn trọng chế độ giảm chuyển động của hệ điều hành.

**Không đổi:** toàn bộ logic đăng nhập, đăng ký, quên và đặt lại mật khẩu, CSRF, danh sách kiểm tra mật khẩu, cùng mọi id và thuộc tính mà `login.js` và test dùng. `login.js` chỉ thêm phần đổi biểu tượng con mắt và cảnh báo Caps Lock. Thêm 3 chuỗi mới cho cả tiếng Việt và tiếng Anh trong `i18n.js`.

**Kiểm chứng:**

- Toàn bộ bộ test: 1178 passed, 11 skipped, gồm các test trình duyệt thật cho đăng ký, đăng nhập, sai mật khẩu và đăng xuất trên trang mới.
- Đã xem trên trình duyệt (bản sao dữ liệu): máy tính chế độ sáng và tối, form đăng ký với danh sách kiểm tra mật khẩu, nút con mắt, điện thoại 375px tiếng Anh không tràn ngang, cảnh báo Caps Lock.

**Chưa kiểm chứng:** cảnh báo Caps Lock mới thử bằng sự kiện bàn phím giả lập, chưa thử với bàn phím thật; chưa thử trên Safari.

## Bổ sung 16/11/2026 · Phiên bản 5.38.0: robot CareerAdapt AI trên trang đăng nhập

**Vị trí:** đầu khung đăng nhập, phía trên tiêu đề, kèm một bong bóng lời thoại. Dùng hai ảnh đầu robot sẵn có (`ai-head-open.webp`, `ai-head-closed.webp`), chỉ khác nhau ở mắt. Không thêm ảnh hay thư viện mới.

**Chuyển động và phản ứng (`frontend/js/login-bot.js`, phần cuối `frontend/css/login.css`):**

- Xuất hiện bằng một cú bật nhẹ khi mở trang; bong bóng hiện ngay sau đó.
- Lúc rảnh: bay lơ lửng chậm, bóng dưới chân co giãn theo, chớp mắt tự nhiên (thỉnh thoảng chớp hai lần).
- Liếc theo con trỏ chuột (chỉ trên máy có chuột), và quay về phía ô đang nhập.
- Gật đầu nhẹ khi gõ email hoặc họ tên.
- Nhắm mắt khi gõ mật khẩu; mở mắt và nhắc để ý xung quanh nếu bấm hiện mật khẩu.
- Nhắc khi Caps Lock đang bật.
- Lắc lư "suy nghĩ" trong lúc chờ máy chủ; lắc đầu và đổi bong bóng sang màu đỏ khi có lỗi; nhảy lên vui vẻ khi có thông báo thành công.
- Mỗi form (đăng nhập, tạo tài khoản, quên mật khẩu, đặt lại mật khẩu) có lời chào riêng. Đổi VI/EN thì câu đang nói đổi theo.
- Hệ điều hành bật "giảm chuyển động": robot đứng yên, chỉ còn chớp mắt.

**Nguyên tắc:** robot chỉ phản ứng theo những gì trang đã làm; không đổi logic đăng nhập và không quyết định gì. Robot được đánh dấu `aria-hidden`; thông báo của form vẫn là nội dung trình đọc màn hình đọc. Lời thoại không có số liệu hay hứa hẹn ngoài chức năng có thật (ví dụ email dùng để lấy lại mật khẩu). 14 câu thoại có cả tiếng Việt và tiếng Anh trong `i18n.js`.

**Sửa kèm:** Edge vẽ thêm nút con mắt riêng trong ô mật khẩu, nên có hai nút cạnh nhau; đã ẩn nút của trình duyệt.

**Lưu ý thiết kế:** nhịp chớp mắt ở đây là chớp nhanh tự nhiên, khác nhịp 1 giây mở / 1 giây nhắm của robot trong ứng dụng, để trạng thái "nhắm mắt khi gõ mật khẩu" nhìn rõ là một phản ứng.

**Kiểm chứng:**

- Toàn bộ bộ test: 1178 passed, 11 skipped (gồm các test trình duyệt thật cho đăng nhập và đăng ký).
- Chạy kịch bản Playwright trên Edge thật với bản sao dữ liệu: liếc theo chuột, câu thoại khi nhập email, nhắm mắt khi nhập mật khẩu, câu nhắc khi hiện mật khẩu, lắc đầu và bong bóng đỏ khi sai mật khẩu, đổi lời khi chuyển form và đổi ngôn ngữ, điện thoại không tràn ngang, chế độ giảm chuyển động vẫn hiện robot. Đã xem ảnh chụp ở chế độ sáng, tối và điện thoại.

**Chưa kiểm chứng:** Caps Lock bằng bàn phím thật; Safari.

## Bổ sung 16/11/2026 · Phiên bản 5.39.0: robot AI ở trang chủ được vẽ lại

**Vấn đề:** đầu robot là ảnh minh họa chi tiết, nhưng thân, tay và ô "AI" là các khối CSS phẳng, nên hai phần trông như hai phong cách khác nhau.

**Thay đổi (`frontend/js/pages/dashboard.js`, cuối `frontend/css/app.css`):**

- Thân mới là hình SVG vẽ cùng phong cách với đầu: viền xanh navy đậm, vỏ trắng bóng có đổ bóng và điểm sáng, khớp vai xanh giống tai nghe, cánh tay có bàn tay, khăn quàng và áo choàng xanh navy như bản linh vật đầy đủ.
- Màn hình "AI" trên ngực phát sáng, có vệt quét sáng chạy ngang; ba đèn LED sáng lần lượt; luồng sáng dưới chân vì robot bay lơ lửng.
- Quầng sáng sau đầu và một vòng quỹ đạo nét đứt có chấm sáng chạy quanh.
- Chuyển động: bay lơ lửng (bóng dưới chân co lại khi bay lên), đầu nghiêng nhẹ lệch nhịp với thân, tay phải vẫy chào định kỳ, áo choàng đung đưa; rê chuột vào thì robot vẫy ngay. Mắt giữ nhịp 1 giây mở / 1 giây nhắm như trước.
- Bật giảm chuyển động: chỉ còn chớp mắt (đã kiểm tra bằng trình duyệt).
- Xóa khối CSS thân cũ (5.26.1). Không thêm ảnh hay thư viện.

**Kiểm chứng:** toàn bộ bộ test 1178 passed, 11 skipped. Chụp màn hình bằng Playwright trên Edge thật (bản sao dữ liệu) ở chế độ sáng, tối và khi đang vẫy tay; không có lỗi console.

## Bổ sung 16/11/2026 · Phiên bản 5.40.0: kiểm tra lại và nâng cấp trang Quản trị nội dung

**Sao lưu trước khi sửa:** `CareerAdapt_AI_backup_truoc_quan_tri_20261116` (thư mục cùng cấp, không gồm `.venv`).

**Cách kiểm tra:** chạy máy chủ trên bản sao dữ liệu, dùng Playwright trên Edge thật đăng nhập bằng một quản trị viên chỉ có trong bản sao, mở lần lượt 11 mục, ghi lỗi console và yêu cầu lỗi, mở các form, lưu thử, chụp màn hình máy tính, điện thoại, chế độ tối.

**Lỗi tìm thấy và đã sửa:**

| # | Lỗi | Sửa |
|---|---|---|
| A1 | Không lưu được kỹ năng tùy chọn STATISTICS: form đòi trọng số tối thiểu 0,01 trong khi máy chủ cho phép 0. Bấm Lưu không có phản hồi. | Form nhận 0 và giải thích "0 là kỹ năng tùy chọn". |
| A2 | Form thêm mẫu hiệu chỉnh ghi cứng 5 kỹ năng, thiếu STATISTICS. | Lấy danh sách kỹ năng từ máy chủ. |
| A3 | Bảng phân tích câu hỏi đọc sai tên trường nên cột số lượt luôn hiện "—"; nhận định của máy chủ ("Chưa đủ dữ liệu", "Quá khó"...) không hiện; bảng tự cắt ở 80 dòng. | Đọc đúng `exposures`, thêm cột Đánh giá, hiện đủ dòng kèm tìm kiếm và lọc theo kỹ năng. |
| A4 | JD và học liệu đã duyệt vẫn có nút "Duyệt"; đã hết hiệu lực hoặc đã ẩn vẫn có nút tương ứng. | Chỉ hiện các thao tác hợp với trạng thái hiện tại. |
| A5 | Mã thô hiện cho người dùng: PUBLISHED, NOT_REVIEWED, ACTIVITY, AI_ABOVE_MACHINE, tên nghiệp vụ AI. | Hiện nhãn tiếng Việt; mã AI vẫn ghi nhỏ bên cạnh để tra cứu. |
| A6 | Trên điện thoại 11 mục xếp thành nhiều hàng, cao 237px. | Một hàng cuộn ngang, cao 58px. |

**Nâng cấp giao diện (`frontend/js/pages/admin.js`, cuối `frontend/css/app.css`):**

- Dải tiêu đề như các trang khác, với 4 số liệu thật lấy từ máy chủ: bài cần duyệt, câu hỏi chờ duyệt, JD cần rà soát (chưa duyệt, đến hạn rà soát hoặc link lỗi), học liệu cần xử lý (nháp hoặc link lỗi).
- Menu bên trái chia 3 nhóm (Kiểm duyệt, Nội dung học, Chất lượng & dữ liệu), mỗi mục có biểu tượng và số việc cần xử lý; dưới 1180px thành một hàng cuộn ngang.
- Mỗi mục có phần đầu với biểu tượng, tên và mô tả ngắn; hiện khung chờ trong lúc tải; lỗi tải hiện thông báo và nút Thử lại.
- Tìm kiếm và lọc trạng thái cho JD, học liệu, kho kiến thức, phân tích câu hỏi.
- Form thêm JD, thêm tài liệu, thêm mẫu hiệu chỉnh thu gọn lại cho đến khi cần.
- Bảng có tiêu đề dính khi cuộn, đổi màu khi rê chuột; trọng số kỹ năng hiện bằng thanh phần trăm và nhãn Cốt lõi / Bổ trợ / Tùy chọn.
- Mỗi mục có đường dẫn riêng (`#/admin/jds`, `#/admin/knowledge`...), mở thẳng được và giữ khi tải lại trang.
- Nút "Tạo vector còn thiếu" ghi số đoạn còn thiếu và tắt khi không còn đoạn nào.
- Toàn bộ chức năng và lệnh gọi máy chủ giữ nguyên; 69 chuỗi mới có bản tiếng Anh.

**Kiểm chứng:**

- Toàn bộ bộ test: 1183 passed, 11 skipped. Thêm 5 test trình duyệt thật cho trang quản trị (tạo quản trị viên trong cơ sở dữ liệu tạm của máy chủ test).
- Chạy lại kịch bản trên bản sao: không lỗi console, không yêu cầu lỗi; lưu STATISTICS thành công; tìm "sql" trong kho kiến thức còn 13/86 tài liệu; đường dẫn `#/admin/analytics` mở đúng mục.
- Dữ liệu thật không bị test chạm vào. Hai tài khoản quản trị trong dữ liệu thật là tài khoản người dùng tự tạo; cột mới của 5.36 đã được thêm khi máy chủ của người dùng khởi động lại.

**Chưa kiểm chứng:** các nút kiểm tra link (gọi ra trang ngoài) và thao tác duyệt/ngừng dùng chỉ thử trên bản sao, không thử trên dữ liệu thật.

## Bổ sung 16/11/2026 · Phiên bản 5.41.0: hộp hội thoại Trợ lý có robot chuyển động

**Kiểm tra chức năng trước khi sửa** (bản sao dữ liệu, Edge thật, AI ở chế độ thử): mở bảng, 7 gợi ý, gửi gợi ý, gửi câu hỏi bằng Enter, đính kèm ảnh và bỏ ảnh, từ chối tệp không phải ảnh, lịch sử, mở lại hội thoại, tạo mới, xóa hội thoại, đóng bằng nút và phím Escape, điện thoại không tràn ngang. Tất cả hoạt động đúng, không có lỗi console hay yêu cầu lỗi.

**Vấn đề giao diện:** ảnh chào là ảnh tĩnh; ở chế độ tối ảnh hiện thành khung trắng chói; mặt robot ở đầu bảng và khi đang trả lời đứng yên, trong khi nút "Trợ lý" có chớp mắt.

**Thay đổi:**

- **Robot dùng chung** (`frontend/js/bot.js`): thân robot vẽ ở bản 5.39 chuyển thành module dùng chung cho trang chủ và Trợ lý. Mã gradient có tiền tố riêng nên hai robot cùng trang không trùng id. Trang chủ hiển thị như cũ (đã chụp lại để so).
- **Cảnh chào động** thay ảnh tĩnh: robot bay lơ lửng và vẫy tay trong vòng sáng xoay (xanh ngọc, xanh dương, tím như ảnh cũ), quanh có bong bóng hội thoại với dấu chấm nhấp nháy, sóng âm, lấp lánh; robot chớp mắt 1 giây mở / 1 giây nhắm như các khuôn mặt khác; rê chuột vào cảnh thì robot vẫy ngay. Chế độ tối có cảnh nền xanh đêm thay khung trắng.
- Mặt robot ở đầu bảng chớp mắt như nút "Trợ lý"; khi đang soạn câu trả lời, một vòng sáng xoay quanh mặt robot cạnh dấu ba chấm.
- Các nút gợi ý hiện dần lần lượt.
- Bật giảm chuyển động: chỉ còn chớp mắt (đã kiểm tra bằng trình duyệt).
- Chức năng và lệnh gọi máy chủ của Trợ lý giữ nguyên.

**Kiểm chứng:** toàn bộ bộ test 1184 passed, 11 skipped (thêm 1 test trình duyệt cho cảnh robot). Chạy lại kịch bản trên bản sao sau khi sửa: mọi chức năng vẫn đúng như trước. Đã xem ảnh chụp chế độ sáng, tối, khi vẫy tay.

**Chưa kiểm chứng:** micro thật và AI thật trong lượt kiểm tra này (dùng AI chế độ thử). Vòng sáng khi đang trả lời được xác nhận bằng hoạt ảnh đang chạy, ảnh chụp đến sau khi câu trả lời đã về.

## Bổ sung 16/11/2026 · Phiên bản 5.42.0: giao diện Quy trình Career Adapt và AI hướng dẫn

**Sao lưu trước khi sửa:** `CareerAdapt_AI_backup_truoc_quy_trinh_20261116` (thư mục cùng cấp, không gồm `.venv`).

**Kiểm tra trước khi sửa:** trên bản sao dữ liệu, một tài khoản mới chỉ có trong bản sao đi hết quy trình bằng Edge thật: chọn nghề, báo cáo kỹ năng (thử cả đường nhập văn bản: 6 gợi ý; rồi chọn từ danh sách), xem trang nhập JD, chọn JD từ thư viện, đọc quy định, bắt đầu và nộp bài, chờ chấm, xem kết quả và bài làm, tạo lộ trình, hoàn tất. Không có lỗi console hay yêu cầu lỗi. Giao diện cũ: robot chỉ là chữ "CA", thẻ lựa chọn không có biểu tượng, thanh bước chỉ là chữ nhỏ, phần lớn màn hình trống.

**AI hướng dẫn (`frontend/js/guide.js`):**

- Mỗi màn hình của quy trình có robot CareerAdapt AI (chớp mắt 1 giây mở / 1 giây nhắm, bay nhẹ, sóng âm khi đang "nói") gõ lời hướng dẫn cho bước đó, kèm các bước thao tác đánh số đúng với nút trên màn hình: trang chọn nghề, báo cáo kỹ năng (3 màn), chọn JD (3 màn và trang xem JD), quy định bài kiểm tra, kết quả, lộ trình.
- Lời hướng dẫn do nhóm viết sẵn, khớp màn hình; robot không chấm, không quyết định, không đổi gì. Ở giao diện tiếng Anh, lời được dịch rồi mới gõ.
- Nút "Hỏi Trợ lý về bước này" gửi câu hỏi của bước sang Trợ lý thật (AI của máy chủ, dùng dữ liệu của chính học viên). Ở bước Kết quả, nút "Nhờ Trợ lý giải thích kết quả" chạy nghiệp vụ giải thích kết quả có sẵn.
- **Trong cả bước Bài kiểm tra** (quy định, phòng làm bài, chờ chấm) không có nút hỏi và Trợ lý vẫn đóng như trước; robot chỉ nhắc quy định. Trước đây Trợ lý đóng ở mọi màn hình quy trình; nay mở lại ở các bước khác (báo cáo kỹ năng, chọn JD, kết quả, lộ trình, hoàn tất). Máy chủ vẫn tự chặn Trợ lý khi đang làm bài.

**Giao diện mới:**

- Trang chọn nghề: dải tiêu đề với số liệu thật (số bước, số nghề đã mở, trạng thái), robot hướng dẫn theo tình trạng (chưa bắt đầu, đang làm dở, đã hoàn tất), thẻ nghề có biểu tượng, cột "Các bước của quy trình" đánh dấu bước đã xong và bước hiện tại.
- Thanh bước có biểu tượng từng bước, đường tiến độ, nhãn "Bước x/6".
- Thẻ lựa chọn có biểu tượng và mũi tên; ô chọn mức kỹ năng được tô khi chọn; quy định làm bài có biểu tượng từng dòng.
- Màn hình chờ chấm có robot đang suy nghĩ trong vòng sáng; màn hình hoàn tất có robot đầy đủ vẫy tay giữa hoa giấy.
- Bật giảm chuyển động: chỉ còn chớp mắt, lời hướng dẫn hiện ngay.

**Sửa kèm:** ở trang Đóng góp câu hỏi, nhãn đếm của mục Bản tiếng Anh hiện lẫn tiếng Việt khi dùng giao diện tiếng Anh ("không bắt buộc · 0/0 items"), vì bộ dịch tách câu tại dấu "·" mà phần "không bắt buộc" chưa có bản dịch. Nhãn nay gồm hai đoạn chữ riêng, mỗi đoạn có bản dịch ("optional · 1/1 items"); đã kiểm tra trên trình duyệt ở cả hai ngôn ngữ.

**Không đổi:** thứ tự bước, mọi lệnh gọi máy chủ, form, hộp xác nhận, quy tắc khóa bước, reset và đổi JD mục tiêu. 85 chuỗi mới có bản tiếng Anh.

**Kiểm chứng:**

- Toàn bộ bộ test: 1184 passed, 11 skipped (bỏ qua: AI thật, Docker thật).
- Chạy lại cả quy trình trên bản sao sau khi sửa: không lỗi; nút hỏi mở Trợ lý, gửi câu hỏi và nhận trả lời; ở bước Bài kiểm tra không có nút hỏi và nút Trợ lý bị ẩn; Trợ lý hiện lại ở màn hình hoàn tất; điện thoại không tràn ngang; tiếng Anh hiện đúng lời đã dịch.

**Chưa kiểm chứng:** AI thật (lượt thử dùng AI chế độ thử); màn hình chờ chấm chưa chụp được vì chấm xong quá nhanh trên máy thử.

## Bổ sung 16/11/2026 · Phiên bản 5.43.0: bộ biểu cảm của robot CareerAdapt AI

**Cách làm:** đầu robot là ảnh vẽ, khuôn mặt nằm sẵn trong ảnh. Khuôn mặt được xóa khỏi kính (lấp bằng màu kính xung quanh, giữ nguyên vỏ, tai nghe, mũ) thành `frontend/img/ai-head-blank.webp`; khuôn mặt mới được vẽ bằng SVG đúng vị trí cũ (mắt xanh phát sáng, miệng hồng, má hồng), nên đổi được biểu cảm và có chuyển động (chớp mắt, nước mắt rơi, mắt sao lấp lánh, dấu ba chấm khi suy nghĩ). Mã: `frontend/js/faces.js`, `frontend/css/faces.css`.

**12 biểu cảm và lúc xuất hiện:**

| Biểu cảm | Khuôn mặt | Khi nào |
|---|---|---|
| happy | mắt tròn, miệng cười mở | chào hỏi, hướng dẫn các bước, trang đăng nhập lúc bình thường |
| neutral | mắt tròn, cười nhẹ | mặc định |
| joy | mắt ^ ^, cười lớn, má hồng | đạt bài kiểm tra; thông báo thành công ở trang đăng nhập |
| celebrate | mắt ngôi sao lấp lánh | đạt từ 85 điểm; màn hình hoàn tất quy trình |
| proud | nháy một mắt | dự phòng |
| encouraging | mắt cong dịu, cười nhẹ | chưa đạt nhưng từ 40 điểm; trước khi làm bài kiểm tra |
| thinking | mắt nhìn lên, ba chấm | đang chấm bài; đang chờ máy chủ khi đăng nhập |
| surprised | mắt tròn to, miệng chữ o | Caps Lock bật; mật khẩu đang hiện |
| worried | lông mày chau, miệng gợn | điểm từ 40 nhưng có lỗi trọng yếu; sai mật khẩu |
| sad | mắt cụp, miệng trễ | từ 20 đến dưới 40 điểm |
| crying | mắt nhắm, nước mắt rơi | dưới 20 điểm |
| shy | nhắm mắt, má hồng | đang gõ mật khẩu |

**Nguyên tắc:** biểu cảm chỉ phản ánh điều đã xảy ra (điểm và quyết định đạt do bộ kiểm tra tính, thông báo trang đã hiện); không quyết định hay thay đổi gì. Ở bước Kết quả, lời của robot đi cùng biểu cảm và luôn hướng về bước tiếp theo; với điểm thấp robot "buồn cùng" người học, không chê.

**Đã gắn vào:** robot trang đăng nhập; robot hướng dẫn mọi bước của quy trình (bước Kết quả chọn biểu cảm theo điểm); màn hình chờ chấm; màn hình hoàn tất. Robot ở trang chủ, Trợ lý và nút "Trợ lý" giữ ảnh vẽ cũ với nhịp chớp 1 giây mở / 1 giây nhắm.

**Lưu ý:** trang đăng nhập có chính sách bảo mật không cho `style` viết trực tiếp, nên khuôn mặt SVG chỉ dùng thuộc tính SVG và lớp CSS. Các khuôn mặt mới chớp mắt nhanh tự nhiên (không theo nhịp 1 giây / 1 giây) để biểu cảm dễ đọc.

**Kiểm chứng:**

- Toàn bộ bộ test: 1184 passed, 11 skipped; thêm 1 test trình duyệt cho biểu cảm ở trang đăng nhập (vui, ngại khi gõ mật khẩu, lo lắng khi sai mật khẩu, không lỗi).
- Đi hết quy trình trên bản sao dữ liệu với bài để trống (0 điểm): hướng dẫn vui, trước bài kiểm tra là động viên, kết quả là khóc kèm lời "Mình buồn cùng bạn một chút", hoàn tất là mắt sao. Đã xem ảnh chụp đủ 12 biểu cảm.

**Chưa kiểm chứng:** biểu cảm ở các mức điểm cao (đạt, từ 85) chưa chạy qua giao diện vì cần bài làm đúng thật; quy tắc chọn biểu cảm theo điểm đã kiểm tra bằng đọc mã. Màn hình chờ chấm chưa chụp được vì chấm xong quá nhanh.

## Bổ sung 16/11/2026 · Phiên bản 5.44.0: Kế hoạch Career Adapt hiện theo nút

**Sao lưu trước khi sửa:** `CareerAdapt_AI_backup_truoc_ke_hoach_20261116`.

**Vấn đề:** mỗi mục của Kế hoạch hiện mọi khối thông tin cùng lúc. Đo trên bản sao dữ liệu (máy tính, 1440px): Khoảng cách kỹ năng cao khoảng 2.500px, Kết quả bài làm 1.700px, Xếp hạng 1.550px, Lộ trình 1.500px.

**Cách mới (`frontend/js/disclose.js`, `frontend/js/pages/plan.js`, cuối `frontend/css/app.css`):**

- Mỗi mục chỉ hiện dải tiêu đề (số liệu tóm tắt) và một hàng nút; mỗi nút có biểu tượng, tên và một dòng mô tả. Bấm nút để mở phần chi tiết ngay bên dưới; bấm lại hoặc "Thu gọn" để đóng. Mỗi lúc chỉ mở một phần; trang nhớ phần đang mở khi quay lại (trong phiên trình duyệt).
- Các thẻ, biểu đồ, form và nút cũ được chuyển nguyên vẹn vào phần tương ứng, không viết lại, nên mọi chức năng giữ nguyên.
- Cảnh báo quan trọng vẫn luôn hiện, đặt trên hàng nút: "Bạn đang chậm so với lịch" (kèm nút Dời lịch), phiên học đang bấm giờ.
- Bấm một kỹ năng trên biểu đồ khoảng cách thì phần "Chi tiết và bằng chứng" tự mở và cuộn tới dòng đó.
- Mục nào tự vẽ lại sau một thao tác (lọc nhắc nhở, cập nhật lộ trình) vẫn giữ hàng nút. Trang con của Lộ trình (tuần, bài học, bài đánh giá tổng hợp) và trang Xem lại bài làm giữ bố cục cũ.

| Mục | Các nút |
|---|---|
| Khai báo và JD | Kỹ năng bạn tự khai · JD đã sử dụng · Làm lại từ đầu |
| Kết quả bài làm | Điểm và bài đã làm · Nhận xét trình độ · Cơ sở đánh giá |
| Khoảng cách kỹ năng | Khoảng cách theo kỹ năng · Chi tiết và bằng chứng · Kỹ năng ưu tiên · So khớp với JD khác |
| Lộ trình học tập | Tiến độ và bài tiếp theo · Các tuần học · Bài đánh giá tổng hợp · Bài chưa xếp và bài cũ |
| Xếp hạng và lương | Bảng xếp hạng · Lương tham khảo · Cách phân bậc kỹ năng |
| Nhắc nhở | Việc cần xử lý · Nhật ký và thay đổi kỹ năng |

**Kiểm chứng:**

- Toàn bộ bộ test: 1185 passed, 11 skipped.
- Trên bản sao dữ liệu, mỗi mục giờ vừa một màn hình máy tính (khoảng 900px) khi chưa mở phần nào; không lỗi console.
- Kịch bản thao tác bằng Edge thật: mỗi nút mở đúng phần, chỉ một phần mở một lúc, bấm lại thì đóng; hộp Reset, hộp Cách phân bậc, ngăn bằng chứng mở được; bấm biểu đồ tự mở bảng chi tiết; danh sách so khớp JD tải vào được; ô tuần dẫn tới trang tuần và quay lại vẫn mở đúng phần; bộ lọc nhắc nhở và nút nhật ký vẫn chạy mà không mất hàng nút. 31 chuỗi mới có bản tiếng Anh.

**Chưa kiểm chứng:** thao tác "Cập nhật lộ trình" và "Dời lịch" không chạy thật (chỉ thử đến hộp xác nhận ở bản trước) để không đổi lộ trình của tài khoản thử.

## Bổ sung 17/11/2026 · Phiên bản 5.45.0: Kế hoạch hiện thẳng thông tin chính

**Sao lưu trước khi sửa:** `CareerAdapt_AI_backup_truoc_thong_tin_chinh_20261117`.

**Yêu cầu:** không biến mọi thứ thành nút; thông tin chính của từng mục hiện thẳng, phần phụ mới để sau nút.

**Thay đổi (`frontend/js/pages/plan.js`, `frontend/js/disclose.js`, cuối `frontend/css/app.css`):** khối chính của mỗi mục không còn bị đưa vào nút mà hiện ngay dưới dải tiêu đề; bên dưới là hàng nút có nhãn "Xem thêm chi tiết" cho phần phụ. Cảnh báo (chậm lịch, phiên học đang chạy) vẫn luôn hiện.

| Mục | Hiện thẳng | Sau nút "Xem thêm chi tiết" |
|---|---|---|
| Khai báo và JD | Kỹ năng bạn tự khai | JD đã sử dụng · Làm lại từ đầu |
| Kết quả bài làm | Điểm, ngưỡng đạt, nút Xem lại bài làm | Nhận xét trình độ · Cơ sở đánh giá |
| Khoảng cách kỹ năng | Biểu đồ khoảng cách theo kỹ năng | Chi tiết và bằng chứng · Kỹ năng ưu tiên · So khớp với JD khác |
| Lộ trình học tập | Tiến độ, bài tiếp theo và lịch học theo tuần (từ 5.45.1) | Bài đánh giá tổng hợp · Bài chưa xếp và bài cũ |
| Xếp hạng và lương | Bảng xếp hạng (kèm bộ lọc) | Lương tham khảo · Cách phân bậc kỹ năng |
| Nhắc nhở | Việc cần xử lý (kèm bộ lọc) | Nhật ký và thay đổi kỹ năng |

**Kiểm chứng:**

- Toàn bộ bộ test: 1185 passed, 11 skipped.
- Kịch bản Edge thật trên bản sao dữ liệu (1440px và 390px): ở cả 6 mục, khối chính hiện ngoài nút và nằm trên hàng nút; không tràn ngang; không lỗi console. Các thao tác vẫn chạy: mở từng nút (mỗi lúc một phần, bấm lại thì đóng), hộp Reset, hộp Cách phân bậc, bấm biểu đồ tự mở bảng chi tiết, ngăn bằng chứng, danh sách so khớp JD, ô tuần dẫn tới trang tuần và quay lại vẫn mở đúng phần, bộ lọc nhắc nhở và nút nhật ký giữ hàng nút.

**Chưa kiểm chứng:** "Cập nhật lộ trình" và "Dời lịch" không chạy thật để không đổi lộ trình của tài khoản thử (mã của hai thao tác này không đổi).

## Bổ sung 17/11/2026 · Phiên bản 5.45.1: Lịch theo tuần hiện thẳng trên Lộ trình

**Yêu cầu:** lịch học theo tuần là phần chính của Lộ trình học tập nên phải hiện ngay, không để sau nút.

**Thay đổi:** bỏ nút "Các tuần học" trong `frontend/js/pages/plan.js`; tiêu đề lịch, các ô tuần và dòng ghi chú mục tiêu giờ hiện ngay dưới phần Tiến độ và bài tiếp theo. Chỉ còn hai nút "Bài đánh giá tổng hợp" và "Bài chưa xếp và bài cũ".

**Kiểm chứng:** 1185 passed, 11 skipped. Trên Edge thật với bản sao dữ liệu (1440px và 390px): 6 ô tuần hiện ngoài nút, nằm trên hàng nút, không tràn ngang, không lỗi console; bấm ô tuần mở trang tuần, quay lại vẫn thấy lịch; hai nút còn lại mở đúng phần.


## Bổ sung 17/11/2026 · Phiên bản 5.46.0: kiểm định, sửa chữa và nâng cấp toàn diện

**Sao lưu trước khi sửa:** `CareerAdapt_AI_backup_truoc_kiem_dinh_master_20261117`. Báo cáo đầy đủ (mục A–J): `FINAL_IMPLEMENTATION_AND_UPGRADE_REPORT.md`.

- **Chống nhồi từ khóa (lỗi HIGH, đã tái hiện):** chữ chép từ đề, cụm đệm lặp lại giữa các câu và câu chỉ liệt kê khái niệm không còn được tính là lời giải thích. Bài chỉ có từ khóa từ 25–100 điểm xuống 0–25; mọi đáp án mẫu vẫn 100/100 trên 4 bộ dữ liệu.
- **Hủy đổi mục tiêu:** trước đây đã bấm "Đổi JD mục tiêu" thì kẹt ở bước JD; nay hủy được và quay về đúng trạng thái cũ.
- **Bài đánh giá tổng hợp bỏ dở quá giờ** nay được tác vụ nền tự nộp và chấm, không còn chặn việc đổi mục tiêu.
- **Nhiều tab:** tab cũ không còn ghi đè đáp án mới hơn (409 kèm thông báo). **Tín hiệu dán** do máy chủ tự ghi nhận, chỉ để tham khảo. **Chạy code** giới hạn một lần mỗi học viên qua mọi tiến trình.
- **Nâng cấp:** bảng "Độ tin cậy đánh giá" (mức dựa trên bao nhiêu bài làm, loại kiểm tra nào); "Lỗi bạn đã mắc ở kỹ năng này" trên trang bài học; mọi ngưỡng đạt gom vào `backend/assessment_policy.py` và hiện cho người học.
- **Kiểm chứng:** 1284 passed, 11 skipped (AI thật, Docker thật), 0 failed; thêm 99 test. Máy chủ uvicorn thật kiểm Host và proxy tin cậy; 21 đoạn code tấn công sandbox đều bị chặn; Edge thật 13 trang × 2 kích thước không lỗi.
- **Dữ liệu:** không đổi cấu trúc, không migration, không ghi vào `data/`.

## Bổ sung 18/11/2026 · Phiên bản 5.47.0: Trợ lý AI trong Kế hoạch Career Adapt

**Sao lưu trước khi sửa:** `CareerAdapt_AI_backup_truoc_tro_ly_ke_hoach_20261118`.

**Thay đổi:** mỗi mục của Kế hoạch có thêm thẻ Trợ lý CareerAdapt AI ngay dưới dải tiêu đề, luôn hiện (không nằm sau nút). Thẻ có robot chuyển động, vai trò cố vấn của mục, một câu giới thiệu và các nút hỏi nhanh. Mỗi nút chuyển câu hỏi cho Trợ lý thật: tác vụ AI của máy chủ (`backend/ai_service/task_engine.py`) hoặc câu hỏi như người dùng gõ; nút "Hỏi điều khác" mở cuộc trò chuyện trống. Thẻ không tự tính, chấm hay đổi dữ liệu nào.

| Mục | Vai trò | Nút hỏi nhanh |
|---|---|---|
| Khai báo và JD | Cố vấn nghề nghiệp | Tổng hợp hành trình của tôi · Phân tích JD của tôi · Tôi nên làm gì tiếp theo? |
| Kết quả bài làm | Cố vấn kỹ năng | Giải thích kết quả đánh giá · Tôi cần cải thiện kỹ năng nào trước? |
| Khoảng cách kỹ năng | Cố vấn kỹ năng | Phân tích kỹ năng của tôi · Tư vấn mức sẵn sàng |
| Lộ trình học tập | Cố vấn lộ trình | Tôi nên học gì tiếp theo? · Giải thích lộ trình · Sắp xếp việc học tuần này |
| Xếp hạng và lương | Cố vấn sẵn sàng ứng tuyển | Tư vấn mức sẵn sàng · Làm sao để tăng thứ hạng? |
| Nhắc nhở | Cố vấn tiến độ | Việc nào nên làm trước? · Tôi nên học gì tiếp theo? |

Tệp: `frontend/js/plan-advisor.js` (mới), `frontend/js/pages/plan.js` (gắn thẻ trước hàng nút chi tiết), cuối `frontend/css/app.css` (kiểu `.pa-*`), `backend/ai_service/assistant.py` (thêm vai trò `plan_rank`, trước đây mục Xếp hạng dùng vai trò mặc định), `frontend/js/lang/en.json` (24 chuỗi), `tests/test_plan_advisor.py` (5 test mới).

**Kiểm chứng:**

- Toàn bộ bộ test: 1289 passed, 11 skipped.
- Edge thật trên bản sao dữ liệu, 1440px và 375px: cả 6 mục có đúng một thẻ, nằm ngoài các phần ẩn và trên hàng nút "Xem thêm chi tiết"; không tràn ngang; không lỗi console. Bấm "Phân tích kỹ năng của tôi" mở bảng Trợ lý và nhận câu trả lời từ dữ liệu của tài khoản; bấm câu hỏi ở mục Nhắc nhở gửi đúng câu hỏi; "Hỏi điều khác" mở cuộc trò chuyện trống; chế độ tiếng Anh hiện bản dịch.

**Chưa kiểm chứng:** bản sao dữ liệu chạy không có Gemini, nên các nút là tác vụ máy chủ trả lời bằng luật dự phòng (có dữ liệu thật), còn các nút là câu hỏi tự do chỉ nhận câu tra cứu kho kiến thức. Câu trả lời của Gemini thật cho các nút này chưa được thử.

## Bổ sung 18/11/2026 · Phiên bản 5.48.0: Kiểm định cuối

Báo cáo đầy đủ: `CAREERADAPT_AI_FINAL_AUDIT_REPORT.md`. Sao lưu: `CareerAdapt_AI_backup_truoc_kiem_dinh_cuoi_20261118` (kèm bản chụp nhất quán của hai cơ sở dữ liệu).

- **D-1 (LOW):** nút "Kiểm tra" của bài thực hành và bước kiểm tra tự động khi chuyên gia đóng góp câu hỏi code chạy code mà không giữ lượt chạy của tài khoản. Giờ mọi lần chạy code theo yêu cầu đều dùng `exam_service.code_run_slot`. Khóa theo người học (5.34) vốn đã xếp hàng các yêu cầu của một tài khoản, nên đây là lớp bảo vệ bổ sung.
- **D-2 (MEDIUM):** phiên hết hạn giữa chừng hoặc mở liên kết khi chưa đăng nhập: đăng nhập xong luôn về Bảng điều khiển. Giờ trang quay lại đúng trang đang dùng; chỉ nhận đoạn `#/…` của ứng dụng nên không thành chuyển hướng mở.
- 7 test mới (`tests/test_audit_2026_11_18.py`, 2 test trong `tests/test_ui_e2e.py`). Toàn bộ: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Không đổi cấu trúc cơ sở dữ liệu.

## Bổ sung 19/11/2026 · Phiên bản 5.49.0: Khai báo và JD gọn hơn

**Yêu cầu:** giao diện mục "Khai báo và JD" của Kế hoạch Career Adapt đẹp hơn, gọn, ít chữ, vẫn đủ chức năng. Bản cũ nằm trong lịch sử Git (commit a33e9fa).

**Bố cục mới** (`frontend/js/pages/plan.js`, cuối `frontend/css/app.css`):

- Dải tiêu đề chỉ còn tên JD và ba số: kỹ năng tự khai, kỹ năng JD yêu cầu, ngày hoàn tất. Bỏ câu giải thích.
- Một bảng **Kỹ năng** thay cho hai lưới thẻ: mỗi dòng là một kỹ năng, hai thanh mức đặt cạnh nhau "Bạn khai" (tím) và "JD cần" (xanh), nhãn "Cốt lõi" cho kỹ năng cốt lõi. Ghi chú một dòng: "Mức tự khai chưa được xác thực" kèm cách khai. Ghi chú bằng chứng tự khai (nếu có) vẫn hiện dưới tên kỹ năng.
- Thẻ **JD** đặt cạnh bảng (máy tính) hoặc bên dưới (điện thoại): nguồn JD, tóm tắt thu gọn 3 dòng với nút "Xem thêm"/"Thu gọn", nhãn AI tóm tắt hoặc tóm tắt theo quy tắc, nút "Phân tích JD của tôi" (tác vụ JD của Trợ lý như trước).
- "Làm lại từ đầu" thành nút nhỏ ở cuối trang, cạnh dòng "Quy trình đã khóa từ …"; bấm vẫn mở hộp xác nhận Reset có xem trước dữ liệu bị xóa.
- Mục này không còn hàng nút "Xem thêm chi tiết" vì cả trang vừa một màn hình. Thẻ Trợ lý AI giữ nguyên, bỏ nút "Phân tích JD của tôi" trùng với nút trong thẻ JD.

**Kiểm chứng:**

- Toàn bộ bộ test: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Edge thật trên bản sao dữ liệu (1440px, 390px, giao diện tối, tiếng Anh): 5 dòng kỹ năng với nhãn đọc màn hình "Bạn khai: mức 1/3", "JD cần: mức 3/3"; "Xem thêm" mở rộng và thu gọn tóm tắt; "Phân tích JD của tôi" mở Trợ lý và nhận câu trả lời; "Làm lại từ đầu" mở hộp Reset, Hủy không đổi gì; không tràn ngang; không lỗi console. 6 chuỗi mới có bản tiếng Anh.

## Bổ sung 19/11/2026 · Phiên bản 5.50.0: Kết quả bài làm gọn hơn

**Yêu cầu:** mục "Kết quả bài làm" của Kế hoạch Career Adapt đẹp, đơn giản, ít chữ, dễ dùng, vẫn đủ chức năng.

**Bố cục mới** (`frontend/js/pages/plan.js`, cuối `frontend/css/app.css`):

- Dải tiêu đề: "Đạt/Chưa đạt · điểm" và ba số (ngưỡng đạt, kỹ năng đạt JD, số bài đã chấm). Bỏ câu giải thích; điểm không còn lặp ở ba chỗ.
- **Thẻ điểm** duy nhất: vòng điểm có vạch ngưỡng, nhãn Đạt/Chưa đạt, robot đổi nét mặt theo điểm (cùng quy tắc `expressionForScore` của 5.43), "Còn thiếu / Cao hơn ngưỡng … điểm", một dòng ngưỡng · số bài · giờ nộp, các nhãn nhỏ khi bài tự nộp, rời màn hình, dán nhiều chữ (rê chuột để đọc ghi chú "không ảnh hưởng điểm"), khung đỏ khi có lỗi trọng yếu, nút "Xem lại bài làm".
- **Thẻ Tiếp theo**: trình độ đã xác thực, mức cạnh tranh, kỹ năng nên học trước (cùng quy tắc chọn như trước) và nút "Mở lộ trình".
- **Bảng Kỹ năng** hiện ngay (trước đây nằm sau nút "Nhận xét trình độ"): mỗi kỹ năng một dòng với thanh mức "Đã xác thực" và "JD cần", nhãn "Đạt" hoặc "Thiếu n", nút "Vì sao" mở chủ đề, độ khó và lý do chấm; nút ⓘ mở hộp "Cách phân bậc"; "Nhận xét của AI" thu gọn trong một dòng; ghi chú phạm vi một dòng.
- "Kết quả này dựa trên gì" giữ dạng thẻ đóng mở ở cuối trang. Mục này không còn hàng nút "Xem thêm chi tiết".
- Sửa kèm: biểu tượng của thẻ "Kết quả này dựa trên gì" bị kéo giãn (quy tắc CSS cho phần chữ áp lên cả biểu tượng); lỗi này cũng có ở trang Xếp hạng.

**Kiểm chứng:**

- Toàn bộ bộ test: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Edge thật trên bản sao dữ liệu (1440px, 390px, giao diện tối, tiếng Anh): robot hiện nét mặt "crying" với bài 0 điểm; "Xem lại bài làm" mở trang xem lại và quay lại được; "Vì sao", "Nhận xét của AI", "Kết quả này dựa trên gì" mở được; nút ⓘ mở hộp Cách phân bậc; "Mở lộ trình" trỏ tới Lộ trình; nhãn đọc màn hình "Đã xác thực: mức 0/3", "JD cần: mức 3/3"; không tràn ngang; không lỗi console. 14 chuỗi mới có bản tiếng Anh.
- Chưa thử với bài có cờ tự nộp, rời màn hình hay lỗi trọng yếu vì tài khoản thử không có các cờ này; phần hiển thị dùng đúng các trường cũ.

## Bổ sung 19/11/2026 · Phiên bản 5.51.0: Xếp hạng và lương gọn hơn

**Yêu cầu:** chỉnh lại giao diện mục "Xếp hạng và lương" của Kế hoạch Career Adapt (cùng hướng 5.49–5.50: gọn, ít chữ, đủ chức năng).

**Bố cục mới** (`frontend/js/pages/rank.js`, cuối `frontend/css/app.css`; chữ trên trang giảm từ khoảng 330 xuống 228 từ):

- **Dải vị trí**: phạm vi xếp hạng (cách xếp · kỹ năng), "Hạng/Top" cỡ lớn, nhãn thay đổi hạng rút gọn ("Giữ hạng", "Tăng 2 hạng"; rê chuột để đọc "so với bài kiểm tra đầu vào"), nhãn "4/5 người để tính Top" khi chưa đủ người. Ba ô: trình độ, tổng mức (có thanh), điểm đầu vào. Hàng thao tác: "Chia sẻ", "Hiện tên tôi" (rê chuột để đọc giải thích), "Cách phân bậc" (thay thẻ riêng ở cuối trang trước đây).
- **Bảng xếp hạng**: bộ chọn "Năng lực hiện tại / Bài kiểm tra đầu vào" và ô chọn kỹ năng chuyển vào đầu bảng (bỏ thẻ bộ lọc riêng); câu quy tắc xếp hạng thu vào "Cách xếp hạng".
- **So với nhóm** và **Phân bố trình độ**: bỏ dòng mô tả; khi chưa đủ người, một dòng giải thích ngắn.
- **Lương tham khảo** hiện ngay (trước đây nằm sau nút): biểu đồ cột, mức tăng theo kinh nghiệm, liên kết nguồn; ghi chú phạm vi, vị trí, thời gian khảo sát, số người trả lời và ngày kiểm tra thu vào "Về số liệu".
- Mục này không còn hàng nút "Xem thêm chi tiết".

**Kiểm chứng:**

- Toàn bộ bộ test: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Edge thật trên bản sao dữ liệu (1440px, 390px, giao diện tối, tiếng Anh): đổi cách xếp hạng và lọc kỹ năng vẽ lại trang, giữ thẻ Trợ lý AI và không hiện lại hàng nút; "Chia sẻ" sao chép đúng nội dung; "Hiện tên tôi" bật rồi tắt lại được (chỉ trên bản sao); hộp Cách phân bậc mở được; "Cách xếp hạng" và "Về số liệu" mở được; liên kết nguồn lương đúng; không tràn ngang; không lỗi console. 16 chuỗi mới có bản tiếng Anh.

## Bổ sung 19/11/2026 · Phiên bản 5.52.0: Hồ sơ và thanh chào mừng

**Yêu cầu:** nâng cấp giao diện trang Hồ sơ cho đẹp và hiện đại; nâng cấp thanh chào mừng ở Bảng điều khiển.

**Hồ sơ** (`frontend/js/pages/profile.js` viết lại phần bố cục, cuối `frontend/css/app.css`):

- Đầu trang màu xanh đậm: ảnh đại diện lớn với nút tải ảnh tròn ở góc, vai trò (Học viên/Quản trị viên, nhãn Đóng góp câu hỏi nếu có), họ tên, email, ba nhãn ngành học, giờ học mỗi tuần · thời hạn, ngày tham gia; nút "Xóa ảnh" khi có ảnh, nút "Trang quản trị" với quản trị viên (thay hộp thông báo cũ).
- Menu bên trái (trên điện thoại là hàng tab cuộn ngang): Thông tin, Mục tiêu, Nhắc nhở, Bảo mật, Dữ liệu. Mỗi lần hiện một phần, có thể chuyển bằng phím mũi tên, trang nhớ phần đang mở trong phiên.
- Nhắc nhở dùng công tắc gạt thay ô đánh dấu. Bảo mật hiện thêm ngày đổi mật khẩu gần nhất và lần đăng nhập gần nhất (đã có sẵn trong `/auth/me`). Dữ liệu gồm hai hàng: Tải về và vùng Xóa màu đỏ.
- Mọi biểu mẫu, tên trường, yêu cầu gửi máy chủ và hộp xác nhận giữ nguyên.

**Thanh chào mừng** (`frontend/js/pages/dashboard.js`):

- Lời chào theo giờ trên máy người dùng (Chào buổi sáng/trưa/chiều/tối), tay vẫy chuyển động nhẹ (tắt khi người dùng chọn giảm chuyển động).
- Nhãn "Chậm lịch n ngày" khi lộ trình chậm; dòng "Tiếp theo: bài học · Tuần n" thay câu khẩu hiệu.
- Nút **Học tiếp** mở thẳng bài học tiếp theo; hai nút cũ giữ nguyên.
- Dải số liệu: tiến độ lộ trình (có thanh), số bài đã học, mức đáp ứng JD (có thanh), ngày dự kiến xong. Chỉ hiện số máy chủ trả về; ô "0% đáp ứng JD" nổi trên hình robot được bỏ vì đã có trong dải.

**Kiểm chứng:**

- Toàn bộ bộ test: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Edge thật trên bản sao dữ liệu (1440px, 390px, giao diện tối, tiếng Anh): nút Học tiếp mở đúng bài ACT_SQL_01; lưu Thông tin, Mục tiêu, Nhắc nhở đều báo đúng thông báo; công tắc nhắc nhở bật tắt được; phím mũi tên chuyển tab; danh sách điều kiện mật khẩu hiện đủ 6 mục; "Tải về" tải tệp `careeradapt-du-lieu-ca-nhan.json`; nút Xóa mở hộp xác nhận (đã hủy, không xóa); tải ảnh đại diện lên rồi xóa ảnh (chỉ trên tài khoản bản sao); tải lại trang vẫn mở đúng tab; không tràn ngang; không lỗi console. 39 chuỗi mới có bản tiếng Anh.
- Chưa thử nút Đổi mật khẩu thật để không đổi mật khẩu tài khoản thử; phần này dùng nguyên mã cũ.

## Bổ sung 19/11/2026 · Phiên bản 5.53.0: Menu dọc cho Kế hoạch Career Adapt

**Yêu cầu:** nâng cấp giao diện Kế hoạch Career Adapt giống trang Hồ sơ: các nút chức năng đặt thẳng đứng, nội dung hiện bên cạnh khi bấm từng mục.

**Thay đổi:**

- `frontend/index.html`: thanh mục và vùng nội dung nằm chung một khung `#view-shell`.
- `frontend/js/core.js`: `setSubnav(html, { side: true })` bật bố cục menu bên cạnh; mọi trang khác vẫn gọi `setSubnav()` như cũ nên không đổi.
- `frontend/js/pages/plan.js`: menu mới gồm nhóm **Nghề** (Data Analyst; Backend Developer và QA Tester có nhãn "Sắp có") và nhóm **Data Analyst** với 6 mục (Khai báo và JD, Kết quả bài làm, Khoảng cách kỹ năng, Lộ trình học tập, Xếp hạng và lương, Nhắc nhở). Mỗi mục vẫn là một liên kết nên nút Quay lại của trình duyệt, liên kết trực tiếp và các trang con (tuần học, bài học, xem lại bài làm) hoạt động như trước; mục đang mở được tô sáng.
- `frontend/css/app.css`: từ 1200px trở lên, menu là cột 236px bên trái, dính khi cuộn trang, nội dung ở bên phải; dưới 1200px (máy tính bảng, điện thoại) menu trở lại dạng hai hàng tab cuộn ngang và tự cuộn tới mục đang mở.

**Kiểm chứng:**

- Toàn bộ bộ test: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Edge thật trên bản sao dữ liệu ở 1440px, 1280px, 1024px và 390px, cả 6 mục và trang Backend Developer: menu dọc ở 1440/1280, hàng tab ở 1024/390; mục đang mở đúng ở mọi trang; menu vẫn ở trên màn hình khi cuộn xuống; bấm "Xếp hạng và lương" chuyển đúng trang; trang tuần học, bài học và xem lại bài làm giữ menu và tô đúng mục cha; rời sang trang Hồ sơ thì bố cục menu bên cạnh tắt; không tràn ngang; không lỗi console; giao diện tối hiển thị đúng.

## Bổ sung 19/11/2026 · Phiên bản 5.54.0: Kết quả bài làm bớt khoảng trống

**Yêu cầu:** trang "Kết quả bài làm" đang quá nhiều khoảng trống, quá đơn giản.

**Thay đổi** (`frontend/js/pages/plan.js`, `frontend/js/pages/exam.js`, cuối `frontend/css/app.css`), chỉ thêm dữ liệu thật đã có trong `/career-process/exam/review`:

- **Thẻ điểm** thêm cột **Điểm từng bài**: Bài 1–5 với kỹ năng, độ khó, thanh điểm (xanh đạt, cam một phần, đỏ sai, xám bỏ trống), nhãn "Trống" và số điểm. Bấm một bài mở trang Xem lại bài làm đúng bài đó (`#/plan/da/review?q=N`; `renderReview` nhận thêm `start`, các nơi khác gọi như cũ).
- **Dải Tiếp theo** thay thẻ dọc: Trình độ, Cạnh tranh, Ưu tiên học và nút "Mở lộ trình" trên một hàng.
- **Bảng Kỹ năng** dày hơn: mỗi dòng có chủ đề và độ khó dưới tên, cột **Điểm bài** (thanh và số), mức đã xác thực, mức JD cần, nhãn Đạt/Thiếu và mũi tên; bấm cả dòng (hoặc Enter) để mở "Vì sao" ngay dưới, không còn dòng "Vì sao" riêng.
- **Nhận xét của AI** thành thẻ riêng (nhãn "Không đổi điểm", "Xem thêm" khi dài), đặt cạnh "Kết quả này dựa trên gì".
- Sửa kèm: quy tắc CSS cho menu dọc ở 1200–1365px bị áp lên cả điện thoại; nay chỉ áp trong khoảng đó.

**Kiểm chứng:**

- Toàn bộ bộ test: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Edge thật trên bản sao dữ liệu (1440px, 1280px, 390px, giao diện tối, tiếng Anh): khoảng trống cuối thẻ điểm giảm từ 66px còn 28px; bấm dòng kỹ năng mở và đóng phần lý do, phím Enter cũng mở được; bấm "Bài 3" mở trang xem lại ở Bài 3, menu vẫn tô "Kết quả bài làm"; `#/plan/da/review` vẫn mở Bài 1, `?q=99` mở bài cuối; hộp Cách phân bậc, "Kết quả này dựa trên gì" và liên kết lộ trình chạy; không tràn ngang; không lỗi console. 6 chuỗi mới có bản tiếng Anh.

## Bổ sung 19/11/2026 · Phiên bản 5.55.0: Cảnh động phía sau robot ở thanh chào mừng

**Yêu cầu:** nâng cấp hiệu ứng, thêm hình ảnh, điều chỉnh hình nền động phía sau robot ở thanh chào mừng.

**Thay đổi** (`heroArt()` trong `frontend/js/pages/dashboard.js`, cuối `frontend/css/app.css`):

- Bỏ khung kính chữ nhật và vệt sáng chéo cứng. Thay bằng ánh sáng mềm quét chậm qua thanh, dải màu cực quang trôi nhẹ, sao lấp lánh và mặt sàn lưới phối cảnh chuyển động dưới chân robot.
- Robot đứng trước một **cổng ánh sáng**: ba vòng sáng đồng tâm xoay ngược chiều nhau và lõi sáng nhịp thở.
- **Hình ảnh mới**: biểu tượng 5 kỹ năng của nghề (SQL, Python, Trực quan hóa, Chất lượng dữ liệu, Giao tiếp viết), mỗi kỹ năng một màu, bay vòng quanh robot và luôn đứng thẳng; thẻ biểu đồ có cột nhấp nhô và đường xu hướng tự vẽ; bong bóng trò chuyện có ba chấm "đang gõ"; khiên xác thực có vòng sóng lan.
- Toàn bộ cảnh chỉ để trang trí: không có con số nào (số thật nằm ở dải số liệu của thanh), đánh dấu `aria-hidden`, và đứng yên khi hệ điều hành bật giảm chuyển động. Trên điện thoại cảnh vẫn được ẩn như trước.

**Kiểm chứng:**

- Toàn bộ bộ test: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Edge thật trên bản sao dữ liệu ở 1440px, 1280px, 1100px: 57 chuyển động chạy trong thanh, 5 biểu tượng kỹ năng trên quỹ đạo, chụp ba khung hình cách nhau 1,3 giây cho thấy quỹ đạo và các thẻ thay đổi; khi bật giảm chuyển động không còn chuyển động nào trong cảnh; ở 390px cảnh ẩn; không tràn ngang; không lỗi console.

## Bổ sung 19/11/2026 · Phiên bản 5.55.1: Bong bóng chat cân đối

Ba chấm "đang gõ" trong bong bóng chat của thanh chào mừng bị dồn sang trái vì khung không căn giữa nội dung. Nay ba chấm nằm giữa (cách hai bên 12px, trên dưới 14px, đo trên Edge), bong bóng có thêm đuôi nhỏ ở góc dưới trái.

## Bổ sung 19/11/2026 · Phiên bản 5.56.0: Xếp hạng và lương cân đối hơn

**Vấn đề:** bảng xếp hạng chỉ rộng 509px nên tên bị cắt, cạnh đó thẻ "So với nhóm" chỉ cao khoảng 120px để lại khoảng trống lớn; ô chọn kỹ năng rơi xuống dòng riêng; thẻ Lương có ô +79% lơ lửng giữa vùng trống.

**Thay đổi** (`frontend/js/pages/rank.js`, cuối `frontend/css/app.css`):

- Bảng xếp hạng trải hết chiều ngang: tên hiện đầy đủ, cột tổng mức rộng hơn, bộ chọn cách xếp và ô chọn kỹ năng trên cùng một hàng.
- Khi chưa đủ người để so sánh nhóm, ghi chú một dòng nằm ở chân bảng (cạnh "Cách xếp hạng") thay vì một thẻ gần như trống. Khi có dữ liệu, "So với nhóm" và "Phân bố trình độ" đặt cạnh nhau dưới bảng.
- Thẻ Lương: biểu đồ cột bên trái (chú thích đường "Mọi mức kinh nghiệm" chuyển xuống dưới biểu đồ), bên phải là ba ô số liệu cao đều nhau: mức tăng theo kinh nghiệm, lương trung vị mọi mức kinh nghiệm, số người trả lời khảo sát (đều lấy từ nguồn lương đã có). Liên kết nguồn và "Về số liệu" ở chân thẻ.

**Kiểm chứng:**

- Toàn bộ bộ test: 1296 passed, 11 skipped (10 cần Gemini thật, 1 cần Docker).
- Edge thật trên bản sao dữ liệu (1440px, 1280px, 390px, giao diện tối, tiếng Anh): đổi cách xếp và lọc kỹ năng vẽ lại trang đúng, giữ thẻ Trợ lý; Chia sẻ sao chép đúng; "Hiện tên tôi" bật rồi tắt lại (chỉ trên bản sao); hộp Cách phân bậc, "Cách xếp hạng", "Về số liệu" mở được; liên kết nguồn lương đúng; nhãn nhóm kinh nghiệm trong ô +79% dịch đúng sang tiếng Anh; không tràn ngang; không lỗi console.
- Chưa xem được cách hiển thị "So với nhóm" và "Phân bố trình độ" cạnh nhau, vì bản sao dữ liệu chỉ có 4 học viên (dưới ngưỡng 5 người).

## Bổ sung 19/11/2026 · Phiên bản 5.56.1: Chữ "Đang tải dữ liệu..." ở giao diện tiếng Anh

**Lỗi:** ở chế độ tiếng Anh, màn hình chờ khi một trang đang tải vẫn hiện "Đang tải dữ liệu...".

**Nguyên nhân:** câu này là giá trị mặc định của tham số `loadingView(text = "...")` trong `frontend/js/core.js`. Công cụ quét chữ giao diện (`scripts/i18n_extract.py`, dùng trong `tests/test_i18n.py`) không đọc giá trị mặc định của tham số nên câu này chưa từng có bản dịch, và test không phát hiện được.

**Sửa:**

- Thêm "Loading data..." vào `frontend/js/lang/en.json`.
- Test mới `tests/test_i18n_literals.py`: đọc mọi chuỗi tiếng Việt nằm trong dấu nháy ở các tệp JavaScript của ứng dụng và yêu cầu có bản tiếng Anh. Lượt quét toàn bộ chỉ tìm thêm 4 chuỗi, đều không hiển thị nguyên dạng (bảng nhãn song ngữ riêng của nút giao diện, một đoạn nằm trong nhãn dài đã dịch, hai ví dụ trong chú thích); 4 chuỗi này được ghi rõ trong danh sách bỏ qua của test.

**Kiểm chứng:** toàn bộ bộ test 1298 passed, 11 skipped (thêm 2 test mới). Edge thật ở tiếng Anh, máy chủ được làm chậm 2,5 giây: màn hình chờ hiện "Loading data..." khi mở Bảng điều khiển, Học liệu và khi mở thẳng ứng dụng.

## Bổ sung 19/11/2026 · Phiên bản 5.57.0: Chuẩn hóa UI/UX toàn bộ giao diện

Đợt này thực hiện "MASTER PROMPT — COMPREHENSIVE UI/UX TRANSFORMATION & INTERACTION ENHANCEMENT". Chức năng, dữ liệu, cách chấm điểm và phân quyền giữ nguyên. Không có số liệu nào được tạo thêm: mọi con số mới trên giao diện đều là phép đếm trên dữ liệu trang đã tải từ API.

- Sao lưu trước khi sửa: thư mục cùng cấp `CareerAdapt_AI_backup_truoc_ui_ux_20261119` (gồm `frontend/`, `README.md`, `UPGRADE_REPORT.md`, `backend/config.py`).
- Checklist kiểm định nội bộ: `docs/UI_UX_CHECKLIST.md`.

### 1. Khảo sát ban đầu

- Rà 34 route (15 của học viên đã xong quy trình, 6 của học viên mới, 13 của quản trị viên) cùng trang đăng nhập.
- Mỗi route chạy trên Edge thật (Playwright, kênh `msedge`) ở 4 khổ màn hình, có giao diện tối và tiếng Anh, tổng cộng 350 lượt xem.
- Máy chủ chạy trên dữ liệu tạm, không mở `data/`.
- Kết quả khảo sát:
  - Không có lỗi console và không có trang nào tràn ngang.
  - Có 27 lượt xem tiếng Anh còn câu dịch dở, nửa Anh nửa Việt.
- `app.css` dài 3.174 dòng. Phân tích tự động cho thấy:
  - 125 khai báo chết, tức bị chính selector đó ghi đè ở phía sau;
  - 15 giá trị z-index rời rạc, 33 cỡ chữ (nhiều cỡ lẻ nửa pixel), 37 bán kính bo góc và 65 kiểu bóng đổ.
- Đo tương phản phát hiện 4 chỗ dưới chuẩn AA:
  - toast ở giao diện tối: 2,27:1 và 1,99:1;
  - số đếm trên chuông: 3,91:1;
  - chữ gợi ý ở ô đăng nhập: 2,81:1;
  - vòng focus trên nền navy: 2,73:1.

### 2. Design system

**Token mới.** Tệp `frontend/css/tokens.css` được nạp đầu tiên ở cả trang ứng dụng và trang đăng nhập. Nó chứa các thang sau:

| Nhóm | Token |
| --- | --- |
| Cỡ chữ | `--fs-2xs` … `--fs-6xl` (11,5 → 32px) |
| Độ đậm | `--fw-*` |
| Khoảng cách | `--sp-1` … `--sp-12` (lưới 4px) |
| Bo góc | `--radius-2xs` … `--radius-xl`, `--radius-pill` |
| Bóng đổ | `--shadow-xs/md/lg/xl`, có bản cho giao diện tối |
| Cỡ control | `--control-sm/md/lg`, `--touch` |
| Chuyển động | `--dur-1` … `--dur-5`, `--ease-standard/out/in/spring` |
| Lớp z-index | `--z-dropdown` … `--z-skip` |

Màu vẫn nằm ở bảng màu sẵn có: `:root` trong `app.css` và `--lp-*` trong `login.css`.

**Dọn CSS trùng lặp.** Đã gỡ 125 khai báo chết và 23 quy tắc rỗng. Để chứng minh giao diện không đổi:
- chụp computed style của mọi phần tử (cả `::before` và `::after`) trên 60 trạng thái trang (sáng/tối × 1440/390 × 15 route), tổng 23.432 phần tử, trước và sau khi dọn;
- khác biệt duy nhất là chữ "x phút trước" thay đổi theo thời gian và nhịp chớp mắt của robot.

**Đưa giá trị lên token.** Các giá trị lẻ được chuyển sang token:

| Loại giá trị | Số chỗ |
| --- | --- |
| Cỡ chữ | 361 |
| Độ đậm | 155 |
| Bo góc | 170 |
| Thời lượng chuyển động | 93 |
| z-index toàn cục | 13 |

Phần này nằm trong `app.css`, `effects.css`, `login.css` và `ambient.css`.

Một số giá trị cố ý giữ nguyên:
- số hiển thị cỡ lớn (36–44px);
- bo góc mảnh 2–3px;
- vòng lặp trang trí dài;
- z-index 0–3 dùng xếp lớp cục bộ.

Cỡ chữ lẻ được làm tròn: 12,5 → 13, 13,5 → 14, 14,5 → 15 và 17 → 18px.

### 3. Thành phần chung (`app.css`, `core.js`)

| Thành phần | Sau 5.57.0 |
| --- | --- |
| Nút | Cao 40px. Có focus nhìn thấy được, trạng thái nhấn, disabled kèm `aria-disabled`, và `aria-busy` khi đang xử lý. Thêm cỡ `btn-lg`. Viền nút nguy hiểm theo tông màu. |
| Ô nhập | Cùng chiều cao với nút. Có hover và trạng thái lỗi (`aria-invalid`, `:user-invalid`). Trạng thái disabled và readonly phân biệt rõ. Chữ gợi ý đạt AA. |
| Tab | `.tab[aria-selected=true]` được tô như tab đang mở. Mọi `[role=tablist]` (Quản trị, bộ lọc Nhắc nhở, tab Lộ trình) đi được bằng mũi tên, Home và End. Hồ sơ giữ cách xử lý phím riêng như trước. |
| Badge | Cùng chiều cao 22px. |
| Alert | Viền theo tông màu ở cả hai giao diện. |
| Toast | Có biểu tượng theo tông và nút đóng. Lỗi dùng `role="alert"` và hiện 7 giây. Di chuột hoặc focus vào thì dừng đếm giờ. Tối đa 4 toast. Toast nằm trên nút Trợ lý, không che nút nữa. Màu đỏ và xanh cố định nên đạt ≥ 5,9:1 ở cả giao diện tối. |
| Modal | Có `aria-labelledby` lấy từ tiêu đề. Phím Tab không thoát ra ngoài hộp thoại. Trang nền không cuộn và có bù độ rộng thanh cuộn. Đóng hộp thoại thì focus về nút đã mở nó. Nền mờ nhẹ, tiêu đề 18px. |
| Đang tải | Khi đổi trang hiện khung xương có `role="status"`. Khung xương chỉ hiện nếu tải lâu hơn 180 ms. Chỗ chờ nhỏ, như AI đang viết nhận xét, vẫn dùng vòng quay. |
| Trống / Lỗi | Trạng thái trống có biểu tượng. Màn lỗi có class `.error-view`, `role="alert"`, biểu tượng và nút "Thử lại". |

### 4. Micro-interaction (đều tắt khi bật `prefers-reduced-motion`)

- **Đổi trang:**
  - nội dung mới hiện mờ dần trong 300 ms; chỉ đổi opacity, nên các phần `fixed` và `sticky` không bị ảnh hưởng;
  - khi người dùng bấm link hoặc menu, focus chuyển về vùng nội dung để trình đọc màn hình bắt đầu từ trang mới.
- **Toast** trượt vào và trượt ra.
- **Danh sách chuông và menu hoãn nhắc** bật lên nhẹ.
- **Panel Trợ lý** trượt vào từ phải.
- **Hover:**
  - mục menu, tab, ô nhập và vùng thả tệp đổi màu êm;
  - thẻ bài kiểm tra đậm viền và đổ bóng rõ hơn;
  - bóng hover dùng `--shadow-md`.
- **Hàng cuộn ngang:** menu Kế hoạch dạng hàng, mục Quản trị trên điện thoại và các hàng tab có mép mờ ở phía còn nội dung. Mép mờ không phải chuyển động, nên vẫn hiện khi bật giảm chuyển động.
- **Có từ trước và được giữ:** thanh tiến độ chạy tới giá trị thật, số đếm tăng dần, gợn sóng khi nhấn, thẻ hiện dần.

### 5. Trang được làm lại

- **Kiểm tra kiến thức** (`tests.js`):
  - dùng `pageHero` chung, giống Kế hoạch, Quản trị và Đóng góp; thông báo "tách biệt với quy trình" thành dòng mô tả của hero;
  - 4 ô số liệu đếm từ API: số bài có sẵn, lượt đã nộp, lượt đang làm, điểm của lượt nộp gần nhất (hiện "—" khi chưa có);
  - có tiêu đề "Chọn bài" kèm phiên bản ngân hàng câu hỏi;
  - thẻ bài: điểm lần gần nhất dạng badge, viền nhấn khi đang làm dở, viền và bóng đậm hơn khi di chuột.
- **Học liệu** (`resources.js`):
  - hero có 3 số liệu đếm trên danh mục lúc tải đầu: số học liệu, số kỹ năng có học liệu, số nguồn cung cấp;
  - thanh lọc thành một hàng có ô tìm kiếm kèm biểu tượng; gợi ý trong ô ghi đúng các trường mà API thật sự tìm (tên, nhà cung cấp, kết quả học tập);
  - nút "Bỏ lọc";
  - dòng số kết quả có `aria-live` và nhận focus sau khi lọc.
- **Khai báo và JD:** tóm tắt JD khi thu gọn nay mờ dần ở cuối, không còn cắt ngang dòng "Yêu cầu chính".
- **Tất cả các trang** đều dùng chung token và các thành phần ở mục 3.

### 6. Lỗi đã sửa

1. Toast ở giao diện tối có chữ trắng trên đỏ nhạt và xanh nhạt (2,27:1 và 1,99:1).
2. Số đếm trên chuông đạt 3,91:1; nay 4,93:1.
3. Chữ gợi ý ở ô đăng nhập đạt 2,81:1; nay 4,72:1.
4. Vòng focus gần như không thấy trên thanh bên và các hero nền navy (2,73:1); nay là vòng trắng.
5. Tiếng Anh còn câu dịch dở, ví dụ "1 lần ghi nhận · gần nhất …", "ôn tập mặc định: 7-day cycle", "So sánh level đã xác thực…", "0 phút. studied" và "Level bị limitations ở 1".
   - Nguyên nhân: bộ dịch hiển thị (`translate.js`) tách câu theo "·" và dấu câu trước khi thử mẫu câu có biến. Vì vậy các mẫu đã có sẵn trong `en.json` không bao giờ được dùng.
   - Sửa: thêm `byWholePattern`, khớp nguyên dòng trước khi tách, và bổ sung 19 mục dịch.
   - Riêng câu "Mức bị giới hạn ở 1 vì…" bị chính máy chủ dịch từng cụm ("giới hạn" thành "limitations"). Đã thêm nguyên câu vào `data/i18n/sensitive_en.json`, để máy chủ thay cả câu trước các cụm ngắn.
   - Kết quả quét lại: chỉ còn tên người và tên tài liệu trong kho kiến thức quản trị, là dữ liệu gốc được phép giữ nguyên.
6. Màn lỗi chưa có class `.error-view`, nên kiểm tra `#view .error-view` trong `test_ui_e2e.py` luôn đạt mà không kiểm được gì. Nay class đã có và có test riêng cho màn lỗi.
7. Regex trong `esc()` chứa dấu nháy làm `scripts/i18n_extract.py` đọc lệch cả phần sau của `core.js`. Trước đây các đoạn đọc lệch phải đưa vào danh sách bỏ qua. Nay hai dấu nháy được viết dạng mã `\u0022\u0027`; hàm vẫn chạy như cũ.
8. Hộp thoại chưa giữ Tab bên trong, chưa trả focus khi đóng, chưa có tên cho trình đọc màn hình, và trang phía sau vẫn cuộn.
9. Toast che nút Trợ lý, không đóng được bằng tay, và lỗi không được đọc ngay.
10. Sau khi đổi trang, focus rơi về `<body>`.
11. Các tablist ngoài Hồ sơ không đi được bằng phím mũi tên.

### 7. Tệp đã sửa

- **Mới:**
  - `frontend/css/tokens.css`
  - `docs/UI_UX_CHECKLIST.md`
  - `tests/test_design_system.py`
- **CSS:**
  - `frontend/css/app.css`
  - `frontend/css/effects.css`
  - `frontend/css/login.css`
  - `frontend/css/ambient.css`
- **HTML:**
  - `frontend/index.html`, `frontend/login.html`: nạp `tokens.css`, phiên bản 5.57.0.
- **JavaScript:**
  - `frontend/js/core.js`
  - `frontend/js/main.js`
  - `frontend/js/effects.js`
  - `frontend/js/icons.js`: thêm `close` và `inbox`.
  - `frontend/js/translate.js`
  - `frontend/js/pages/tests.js`
  - `frontend/js/pages/resources.js`
  - `frontend/js/lang/en.json`
- **Khác:**
  - `data/i18n/sensitive_en.json`: thêm 1 câu.
  - `tests/test_ui_e2e.py`: thêm 5 test.
  - `backend/config.py`: `APP_VERSION = "5.57.0"`.
  - `README.md`
  - `UPGRADE_REPORT.md`

Các tệp CRLF vẫn giữ CRLF và các tệp LF vẫn giữ LF; đã kiểm bằng cách đếm byte.

### 8. Kiểm chứng

- **Toàn bộ bộ test:** `.venv/Scripts/python -m pytest -q -p no:cacheprovider` cho **1308 passed, 11 skipped**. Trước đợt này là 1298 passed, 11 skipped. 10 test mới:
  - 5 test trong `tests/test_design_system.py`: token, lớp z-index, cỡ chữ, không còn khai báo CSS chết;
  - 5 test Playwright trong `tests/test_ui_e2e.py`: focus về nội dung khi đổi trang; trạng thái trống và màn lỗi; hộp thoại giữ Tab bên trong và trả focus; toast có nút đóng; phím mũi tên ở mục Quản trị.
- **Rà soát trên Edge thật** (Playwright kênh `msedge`), máy chủ chạy trên dữ liệu tạm:
  - Ma trận 34 route cùng trang đăng nhập, tổng **350 lượt xem**. Các khổ đã chạy:
    - 1440, 1280, 1024 và 390 (giả lập điện thoại cảm ứng) ở giao diện sáng;
    - 1440, 1024 và 390 ở giao diện tối;
    - 1440 và 390 ở tiếng Anh, 1280 ở tiếng Anh với giao diện tối.
    - Kết quả: **0 lỗi console hoặc pageerror, 0 API 5xx, 0 trang tràn ngang**.
  - Route sâu: bài học trong Lộ trình, trình làm bài, báo cáo bài, bài đánh giá tổng hợp, bước 1 của Quy trình và Báo cáo năng lực. Tổng **42 lượt xem** ở 1440, 1280, 1024 và 390, sáng, tối và tiếng Anh. Kết quả: **0 lỗi, 0 tràn ngang**.
  - Ngoài ra đã chụp các trạng thái toast, hộp thoại, chuông, khung xương, màn lỗi và vòng focus ở cả hai giao diện. Có chụp thêm 5 trang khi bật chuyển động; không có lỗi.
- **Tiếng Anh:** quét chữ chưa dịch (`careerI18n.missing()`) sau khi sửa. Chỉ còn:
  - tên người dùng;
  - tên báo cáo nguồn ITviec, vốn được gắn `data-no-i18n` có chủ đích;
  - tên 2 tài liệu trong Kho kiến thức AI của quản trị viên;
  - tên bài thực hành trên trang bài học (xem mục 9).
- **CSS:** sau khi dọn, không còn khai báo chết nào. Mọi z-index toàn cục dùng token; không còn cỡ chữ lẻ nửa pixel. `app.css` dài 3.227 dòng; số dòng tăng vì có thêm khối thành phần và khối trang.
- **Database thật:** `data/accounts.sqlite3` và `data/careeradapt.sqlite3` giữ nguyên kích thước và thời điểm sửa (14:59 và 15:08, trước đợt này). Không đọc hay sửa `.env`.

### 9. Chưa kiểm chứng / chưa làm

- **Tên bài thực hành ở trang bài học, chế độ tiếng Anh.** Các tên như "Đọc và lọc dữ liệu bằng Pandas" vẫn hiện tiếng Việt, dù bản dịch đã có trong catalog riêng của máy chủ.
  - Nguyên nhân: API `/me/journey/...` không nằm trong `TRANSLATED_PATHS` của `backend/i18n.py`.
  - Chưa thêm, vì payload này có cả ghi chú do học viên tự viết, và quy tắc của dự án là không dịch chữ của học viên.
  - Cần quyết định trường nào được dịch trước khi sửa.
- **Trình đọc màn hình thật** (NVDA, Narrator) chưa được thử. Mới kiểm thuộc tính ARIA, thứ tự focus và vòng focus bằng Playwright.
- **Thiết bị thật** (điện thoại, máy tính bảng) chưa được thử. Khổ 390 và vùng chạm 44px được kiểm bằng giả lập `is_mobile` và `has_touch`.
- **Chuyển động** chủ yếu được kiểm ở chế độ giảm chuyển động, vì ảnh chụp cần ổn định. Khi bật chuyển động, mới chụp 5 trang ở trạng thái cuối và không có lỗi. Chưa quay lại toàn bộ chuỗi chuyển động.
- **Chưa mở được** `#/mini/:id` (cần một bài học đã xong để có bài kiểm tra học phần) và `#/result/:id` (đánh giá theo luồng cũ).
- **Trang giới thiệu** `/gioi-thieu` (`landing.html`) không thuộc ROUTES của ứng dụng nên không làm lại.
- **Tương phản** đã đo cho các cặp màu token và các chỗ đã sửa. Chưa đo tự động từng phần tử.
- **Phông chữ:** Inter không được đóng gói, nên Windows hiển thị bằng Segoe UI.
  - Độ đậm 650 và 750 cũ nay là 700 và 800. Trên Segoe UI hình dạng chữ không đổi.
  - Trên máy có Inter, chữ có thể đậm hơn một chút.

## Bổ sung 19/11/2026 · Phiên bản 5.57.1: Lỗi đã mắc ở trang bài học (tiếng Anh) và menu Quản trị

### Lỗi 1: thẻ "lỗi đã mắc" ở tiếng Anh vẫn hiện tiếng Việt

**Biểu hiện:** ở chế độ tiếng Anh, thẻ lỗi đã mắc trên trang bài học vẫn hiện tiếng Việt, ví dụ tên câu "Đọc và lọc dữ liệu bằng Pandas" và tiêu chí "Lọc theo status completed". Mục 9 của bản 5.57.0 ghi nhầm đây là tên bài thực hành; thật ra đó là nội dung đề thi trong thẻ lỗi đã mắc (trường `mistakes`).

**Nguyên nhân:**
- Bản dịch của đề thi chỉ nằm trong catalog riêng của máy chủ, `data/i18n/sensitive_en.json`. Trình duyệt không bao giờ nhận catalog này.
- Máy chủ chỉ dịch các API phòng thi và kiểm tra (`TRANSLATED_PATHS`), không dịch `/me/journey/lessons/...`.

**Sửa** (`backend/api/journey.py`):
- Ở tiếng Anh, chỉ dịch hai trường `topic` và `check` của mỗi lỗi bằng catalog đó.
- "Bài làm khi đó" (`answer_gave`, kết quả bài làm của học viên) và phần còn lại của trang được giữ nguyên.
- Không thêm đường dẫn nào vào `TRANSLATED_PATHS`, nên ghi chú học viên tự viết không bị đụng tới.

### Lỗi 2: menu Quản trị chưa dùng được ngay

Phát hiện khi viết test bàn phím, ở trang Quản trị:
- Các nút mục đã hiện nhưng chỉ hoạt động sau khi mục đầu tiên tải xong, vì hành động được đăng ký sau `await drawPane()`. Bấm chuột hay bấm phím trong khoảng đó đều bị bỏ qua.
- Khi số đếm tải xong, menu được vẽ lại và focus bàn phím rơi khỏi menu.

**Sửa** (`frontend/js/pages/admin.js`):
- Đăng ký hành động trước khi tải mục đầu tiên.
- Khi vẽ lại menu, đưa focus về đúng mục đang được focus.

### Test

`tests/test_lesson_mistakes_english.py` gồm 2 test:
- Ở tiếng Anh, tiêu chí và chủ đề nhận đúng bản dịch từ catalog. "Bài làm khi đó" và mọi trường khác giống hệt bản tiếng Việt.
- Ở tiếng Việt, chữ gốc giữ nguyên.

Đã thử tắt bản sửa: test thất bại; bật lại thì đạt. Test bàn phím của Quản trị chạy lặp 3 lần đều đạt; trước khi sửa, 2 trong 3 lần thất bại.

### Kiểm chứng

- Toàn bộ bộ test: **1310 passed, 11 skipped**.
- Kiểm trên Edge thật, trang bài học ở tiếng Anh và tiếng Việt, khổ 1280 và 390:
  - không có lỗi console và không tràn ngang;
  - quét chữ chưa dịch không còn mục nào, ngoài tên người dùng.
- **Database thật:** lúc 17:31 thời điểm sửa của `data/careeradapt.sqlite3` đổi, và tệp `-wal` vẫn tiếp tục được ghi.
  - Nguyên nhân là máy chủ thật của người dùng: `run.py`, cổng 8000, chạy từ 10:52. Tệp `-shm` được tạo lúc 10:52:26, đúng lúc máy chủ này khởi động.
  - Đợt này không mở database thật: pytest dùng database trong bộ nhớ, còn máy chủ thử chạy trên thư mục dữ liệu tạm.
  - Vì vậy câu "giữ nguyên thời điểm sửa" ở mục 8 của bản 5.57.0 chỉ đúng tại lúc kiểm tra đó.
  - Máy chủ đang chạy vẫn dùng mã backend cũ. Cần khởi động lại `run.py` thì phần dịch lỗi đã mắc và số phiên bản 5.57.1 mới có hiệu lực; phần frontend có hiệu lực ngay sau khi tải lại trang.

### Tệp đã sửa

- `backend/api/journey.py`
- `frontend/js/pages/admin.js`
- `tests/test_lesson_mistakes_english.py` (mới)
- Phiên bản 5.57.1 ở `backend/config.py`, `frontend/index.html`, `frontend/login.html`, `README.md`

## Bổ sung 19/11/2026 · Phiên bản 5.57.2: Báo cáo năng lực không còn gọi API khi chưa có bài

**Lỗi:** khi thử bản clone mới từ GitHub, mở Báo cáo năng lực bằng tài khoản chưa làm bài kiểm tra thì console có lỗi "Failed to load resource … 409".
- Trang vẫn gọi `/career-process/exam/review`, và máy chủ trả 409 vì chưa có bài đã chấm.
- Giao diện đã xử lý đúng: trang hiện "Chưa có dữ liệu để lập báo cáo" hoặc "Chưa có bài kiểm tra đã chấm".
- Tuy vậy, trình duyệt vẫn ghi request bị từ chối thành lỗi. Hành vi này có từ bản 5.48.

**Sửa** (`frontend/js/pages/report.js`):
- Đọc `/me/gap` trước.
- Chỉ gọi API kết quả bài làm khi đã có ít nhất một kỹ năng có bằng chứng.
- Các API còn lại vẫn được gọi song song như cũ.

**Test:** thêm `#/report` vào danh sách trang của `tests/test_ui_e2e.py`. Danh sách này kiểm tra không lỗi console và không tràn ngang, trên máy tính và điện thoại. Hai test này thất bại với mã cũ và đạt với mã mới.

**Kiểm chứng:**
- Toàn bộ bộ test: **1312 passed, 11 skipped**.
- Trên Edge, học viên đã làm bài vẫn thấy đủ phần điểm (85/100, Đạt). Học viên đang làm dở quy trình thấy "Chưa có bài kiểm tra đã chấm". Cả hai trường hợp đều không có lỗi console.

**Kiểm thử bản clone (bản 5.57.1, trước bản sửa này):**
- Clone commit c87e596 từ GitHub vào thư mục tạm, tạo venv Python 3.13 mới và cài `requirements.txt` và `requirements-dev.txt`: không lỗi.
- `run.py` chạy ở cổng 8790 và báo phiên bản 5.57.1.
- Trên Edge, ở khổ 1440 sáng tiếng Việt và khổ 390 tối tiếng Anh: đăng ký, đăng nhập, mở 7 trang chính và Trợ lý AI đều không tràn ngang. Lỗi console duy nhất là dòng 409 đã sửa ở trên.
- Bộ test trên bản clone: 1310 passed, 11 skipped.

## Bổ sung 19/11/2026 · Phiên bản 5.58.0: Thu gọn thanh bên và menu Kế hoạch để có thêm chỗ làm việc

**Yêu cầu:** có cách ẩn thanh điều hướng navy bên trái và menu dọc của Kế hoạch Career Adapt, để vùng nội dung rộng hơn.

**Cách làm:** hai thanh không ẩn hẳn mà thu thành một cột chỉ còn biểu tượng. Như vậy vẫn chuyển trang được bằng một cú bấm, trong khi phần lớn bề ngang được trả lại cho nội dung.

**Thanh bên chính:**
- Nút mới nằm ở đầu thanh trên cùng, cạnh tên trang (`#rail-btn`, `aria-controls="sidebar"`, có `aria-expanded`).
- Khi thu gọn, thanh còn 76px:
  - logo chỉ còn hình;
  - tiêu đề nhóm thành vạch ngăn;
  - mục menu chỉ còn biểu tượng; rê chuột thì hiện tên, và trình đọc màn hình vẫn đọc được tên;
  - thẻ Trợ lý AI và dòng ghi chú cuối thanh được ẩn. Nút "Trợ lý" nổi ở góc vẫn mở trợ lý như cũ.
- Chỉ có tác dụng từ 821px trở lên. Hẹp hơn thì thanh bên vẫn là ngăn kéo mở bằng nút ☰.

**Menu Kế hoạch:**
- Nút "Thu gọn menu" nằm ở đầu menu dọc.
- Khi thu gọn, menu còn 68px; mỗi mục chỉ còn biểu tượng, có tên khi rê chuột.
- Chỉ có tác dụng từ 1200px trở lên. Hẹp hơn thì menu vẫn là hàng ngang như trước.

**Chung cho cả hai:**
- Lựa chọn được nhớ trong trình duyệt (`localStorage`). `boot.js` áp lựa chọn đó trước khi trang hiện, nên trang không bị giật khi mở.
- Khi thanh bên thu gọn, vùng nội dung được rộng tối đa 1440px thay vì 1320px.
- Hiệu ứng co giãn tắt khi bật giảm chuyển động.
- Không có dữ liệu hay chức năng nào thay đổi.

**Kết quả đo trên Edge (trang Khoảng cách kỹ năng, bề rộng vùng nội dung):**

| Khổ màn hình | Trước | Sau khi thu gọn |
| --- | --- | --- |
| 1440, thu cả hai thanh | 866px | 1218px |
| 1024, thu thanh bên | 764px | 948px |

- Ở 1280px với tiếng Anh, nhãn nút đổi đúng ("Expand sidebar", "Expand menu").
- Ở 390px, hai nút ẩn và nút ☰ vẫn hoạt động.
- Tải lại trang vẫn giữ trạng thái thu gọn. Bấm Enter trên nút mở lại được.
- Không có lỗi console, không tràn ngang.

**Tệp:**
- `frontend/js/layout.js` (mới)
- `frontend/js/boot.js`
- `frontend/js/main.js`
- `frontend/js/pages/plan.js`
- `frontend/index.html`
- `frontend/css/app.css`
- `frontend/js/lang/en.json`: 4 nhãn mới
- `tests/test_ui_e2e.py`: 2 test mới
- Phiên bản 5.58.0 ở `backend/config.py`, `frontend/index.html`, `frontend/login.html`, `README.md`

**Kiểm chứng:**
- Toàn bộ bộ test: **1314 passed, 11 skipped**.
- Test mới, thu gọn cả hai thanh: kiểm `aria-expanded`, tên hiện khi rê chuột, độ rộng thanh bên ≤ 80px, nội dung rộng thêm hơn 300px, trạng thái còn giữ sau khi tải lại, và mở lại bằng bàn phím.
- Test mới trên điện thoại: nút thu gọn ẩn, nút ☰ còn hiện.

## Bổ sung 19/11/2026 · Phiên bản 5.58.1: Tooltip riêng cho mục đã thu gọn

**Yêu cầu:** dòng chữ hiện ra khi rê chuột vào một mục đã thu gọn trông chưa đẹp. Đó là tooltip mặc định của trình duyệt (thuộc tính `title`), một hộp xám nhỏ không chỉnh kiểu được.

**Thay đổi:**
- Bỏ thuộc tính `title` ở các mục đã thu gọn và ở hai nút thu gọn.
- Thay bằng tooltip riêng của ứng dụng (`.nav-tip`, trong `frontend/js/layout.js`):
  - Kiểu dáng: nền navy chữ trắng ở giao diện sáng, nền sáng chữ navy ở giao diện tối. Chữ 13px, đậm vừa, bo góc 10px, có bóng đổ.
  - Vị trí: có mũi nhọn chỉ đúng vào biểu tượng. Tooltip nằm bên phải mục, hoặc bên dưới với nút thu gọn thanh bên. Nếu sát mép màn hình, tooltip được đẩy vào trong nhưng mũi nhọn vẫn chỉ đúng mục.
  - Hiển thị: hiện mờ dần và trượt nhẹ trong 150 ms (tắt khi bật giảm chuyển động). Có khi rê chuột, và có cả khi dùng phím Tab, điều tooltip mặc định không làm được.
  - Tooltip ẩn khi bấm chuột, cuộn trang, đổi trang hoặc nhấn Esc. Tooltip không chặn chuột.
- Tên mục vẫn nằm trong liên kết cho trình đọc màn hình. Bản thân tooltip được ẩn khỏi trình đọc màn hình (`aria-hidden`) để tên không bị đọc hai lần.
- Nút "Thu gọn menu" khi menu đang mở đã có chữ trên nút, nên không hiện tooltip.

**Kiểm chứng:**
- Toàn bộ bộ test: **1314 passed, 11 skipped**.
- Test giao diện kiểm: liên kết không còn `title`; tooltip hiện đúng tên khi rê chuột và tắt khi rời chuột; tooltip hiện khi focus bằng bàn phím; tên truy cập của liên kết vẫn đúng.
- Đã chụp ảnh trên Edge (khổ 1280, sáng và tối) cho menu Kế hoạch, thanh bên và nút thu gọn. Không có lỗi console.

**Tệp:**
- `frontend/js/layout.js`
- `frontend/css/app.css`
- `tests/test_ui_e2e.py`
- Phiên bản 5.58.1 ở `backend/config.py`, `frontend/index.html`, `frontend/login.html`, `README.md`

## Bổ sung 19/11/2026 · Phiên bản 5.59.0: Biểu tượng mới cho Bảng điều khiển, Quy trình và Kế hoạch

**Yêu cầu:** thiết kế lại biểu tượng của Bảng điều khiển (trang chủ), Quy trình Career Adapt và Kế hoạch Career Adapt cho đẹp, đồng bộ và hiện đại hơn.

**Trước đây:**
- Ba trang dùng các biểu tượng chung của bộ icon: ngôi nhà, bia bắn và biểu đồ cột.
- Biểu tượng của Bảng điều khiển còn không thống nhất: menu bên dùng ngôi nhà, còn tiêu đề trang dùng lưới ô vuông.

**Thiết kế mới** (`frontend/js/icons.js`, nhóm `DUO`):
- Kiểu hai tông: nét viền như cả bộ icon, cộng một mảng tô nhạt cùng màu.
- Cùng lưới 24px, cùng độ dày nét 1,8 và cùng kiểu đầu nét tròn như các biểu tượng khác.

| Trang | Biểu tượng mới | Mảng tô |
| --- | --- | --- |
| Bảng điều khiển (`dashboard`) | Bố cục bảng điều khiển: một ô dọc lớn và hai ô nhỏ | Ô lớn |
| Quy trình Career Adapt (`journey`) | Dòng thời gian các bước: ba bước tròn nối dọc, mỗi bước có một dòng | Hai bước đầu, gợi ý "đang tiến triển" |
| Kế hoạch Career Adapt (`plan`) | Bảng kế hoạch có đường đi lên | Thanh tiêu đề của bảng |

- Mảng tô nhạt hơn khi bình thường và đậm hơn khi rê chuột hay khi đang ở trang đó.
- Khi chọn mẫu đã thử thêm hai phương án và bỏ đi:
  - "đường uốn tới lá cờ": quá giống biểu tượng Lộ trình học tập;
  - "ba nút nối zic-zắc": dễ bị đọc nhầm thành biểu tượng Chia sẻ.

**Áp dụng ở:**
- menu bên, cả khi mở và khi thu gọn;
- tiêu đề trang trên thanh trên cùng;
- hero của trang Quy trình;
- thẻ dẫn tới Kế hoạch trên Bảng điều khiển.

Các màn khác đang dùng `chart` và `target` cho dữ liệu (biểu đồ, mục tiêu) giữ nguyên.

**Kiểm chứng:**
- Toàn bộ bộ test: **1314 passed, 11 skipped**.
- Chụp trên Edge (khổ 1280, độ phân giải gấp đôi), ở giao diện sáng và tối, gồm menu mở, menu thu gọn, tiêu đề, hero và thẻ dẫn trang. Không có lỗi console.

**Tệp:**
- `frontend/js/icons.js`
- `frontend/js/main.js`
- `frontend/js/pages/dashboard.js`
- `frontend/js/pages/process.js`
- `frontend/css/app.css`
- Phiên bản 5.59.0 ở `backend/config.py`, `frontend/index.html`, `frontend/login.html`, `README.md`

## Bổ sung 19/11/2026 · Phiên bản 5.59.1: Đầu trang cân đối hơn

**Yêu cầu:** phía trái thanh trên cùng gồm nút thu gọn, biểu tượng trang và tiêu đề trông chưa cân đối.

**Nguyên nhân:**
- Biểu tượng trang (`#page-icon`) là một thẻ `span` thường nằm theo dòng chữ, nên nó lệch lên so với tiêu đề.
- Biểu tượng chỉ cao 24px, đứng trơ trọi cạnh nút tròn 40px có viền.

**Sửa** (`frontend/css/app.css`):
- Biểu tượng trang nằm trong một ô vuông bo góc 40px, cùng cao với nút thu gọn và các nút khác trên thanh. Ô có nền màu thương hiệu nhạt, nền đậm hơn ở giao diện tối, và được căn giữa theo tiêu đề.
- Một vạch ngăn mảnh tách nút thu gọn khỏi cụm "biểu tượng + tiêu đề".
- Khoảng cách giữa ô và tiêu đề tăng từ 12 lên 14px; dòng tiêu đề có `line-height` 1,2 để căn giữa chính xác.
- Ở khổ 820px trở xuống, ô biểu tượng ẩn đi như biểu tượng cũ.

**Kiểm chứng:**
- Đo trên Edge ở khổ 1280 (sáng, tối, thanh bên thu gọn): nút, ô biểu tượng và tiêu đề có cùng tâm dọc (35px); nút và ô cùng cao 40px.
- Ở khổ 390 bố cục giữ như trước. Không có lỗi console.
- Toàn bộ bộ test: **1314 passed, 11 skipped**.

## Bổ sung 19/11/2026 · Phiên bản 5.59.2: Tiêu đề trang không còn bị cắt chân chữ

**Lỗi:** bản 5.59.1 đặt chiều cao dòng của tiêu đề trang bằng 1,2 lần cỡ chữ. Tiêu đề có `overflow: hidden` để hiện dấu "…" khi quá dài, nên phần chân của chữ "g", "y" trong các tiêu đề như "Đóng góp câu hỏi" bị cắt.

**Sửa** (`frontend/css/app.css`, `.topbar h1`): chiều cao dòng tăng lên 1,4 và chừa thêm 1px ở dưới. Tiêu đề vẫn căn giữa với ô biểu tượng.

**Kiểm chứng:**
- Đo trên Edge: chiều cao nội dung của tiêu đề bằng chiều cao khung (29/29px ở khổ 1280, 26/26px ở khổ 390), nghĩa là không còn phần nào bị cắt. Tiêu đề và ô biểu tượng vẫn cùng tâm dọc 35px.
- Đã kiểm ở giao diện sáng, tối và tiếng Anh.
- Toàn bộ bộ test: **1314 passed, 11 skipped**.

## Bổ sung 19/11/2026 · Phiên bản 5.59.3: Tăng hạn chờ AI khi Gemini chậm

**Bối cảnh:**
- Gọi thẳng Gemini (`gemini-3.5-flash-lite`) cho thấy mỗi câu hỏi ngắn mất 10–30 giây. Có lần dịch vụ trả HTTP 503 "This model is currently experiencing high demand".
- Một câu hỏi gửi Trợ lý cần 2–3 lượt gọi. Vì vậy với hạn chờ cũ, nhiều câu hỏi bị quá giờ và Trợ lý phải trả lời theo quy tắc thay vì do AI viết.

**Thay đổi trong `.env`** (được làm theo yêu cầu của người dùng; tệp này không đưa lên GitHub):

| Biến | Cũ | Mới |
| --- | --- | --- |
| `LLM_TIMEOUT_SECONDS` | 60 | 120 |
| `AI_REQUEST_DEADLINE_SECONDS` | 150 | 240 |
| `LLM_MAX_RETRIES` | 2 | 3 |

Thêm một lần thử lại giúp vượt qua các lỗi 503 tạm thời. Các dòng khác của `.env` giữ nguyên, và khóa API không bị đọc ra hay in ra.

**Thay đổi trong code** (`backend/api/learning_tasks.py`):
- Trợ lý chat và các tác vụ AI chạy không giữ khóa của học viên.
- Riêng "Nhận xét AI" cho bài kiểm tra học phần (`POST /micro-tests/{id}/ai-feedback`) chạy trong lúc giữ khóa, mà khóa chỉ giữ tối đa 120 giây (`CAREERADAPT_USER_LOCK_LEASE`).
- Vì vậy thời gian chờ AI ở route này được giới hạn ở `min(AI_REQUEST_DEADLINE_SECONDS, thời hạn khóa − 15)`, tức 105 giây. Khóa không bao giờ hết hạn khi yêu cầu chưa xong, dù hạn chờ chung đã tăng lên 240 giây.

**Lưu ý khi kiểm thử:** dưới pytest, `backend/config.py` cố ý không đọc `.env`. Test Gemini thật vì thế dùng giá trị mặc định 20/45 giây và thử lại 2 lần, trừ khi đặt biến môi trường. Muốn mô phỏng đúng ứng dụng, chạy:
`CAREERADAPT_LIVE_AI=1 LLM_TIMEOUT_SECONDS=120 AI_REQUEST_DEADLINE_SECONDS=240 LLM_MAX_RETRIES=3 python -m pytest tests/test_ai_live.py`

**Kiểm chứng:**
- Ứng dụng đọc đúng giá trị mới (`config.LLM_TIMEOUT_SECONDS = 120`, `config.AI_REQUEST_DEADLINE_SECONDS = 240`).
- 10 test Gemini thật với đúng cấu hình đó: **10/10 đạt**. Các luồng Trợ lý mất 22–51 giây.
- Docker Desktop đã được bật và image `careeradapt-sandbox:1` (518 MB) đã được build, nên test sandbox Docker thật chạy được và đạt.
- Toàn bộ bộ test: **1315 passed, 10 skipped**. 10 test bỏ qua là test Gemini thật, chỉ chạy khi đặt `CAREERADAPT_LIVE_AI=1`.

**Cần làm:** khởi động lại `run.py` để máy chủ đang chạy nạp `.env` và code mới.

## Bổ sung 20/11/2026 · Phiên bản 5.60.0: Trang phục tốt nghiệp cho robot AI và ba biểu tượng cùng cỡ

### 1. Thân robot AI

Robot xuất hiện ở ba nơi: thanh chào mừng của Bảng điều khiển, khung Trợ lý và màn hoàn tất Quy trình. Cả ba dùng chung hình vẽ thân trong `frontend/js/bot.js`. Phần đầu là ảnh vẽ tay của nhóm và giữ nguyên; chỉ phần thân được vẽ lại.

**Trang phục mới, áo tốt nghiệp công nghệ hợp với mũ cử nhân trên đầu:**
- Vạt áo màu xanh hoàng gia mở hai bên thân trắng. Mặt trước vẫn để lộ màn hình "AI".
- Dải khăn tốt nghiệp (stole) màu vàng, cùng tông với tua mũ. Khăn có đường chỉ sáng ở giữa và một viên đá xanh ở mỗi đầu.
- Áo choàng phía sau có viền sáng ở hai mép và đường viền vàng ở gấu.
- Vai có vòng đèn xanh; cổ áo có đường may phát sáng.
- Cổ tay áo màu xanh có vạch đèn.
- Màn hình "AI" có khung viền chuyển màu và vầng sáng bao quanh, thêm hai đường quét mờ bên trong.
- Năm thanh sóng âm thay cho ba đèn tròn cũ.
- Viền sáng bên phải thân, đón ánh sáng của cảnh nền.
- Ba tia lửa nhỏ dưới ống phản lực.

**Hiệu ứng mới**, chỉ chạy khi người dùng không bật giảm chuyển động:
- thanh sóng âm nhấp nhô lệch nhịp như đang nói;
- khung màn hình "thở" sáng lên rồi mờ đi;
- vòng đèn vai, đường may cổ, cổ tay áo và viền sáng nhấp nháy nhẹ;
- hai viên đá ở đầu khăn lần lượt lóe sáng;
- tia lửa rơi từ ống phản lực.

Khi rê chuột vào cảnh, thanh sóng âm và khung màn hình chạy nhanh gấp đôi.

Khi bật giảm chuyển động, robot đứng yên và chỉ còn mắt chớp như quy ước cũ. Thanh sóng âm khi đó đứng ở độ cao so le để vẫn có nhịp điệu.

**Dọn CSS:**
- Trước đây robot ở Bảng điều khiển và robot trong Trợ lý có hai bộ quy tắc trùng nhau. Nay dùng chung một bộ `:is(.hero-bot-body, .as-bot-body)`; chỉ riêng nhịp vẫy tay là khác nhau.
- Bỏ quy tắc và `@keyframes` của ba đèn LED cũ.
- Hiệu ứng sáng của chữ "AI" chỉ đổi độ trong suốt. Trước đây nó dùng CSS `filter`, làm tạm mất bộ lọc phát sáng gốc của chữ.
- Giữ nguyên các id và class mà test đang kiểm (`#hb-shell`, `#as-shell`, `svg.as-bot-body`).

### 2. Ba biểu tượng Bảng điều khiển, Quy trình, Kế hoạch cùng cỡ

**Trước đây:** biểu tượng Bảng điều khiển trông to và đậm nhất, Quy trình (vài nét mảnh) trông nhỏ và nhạt nhất.

**Sửa** (`frontend/js/icons.js`, nhóm `DUO`):
- Cả ba được vẽ vừa đúng một ô 16×16 trên lưới 24px. Đo trên Edge bằng `getBBox`, cả ba đều 16,0 × 16,0 tại điểm (4, 4).
- Biểu tượng Quy trình được vẽ lại thành ba hàng, mỗi hàng gồm một chấm và một thanh bo tròn; hai hàng đầu được tô. Nhờ vậy độ đậm tương đương hai biểu tượng còn lại.
- Phương án trước đó (ba nút tròn lớn) bị bỏ vì các nút dính vào nhau.
- Biểu tượng Kế hoạch được nới thêm 0,2 đơn vị mỗi bên cho đúng ô.

### Kiểm chứng
- Chụp trên Edge ở độ phân giải gấp 3, cả giao diện sáng và tối, ở Bảng điều khiển và trong Trợ lý.
- Chụp khi đang chuyển động: tay vẫy, thanh sóng âm và tia lửa hiện đúng.
- Kiểm tra `animationName` của từng phần: 14 phần đều có chuyển động.
- Không có lỗi console.
- Toàn bộ bộ test: **1315 passed, 10 skipped**. 10 test bỏ qua là test Gemini thật.

### Tệp
- `frontend/js/bot.js`
- `frontend/js/icons.js`
- `frontend/css/app.css`
- Phiên bản 5.60.0 ở `backend/config.py`, `frontend/index.html`, `frontend/login.html`, `README.md`

## Bổ sung 20/11/2026 · Phiên bản 5.61.0: Mọi biểu tượng trên thanh bên cùng cỡ

**Yêu cầu:** cân lại kích thước các biểu tượng trên thanh bên cho đều nhau.

**Nguyên nhân:**
- Sau bản 5.59–5.60, Bảng điều khiển, Quy trình và Kế hoạch dùng biểu tượng hai tông mới, cao 16 đơn vị trên lưới 24.
- Học liệu, Kiểm tra kiến thức, Đóng góp câu hỏi, Hồ sơ và Quản trị vẫn dùng biểu tượng chung cũ. Các biểu tượng này cao 17–18 đơn vị và chỉ có nét viền, nên trông to nhỏ, đậm nhạt khác nhau.

**Sửa** (`frontend/js/icons.js`, nhóm `DUO`): thêm năm biểu tượng hai tông cùng kiểu.

| Mục | Biểu tượng | Mảng tô |
| --- | --- | --- |
| Học liệu (`learn`) | Cuốn sách có gáy trang | Bìa sách |
| Kiểm tra kiến thức (`test`) | Bảng kẹp có dấu tích | Kẹp giấy |
| Đóng góp câu hỏi (`write`) | Bút viết trên một dòng | Đầu bút |
| Hồ sơ (`account`) | Người | Đầu |
| Quản trị (`admin`) | Khiên có dấu tích | Nửa trái khiên |

- Mọi biểu tượng đều cao 16 đơn vị. Hình vuông rộng 16; hình dáng đứng (sách, bảng kẹp, bút, người, khiên) rộng 15 để nhìn cân về thị giác.
- Tất cả cùng nét 1,8 và có mảng tô nhạt cùng màu, đậm hơn khi rê chuột hay khi đang ở trang đó.
- Áp dụng ở thanh bên (mở và thu gọn), ô biểu tượng ở tiêu đề trang, hero của trang Học liệu, Kiểm tra kiến thức, Đóng góp câu hỏi, Quản trị, và hai thẻ dẫn trang trên Bảng điều khiển.
- Các chỗ khác đang dùng `book`, `quiz`, `pen`, `user`, `shield` (thẻ học liệu, bài kiểm tra học phần, bài tổng hợp…) giữ nguyên.

**Kiểm chứng:**
- Đo bằng `getBBox` trên Edge, với tài khoản học viên và tài khoản quản trị (đủ 8 mục):
  - Bảng điều khiển, Quy trình, Kế hoạch: 16,0 × 16,0;
  - Học liệu, Kiểm tra kiến thức, Hồ sơ, Quản trị: 15,0 × 16,0;
  - Đóng góp câu hỏi: 15,1 × 16,0.
- Đã chụp thanh bên thu gọn ở giao diện sáng và tối, cùng ô biểu tượng ở tiêu đề trang. Không có lỗi console.
- Toàn bộ bộ test: **1315 passed, 10 skipped**.

**Tệp:**
- `frontend/js/icons.js`
- `frontend/js/main.js`
- `frontend/js/pages/dashboard.js`
- `frontend/js/pages/resources.js`
- `frontend/js/pages/tests.js`
- `frontend/js/pages/contribute.js`
- `frontend/js/pages/admin.js`
- Phiên bản 5.61.0 ở `backend/config.py`, `frontend/index.html`, `frontend/login.html`, `README.md`

## Bổ sung 20/11/2026 · Phiên bản 5.62.0: Cảnh chào mới của Trợ lý và AI xuất hiện theo ngữ cảnh

### 1. Cảnh chào trong khung chat AI

Cảnh này hiện ở đầu khung Trợ lý khi cuộc trò chuyện còn trống. Mã nằm ở `frontend/js/assistant.js` (`stage()`) và CSS khối 5.62. Cảnh được dựng lại thành ba lớp:
- **Lớp sau:** hai vầng cực quang (xanh ngọc, tím) trôi chậm, lưới chấm mờ dần ra mép, hai vòng sáng xoay như cũ, và một quỹ đạo elip có ba vệ tinh phát sáng chạy quanh robot (`offset-path`).
- **Lớp giữa:** sóng âm hai bên, nay có quầng sáng, và các tia lấp lánh.
- **Lớp trước:** bong bóng kiểu kính mờ (`backdrop-filter`):
  - một bong bóng đang gõ "…";
  - một bong bóng lần lượt hiện bốn biểu tượng kỹ năng mà Trợ lý đọc (dữ liệu, code, biểu đồ, viết);
  - một huy hiệu tích xanh nhấp nhịp.

Các hiệu ứng khác:
- **Chiều sâu:** ba lớp dịch theo con trỏ chuột với mức khác nhau (−5 / 4 / 9px), nên cảnh có chiều sâu.
- **Rê chuột:** vòng sáng quay nhanh hơn và robot vẫy tay như trước.
- **Giảm chuyển động:** mọi lớp đứng yên, kể cả hiệu ứng chiều sâu; robot chỉ còn chớp mắt.
- Tất cả chỉ để trang trí (`aria-hidden`), không thêm số liệu nào.

### 2. AI xuất hiện theo ngữ cảnh

Module mới `frontend/js/companion.js`. Robot AI không còn chỉ đứng cố định ở nút "Trợ lý". Khi người dùng cuộn tới phần trang mà AI có thể giúp, robot hiện lên từ góc phải trên của phần đó: đầu robot (khuôn mặt có biểu cảm) nhô qua mép thẻ, kèm bong bóng kính mờ. Robot "gõ" một nhịp, nói một câu ngắn, và đưa ra một hoặc hai câu hỏi gửi thẳng cho Trợ lý thật (`askAssistant`, gồm cả các tác vụ AI của máy chủ). Xong việc, robot tự lui đi.

| Trang | Robot xuất hiện ở | Câu hỏi đưa cho Trợ lý |
| --- | --- | --- |
| Bảng điều khiển (đã có tiến độ) | thẻ Tổng quan tiến độ | Tổng hợp hành trình · Tôi nên học gì tiếp theo |
| Bảng điều khiển (mới bắt đầu) | thẻ dẫn tới Kế hoạch | Giải thích 6 bước của Quy trình |
| Học liệu | thẻ học liệu đầu tiên | Tôi nên học gì tiếp theo · Gợi ý học liệu cho kỹ năng còn thiếu |
| Kiểm tra kiến thức | thẻ bài đầu tiên | Nên luyện bài nào trước · Phân tích kỹ năng |
| Báo cáo năng lực | bảng kỹ năng | Tổng hợp hành trình · Viết phần kỹ năng trong CV đúng với kết quả đã xác thực |
| Trang bài học có lỗi đã mắc | thẻ "Lỗi bạn đã mắc" | Giải thích đúng tiêu chí đã sai (tên tiêu chí lấy từ thẻ) |
| Trang bài học chưa có lỗi | bài thực hành | Gợi ý hướng làm theo bước, không đưa đáp án hoàn chỉnh |
| Hồ sơ, tab Mục tiêu | bảng mục tiêu | Gợi ý số giờ học mỗi tuần để kịp lộ trình |

**Quy tắc để robot hữu ích mà không làm phiền:**
- **Thời điểm:** robot chỉ đến khi phần trang ở trong màn hình ít nhất 0,9 giây. Mỗi lần mở trang chỉ một robot, và mỗi gợi ý chỉ một lần trong phiên.
- **Lúc rời đi:** robot tự rời sau 16 giây nếu không được dùng (dừng đếm khi rê chuột hay focus vào bong bóng). Robot cũng rời khi phần trang bị cuộn khuất, khi đổi trang, khi mở khung Trợ lý hay một hộp thoại, hoặc khi nhấn Esc.
- **Không bao giờ xuất hiện khi đang làm bài:** robot không đến các trang làm bài (`/flow`, `/tests/run`, `/mini`, `/final-exam`), khi Trợ lý bị khóa vì có bài đang mở, hay khi tab trình duyệt bị ẩn.
- **Bật/tắt:** nút "Tắt gợi ý trên các trang" ngay trong bong bóng, và công tắc "Hiện gợi ý của Trợ lý AI trên các trang" trong Hồ sơ > Nhắc nhở. Lựa chọn lưu trên trình duyệt.
- **Trên điện thoại** (dưới 720px), bong bóng thành một dải phía trên nút Trợ lý.
- **Trợ năng:** câu nói được đọc qua vùng `aria-live`; nút đóng có nhãn; có vùng chạm 44px trên màn hình cảm ứng; không giành focus của người dùng.

**Ranh giới:**
- Robot chỉ đọc chữ đang hiển thị trên trang và chuyển câu hỏi đi. Câu trả lời đến từ Trợ lý, dựa trên dữ liệu của chính học viên và kho kiến thức đã duyệt.
- Robot không chấm điểm, không quyết định và không viết câu hỏi.
- Có chủ đích không đặt robot ở:
  - Đóng góp câu hỏi, vì dự án không dùng câu hỏi do AI viết;
  - báo cáo bài kiểm tra kiến thức, vì Trợ lý không có công cụ đọc dữ liệu này;
  - các mục Kế hoạch và các bước Quy trình, vì ở đó đã có thẻ cố vấn AI và robot hướng dẫn;
  - trang Quản trị.

### Kiểm chứng

Trên Edge, với server chạy trên dữ liệu tạm:
- Bảng điều khiển: robot đến bên thẻ tiến độ. Bấm "Tổng hợp hành trình của tôi" thì Trợ lý mở và chạy tác vụ, robot rời đi. Quay lại trang thì robot không đến nữa.
- Học liệu: robot đến khi cuộn tới thẻ đầu tiên, và rời khi bấm đóng.
- Trang bài học: robot nói "Lần trước bạn chưa đạt “Code đúng cú pháp Python”…" và gửi đúng câu hỏi có tên tiêu chí đó.
- Tắt từ bong bóng thì giá trị `off` được lưu, và công tắc trong Hồ sơ hiện tắt. Bật lại thì lưu `on`.
- Khổ 390, giao diện tối, tiếng Anh: dải dưới đáy hiển thị đúng tiếng Anh, không tràn ngang.
- Cảnh chào: đã chụp giao diện sáng, tối và chế độ giảm chuyển động. Hiệu ứng chiều sâu chạy (lớp trước dịch 7,2 / −5,4px); khi giảm chuyển động thì không có chuyển động nào.
- Không có lỗi console.

Test:
- 3 test Playwright mới: robot đến đúng chỗ và chuyển câu hỏi cho Trợ lý, chỉ một lần mỗi phiên; tắt rồi bật lại được; không xuất hiện khi đang làm bài.
- Toàn bộ test giao diện: 44 passed.
- Toàn bộ bộ test: **1318 passed, 10 skipped**.

### Tệp
- `frontend/js/companion.js` (mới)
- `frontend/js/assistant.js`
- `frontend/js/main.js`
- `frontend/js/pages/profile.js`
- `frontend/css/app.css`
- `frontend/js/lang/en.json` (31 mục mới)
- `tests/test_ui_e2e.py`
- Phiên bản 5.62.0 ở `backend/config.py`, `frontend/index.html`, `frontend/login.html`, `README.md`

### Chưa kiểm chứng
- Chưa thử trình đọc màn hình thật đọc bong bóng.
- Chưa thử trên thiết bị cảm ứng thật.
- Câu trả lời thật từ Gemini cho các câu hỏi mới chưa được chạy trực tiếp; trong test, Trợ lý chạy bằng câu trả lời theo quy tắc.

## Bổ sung 20/11/2026 · Phiên bản 5.63.0: AI xuất hiện ở góc màn hình, không che giữa trang

Ở bản 5.62, robot hiện ngay mép phần trang mà nó nói tới, nên có lúc che giữa trang. Bản này đưa robot về một chỗ cố định và làm lại cách nó xuất hiện. Mã ở `frontend/js/companion.js` và khối CSS 5.63 trong `frontend/css/app.css`.

### 1. Chỗ hiển thị

- **Góc phải dưới, ngay trên nút "Trợ lý":** robot và bong bóng luôn nằm ở góc này, không bao giờ đè lên nội dung giữa trang.
- **Viền sáng cho phần đang nói tới:** thay vì đứng cạnh, robot làm phần trang đó hiện một viền sáng mềm (`.ai-spotlight`). Viền tắt khi robot rời đi.
- **Chip "Về: …":** bong bóng ghi tên phần đang nói tới (ví dụ "Về: Tổng quan tiến độ", "Về: Python"). Bấm vào chip thì trang cuộn tới phần đó và viền sáng lóe lại.
- **Nút lên đầu trang** tạm ẩn khi robot đang hiện, để hai thứ không chồng nhau.
- **Điện thoại** (dưới 720px): bong bóng là một dải ngang phía trên nút Trợ lý, không tràn ngang.
- Bỏ "đuôi" hình thoi trắng của bong bóng, vì không hợp với nền kính mờ.

### 2. Hiệu ứng xuất hiện theo nhịp

1. Robot bật lên kiểu lò xo, kèm một vòng sáng lan ra và năm đốm lấp lánh.
2. Bong bóng kính mờ mở ra từ phía robot (mờ dần thành rõ, phóng từ nhỏ đến lớn).
3. Ba chấm "đang gõ", rồi câu nói hiện ra như đang được gõ.
4. Các nút câu hỏi trượt vào lần lượt.

Khi rời đi, bong bóng thu về phía robot rồi robot chìm xuống. Ở chế độ giảm chuyển động, mọi thứ hiện và tắt ngay, không có chuyển động.

### 3. Thêm ba chỗ trong Kế hoạch

| Trang | Robot nói về | Câu hỏi đưa cho Trợ lý |
| --- | --- | --- |
| Kết quả bài kiểm tra đầu vào | kỹ năng đầu tiên có nhãn còn thiếu | Cách bù kỹ năng này |
| Phân tích khoảng cách | kỹ năng đầu tiên chưa đạt mức JD | Cách bù kỹ năng này · Tư vấn mức sẵn sàng |
| Lộ trình học | bài học tiếp theo | Bài này học gì? |

Tên kỹ năng hay tên bài học được đọc từ chữ đang hiển thị trên trang. Nếu trang không có phần đó (ví dụ mọi kỹ năng đã đạt), robot không đến. Robot vẫn không chấm điểm, không quyết định mức đạt; câu trả lời đến từ Trợ lý.

### Kiểm chứng

- Trên Edge (dữ liệu tạm):
  - robot nằm cách mép phải và mép dưới đúng như thiết kế;
  - thẻ tiến độ có viền sáng, và viền tắt khi đóng;
  - chip "Về:" cuộn đúng tới thẻ;
  - ba chỗ mới trong Kế hoạch đọc đúng tên kỹ năng và tên bài học;
  - khổ 390, giao diện tối, tiếng Anh hiển thị đúng, không tràn ngang;
  - không có lỗi console.
- Kiểm thử giao diện: thêm kiểm tra vị trí góc, viền sáng và việc viền tắt sau khi gửi câu hỏi.
- Toàn bộ bộ test: **1318 passed, 10 skipped** (10 test gọi Gemini thật, bỏ qua theo mặc định).

## Bổ sung 20/11/2026 · Phiên bản 5.64.0: Nút Trợ lý chỉ còn logo AI, robot bay ra từ nút

### 1. Nút "Trợ lý"

- **Lúc bình thường:** nút tròn 56px, bên trong chỉ có khuôn mặt AI (46px, viền trắng). Không còn chữ.
- **Rê chuột hoặc dùng phím Tab tới nút:** chữ "Trợ lý" (tiếng Anh: "Assistant") trượt ra bên trái khuôn mặt.
  - Nút giãn thành viên thuốc rộng 117px (141px với "Assistant"), theo đúng độ rộng chữ (kỹ thuật `grid-template-columns: 0fr → 1fr`, không đặt độ rộng cứng).
  - Chữ mờ dần thành rõ, trễ 70ms so với lúc nút giãn để không bị chen chúc.
  - Khuôn mặt đứng yên tại chỗ (bố cục `row-reverse`), chỉ nghiêng nhẹ và to lên 4%.
  - Nút nhấc lên 2px với bóng sâu hơn; khi bấm thì lún nhẹ.
- **Màn hình cảm ứng:** nút giữ dạng tròn (chữ chỉ hiện khi có chuột thật, `@media (hover: hover)`).
- **Khi nút hiện ra** (lúc tải trang, hoặc khi đóng khung Trợ lý): nút bật vào nhẹ.
- **Trợ năng:** nút vẫn có tên "Mở Trợ lý CareerAdapt AI" cho trình đọc màn hình; focus bằng bàn phím cũng mở chữ.
- **Giảm chuyển động:** không còn hiệu ứng.

### 2. AI xuất hiện "biến ra" từ nút

Mỗi khi AI xuất hiện theo ngữ cảnh (các chỗ ở bản 5.62 và 5.63), robot giờ bay ra từ chính khuôn mặt trong nút:

1. **Phóng ra:** khuôn mặt trong nút nhún xuống rồi bật lên, một vòng sáng xanh ngọc lan ra từ nút.
2. **Bay lên:** robot xuất phát nhỏ đúng tại khuôn mặt trong nút, bay lên và lớn dần tới chỗ đứng ngay trên nút, nảy nhẹ khi đáp. Các đốm lấp lánh bung ra lúc đáp.
3. **Trong lúc robot ở ngoài:** khuôn mặt trong nút mờ đi và nhỏ lại, như thể robot đã rời khỏi nút. Rê chuột vào nút thì khuôn mặt sáng lại.
4. **Thu về:** bong bóng thu lại, robot nhún lên rồi lao xuống, thu nhỏ vào nút. Một vòng sáng co lại quanh nút và khuôn mặt bật sáng trở lại.

Chi tiết kỹ thuật:
- Quãng đường bay được đo lúc robot xuất hiện (`--from-x`, `--from-y`), nên luôn đúng ở mọi khổ màn hình, kể cả điện thoại.
- Đổi trang, gửi câu hỏi hoặc tắt gợi ý thì robot biến mất ngay và nút trở lại bình thường.
- Bấm nút Trợ lý trong lúc robot đang hiện thì robot rời đi và khung Trợ lý mở ra.
- Ở chế độ giảm chuyển động, không có đường bay; chỉ có khuôn mặt trong nút mờ đi rồi sáng lại.

### 3. Lỗi tìm ra và đã sửa

Vòng sáng quanh robot sau khi lan ra (phóng to 2,3 lần) vẫn nằm đó dù đã trong suốt. Vòng này phủ lên nút Trợ lý, nên **trong suốt 16 giây robot hiện, bấm vào giữa nút không có tác dụng**. Lỗi có từ bản 5.63, khi robot được dời xuống ngay trên nút.

Đã sửa bằng cách cho cả phần robot không nhận sự kiện chuột (`pointer-events: none`). Robot chỉ để trang trí; bong bóng và các nút vẫn bấm được bình thường.

### 4. Các vị trí được dời theo nút mới

Nút cao 56px (trước là 42px), nên mọi thứ nằm phía trên nút được dời lên cho khỏi chồng nhau:
- bong bóng thông báo: từ 76px lên 88px tính từ đáy;
- nút lên đầu trang: từ 84px lên 88px, căn giữa thẳng với nút;
- robot: từ 74px lên 88px, đứng ngay trên mép nút.

### Kiểm chứng

- **Trên Edge (dữ liệu tạm):**
  - **Nút:** nút tròn 56×56 ở cả giao diện sáng và tối; rê chuột thì rộng 117px với "Trợ lý" và 141px với "Assistant", rời chuột thì về 56px; focus bằng bàn phím cũng mở chữ.
  - **Hiệu ứng:** đã chụp từng khung hình của đường bay ra và bay về bằng cách dừng và tua animation. Robot xuất phát và kết thúc đúng tâm khuôn mặt trong nút (lệch 3px ngang, 62px dọc so với chỗ đứng).
  - **Khổ 390:** nút tròn, robot bay ra đúng, không tràn ngang.
  - **Giảm chuyển động:** không có animation nào của nút; đóng robot thì nút về ngay.
  - **Bấm nút khi robot đang hiện:** nhận ngay (82ms). Trước khi sửa, Playwright phải chờ 15 giây.
  - **Console:** không có lỗi.
- **Hai kiểm thử giao diện mới:**
  - `test_the_assistant_button_shows_only_the_face_until_pointed_at`;
  - `test_the_robot_comes_out_of_the_assistant_button_and_leaves_it_clickable`. Kiểm thử này đã được chứng minh là bắt được lỗi cũ: khi trả lại CSS cũ, nó thất bại vì hết 3 giây chờ bấm.
- **Toàn bộ bộ test:** **1320 passed, 10 skipped (10 test gọi Gemini thật, bỏ qua theo mặc định)**.
