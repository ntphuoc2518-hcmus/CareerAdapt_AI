# CareerAdapt AI: báo cáo kiểm định toàn hệ thống

Ngày kiểm định: 15/11/2026. Phiên bản trước: 5.31.0. Phiên bản sau khi sửa: **5.32.0**.

Bản sao lưu trước khi sửa (mã nguồn và hai tệp cơ sở dữ liệu): thư mục `CareerAdapt_AI_backup_truoc_kiem_dinh_toan_dien_20261115`, nằm cạnh thư mục dự án.

---

## A. Tổng quan

### Trạng thái ban đầu

- Thư mục dự án không dùng Git, nên không có branch hay thay đổi chưa commit để bảo vệ. Sao lưu được làm bằng cách chép thư mục.
- Bộ test có sẵn: 1093 đạt, 10 bỏ qua (cần Gemini thật), 0 lỗi.
- Kiến trúc: FastAPI + SQLite (2 tệp: dữ liệu học tập và tài khoản), giao diện ES module thuần, AI qua Gemini có chế độ tra cứu khi không có AI.

### Trạng thái sau khi sửa

- Tìm ra **7 lỗi** trong đợt này, sửa cả 7, mỗi lỗi có test tái hiện.
- Bộ test: **1103 đạt, 10 bỏ qua, 0 lỗi** (thêm 10 test mới).
- Không đổi cấu trúc cơ sở dữ liệu, không xóa dữ liệu, không commit.

### Phạm vi đã kiểm tra

| Hạng mục | Số lượng | Cách kiểm |
|---|---:|---|
| Đường dẫn API | 174 | Gọi từng đường dẫn khi chưa đăng nhập, với vai học viên trên trang quản trị, và với dữ liệu rác |
| Trang giao diện | 18 | Mở từng trang ở 1360 px và 375 px, bắt lỗi script, tràn ngang, mã thô |
| Kịch bản chấm bài thi | 5 | Bài bỏ trống, bài sai, code không liên quan, code độc hại, văn bản nhồi từ khóa |
| Kịch bản nghiệp vụ khác | 12 | Tự đánh dấu hoàn thành, sửa hồ sơ, đường dẫn cũ, kiểm tra kiến thức bỏ trống, 5 dạng JD lỗi |
| Cơ sở dữ liệu | 2 tệp | `integrity_check`, dòng mồ côi, trùng email, kiểu băm mật khẩu (chỉ đọc) |

---

## B. Danh sách lỗi đã phát hiện

| # | Lỗi | Mức | Nguyên nhân | Tệp | Cách sửa |
|---|---|---|---|---|---|
| 1 | Code chỉ "chạy được" vẫn có điểm: `SELECT 1` được 4,5/30; `print('xin chao')` được 3/15. Bài sai toàn bộ vẫn được 14,25/100. | HIGH | Các tiêu chí "đúng cú pháp" và "chạy không lỗi" được cộng điểm độc lập với yêu cầu của đề. | `backend/engine/exam_grader.py` | Các tiêu chí nền chỉ được tính khi có ít nhất một tiêu chí về yêu cầu của đề đạt. |
| 2 | Chỉ cần `print(df)` (in cả bảng dữ liệu) là qua tiêu chí "Kết quả in ra đúng", được 10,5/15 và **mức 1 kỹ năng Python** mà không tính gì. | HIGH | Bộ chấm tìm con số đúng ở bất kỳ đâu trong phần in ra; bảng dữ liệu luôn chứa con số đó một cách tình cờ. | `backend/engine/exam_grader.py` | Con số chỉ được tính trên dòng kết quả. Dòng có hơn 4 con số (dòng của bảng dữ liệu) bị loại. |
| 3 | Tiến độ ở Bảng điều khiển, Báo cáo năng lực và câu trả lời của AI tăng khi người học tự đánh dấu "hoàn thành", dù chưa qua bài kiểm tra. Thử: đánh dấu 1 bài, tiến độ từ 0% lên 25%. | HIGH | Ba nơi này dùng `overall_progress_percent` (số tự khai), trong khi trang Lộ trình dùng số đã xác minh. | `backend/api/roadmaps.py`, `backend/ai_service/career_context.py`, `frontend/js/pages/dashboard.js`, `frontend/js/pages/report.js` | Thêm `verified_progress_percent`, `verified_activity_ids`, `lessons_verified`. Ba nơi trên chuyển sang dùng số đã xác minh. |
| 4 | Câu "Em chưa rõ nội dung này nên trả lời đại." được 3,75/15 ở câu viết báo cáo. | MEDIUM | Chữ "nên" khớp mẫu "khuyến nghị hành động". | `backend/engine/exam_grader.py` | Bài viết ngắn (≤ 30 từ) chỉ nói là không biết thì không tiêu chí nào được tính. |
| 5 | `POST /me/final-assessment/start` làm sập máy chủ (lỗi 500, `KeyError: 'can_start'`) khi tài khoản chưa có lộ trình. | MEDIUM | Nhánh "chưa có lộ trình" trả về thiếu khóa `can_start`. | `backend/final_assessment.py` | Nhánh này trả đủ khóa như nhánh chính. Kết quả: 409 kèm lý do. |
| 6 | Nội dung form quá 1 MB và đường dẫn API không tồn tại trả về `{"detail": ...}` tiếng Anh, khác khuôn lỗi chung nên giao diện không hiện được thông báo. | LOW | Bộ xử lý lỗi chỉ đăng ký cho lớp lỗi của FastAPI, không bắt lớp gốc của Starlette. | `backend/main.py` | Đăng ký cho lớp gốc; thêm thông báo tiếng Việt cho trường hợp quá lớn; giữ header của lỗi. |
| 7 | Gửi lại cùng một trạng thái tiến độ nhiều lần tạo nhiều dòng nhật ký giống nhau. | LOW | Không kiểm tra trạng thái có đổi hay không trước khi ghi nhật ký. | `backend/api/roadmaps.py` | Chỉ ghi nhật ký khi trạng thái hoặc phần trăm thay đổi. |

Trước khi sửa lỗi 1, 2 và 4, mức kỹ năng tổng vẫn là 0 trong các kịch bản thử, trừ lỗi 2 (Python lên mức 1). Điểm số thì bị thổi lên ở cả ba.

### Đã kiểm và không thấy lỗi

- **Phân quyền:** 162 đường dẫn ngoài danh sách công khai đều trả 401 hoặc 403 khi chưa đăng nhập. Học viên bị từ chối ở mọi đường dẫn quản trị. Tài khoản khác đọc báo cáo bài kiểm tra nhận 404.
- **Mật khẩu:** cả 5 tài khoản thật dùng Argon2id. Không có email trùng.
- **SQL injection:** mọi câu SQL ghép chuỗi chỉ ghép tên bảng, tên cột lấy từ danh sách cố định trong code; giá trị luôn truyền qua tham số.
- **XSS:** các chỗ chèn chuỗi từ máy chủ vào HTML đều qua `esc()`; ba chỗ nghi ngờ đều dùng `textContent` hoặc hộp thoại đã lọc.
- **Tăng mức không có bằng chứng:** bài bỏ trống được 0 điểm, mức 0. Sửa hồ sơ kèm `assessed_skills` bị bỏ qua. Đường dẫn cũ `/submissions` và `/roadmaps` không đổi mức. Bài kiểm tra kiến thức bỏ trống được 0.
- **JD lỗi:** rỗng, quá ngắn, không giống JD đều bị từ chối 422 kèm lý do.
- **Thực thi code:** code gọi `os.system` hoặc vòng lặp vô hạn bị chặn, chỉ còn tiêu chí "đúng cú pháp" (nay cũng không được điểm).
- **Cơ sở dữ liệu:** `integrity_check` đạt ở cả hai tệp; không có dòng nào trỏ tới tài khoản không tồn tại; không có tài khoản nào có 2 quy trình đang mở.
- **Giao diện:** 18 trang không có lỗi script, không tràn ngang, không lộ mã thô.

---

## C. Danh sách tệp đã chỉnh sửa

| Tệp | Thay đổi | Lý do |
|---|---|---|
| `backend/engine/exam_grader.py` | Thêm `FOUNDATION_CASES`, `_result_lines`, `_is_non_answer` | Lỗi 1, 2, 4 |
| `backend/final_assessment.py` | Nhánh "chưa có lộ trình" trả đủ khóa | Lỗi 5 |
| `backend/api/roadmaps.py` | Thêm `verified_progress()`; `GET /me/roadmap` trả thêm số đã xác minh; không ghi nhật ký trùng | Lỗi 3, 7 |
| `backend/ai_service/career_context.py` | Công cụ tiến độ và tổng hợp hành trình của trợ lý dùng số đã xác minh | Lỗi 3 |
| `backend/main.py` | Bộ xử lý lỗi bắt lớp gốc của Starlette | Lỗi 6 |
| `frontend/js/pages/dashboard.js` | Thanh tiến độ, danh sách bài còn lại và học liệu gợi ý dùng bài đã xác minh | Lỗi 3 |
| `frontend/js/pages/report.js` | "Tiến độ học tập" dùng số đã xác minh | Lỗi 3 |
| `frontend/js/lang/en.json` | 5 chuỗi tiếng Anh mới | Bản tiếng Anh |
| `backend/config.py`, `frontend/index.html`, `README.md` | Số phiên bản 5.32.0 | Phiên bản |
| `tests/test_audit_2026_11_15.py` (mới) | 10 test hồi quy | Chứng minh đã sửa |

---

## D. Kết quả kiểm thử

Chạy bằng `python -m pytest -q` sau khi sửa xong. BLOCKED là test cần khóa Gemini thật nên bị bỏ qua.

| Nhóm test | Tổng số | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|---:|
| Tài khoản, phân quyền, bảo mật | 81 | 81 | 0 | 0 |
| Bài thi, chấm điểm, môi trường thực hành | 509 | 509 | 0 | 0 |
| Quy trình, JD, hồ sơ, quản trị | 135 | 135 | 0 | 0 |
| Lộ trình, bài học, nhắc nhở, nhật ký | 182 | 182 | 0 | 0 |
| Trợ lý AI (dùng AI giả lập) | 158 | 158 | 0 | 0 |
| Trợ lý AI với Gemini thật | 10 | 0 | 0 | 10 |
| Song ngữ Việt, Anh | 38 | 38 | 0 | 0 |
| **Tổng** | **1113** | **1103** | **0** | **10** |

Kiểm tra ngoài bộ test tự động:

- **Trình duyệt:** 18 trang ở hai kích thước màn hình trên bản sao dữ liệu; sau khi sửa, mở lại Bảng điều khiển và Báo cáo năng lực, số tiến độ khớp với trang Lộ trình (0%, 0/9 bài).
- **Không có** test giao diện tự động hay test end-to-end trong dự án; phần giao diện được kiểm bằng tay qua trình duyệt.

---

## E. Đánh giá chất lượng

| Mảng | Đánh giá |
|---|---|
| **Backend** | Tốt. Phân quyền kín ở mọi đường dẫn, khuôn lỗi thống nhất sau đợt này. Điểm yếu: dữ liệu lộ trình giữ trong bộ nhớ của một tiến trình, nên chưa chạy được nhiều tiến trình song song. |
| **Frontend** | Tốt. Không lỗi script ở 18 trang, không tràn ngang trên điện thoại. Chưa có test tự động cho giao diện. |
| **Database** | Khá. Toàn vẹn, không dòng mồ côi, 73 chỉ mục. Tệp dữ liệu học tập không khai báo khóa ngoại; tính nhất quán do code bảo đảm. |
| **AI** | Khá. Điểm và mức không do AI quyết định; câu trả lời có nguồn và bị loại nếu chứa số không khớp. Chưa kiểm lại với Gemini thật trong đợt này. |
| **Chấm điểm** | Tốt hơn trước. Ba chỗ dễ dãi đã siết. Giới hạn còn lại: mỗi kỹ năng chỉ có 1 câu cho mỗi độ khó, nên một kỹ năng được kết luận từ một câu hỏi. |
| **UI/UX** | Tốt. Nhất quán màu, cỡ chữ, có trạng thái trống, lỗi, đang tải, có giao diện tối và song ngữ. |
| **Bảo mật** | Tốt. Argon2id, CSRF, CSP chặt, cookie phiên, không lộ khóa API trong mã nguồn (khóa nằm trong `.env`). |
| **Hiệu suất** | Đủ cho quy mô đồ án. Chưa đo tải; `GET /me/reminders` và trang Lộ trình chạy lại phép quét mỗi lần gọi. |
| **Trải nghiệm** | Tốt. Luồng theo bước, việc cần làm tiếp luôn có nút dẫn tới. |

---

## F. Những vấn đề chưa giải quyết

| Vấn đề | Vì sao chưa làm | Hướng giải quyết |
|---|---|---|
| Mỗi kỹ năng chỉ có 1 câu thi cho mỗi độ khó | Cần người có chuyên môn soạn và kiểm đáp án; không tự sinh bằng AI vì không kiểm chứng được | Soạn thêm 2 đến 3 câu cho mỗi ô kỹ năng × độ khó, kết luận mức từ nhiều câu |
| Không có vai "người đóng góp câu hỏi" | Chức năng này chưa tồn tại; chỉ quản trị viên thêm, sửa câu hỏi. Không dựng bản giả | Thêm vai contributor, trạng thái DRAFT → IN_REVIEW → APPROVED, và kiểm trùng câu hỏi |
| Dữ liệu lộ trình giữ trong bộ nhớ một tiến trình | Đổi sang lưu hoàn toàn trong SQLite là thay đổi kiến trúc lớn | Chuyển `store.roadmaps` và `store.profiles` sang bảng, rồi mới chạy nhiều worker |
| Code Python chạy trong tiến trình con có giới hạn, chưa phải container | Cần Docker hoặc dịch vụ ngoài | Chạy sandbox trong container không mạng, giới hạn CPU và bộ nhớ |
| Tệp dữ liệu học tập không có khóa ngoại | Thêm khóa ngoại cần dựng lại bảng trên dữ liệu thật | Migration có sao lưu, thêm khóa ngoại cho các bảng theo `user_id`, `run_id` |
| Chưa kiểm với Gemini thật, micro thật, gửi email thật | Môi trường kiểm thử không có khóa, micro và SMTP | Chạy `tests/test_ai_live.py` với khóa thật; thử giọng nói trên Chrome; cấu hình SMTP |
| Chưa có test giao diện tự động | Dự án chưa có công cụ (Playwright…); thêm thư viện mới cần nhóm đồng ý | Thêm Playwright cho 5 luồng chính |
| Mẫu "khuyến nghị" trong câu viết báo cáo vẫn khớp chữ "nên" theo nghĩa "vì vậy" ở bài dài | Sửa mẫu từ khóa dễ làm trượt bài đúng; cần bộ bài mẫu để đối chiếu | Chấm phần lập luận bằng rubric có người duyệt hoặc AI có kiểm chứng |

---

## G. Những nâng cấp đã triển khai

**Trong đợt kiểm định này (5.32.0)**

- Bộ chấm bài thi không còn cho điểm code không liên quan, kết quả in tình cờ và câu trả lời "không biết".
- Một con số tiến độ duy nhất, dựa trên bài kiểm tra đã đạt, ở Bảng điều khiển, Báo cáo, trang Lộ trình và trợ lý AI.
- Trợ lý AI phân biệt rõ "bài học đã xác minh" với "tự đánh dấu hoàn thành".
- Khuôn lỗi thống nhất cho mọi lỗi của API.
- Hai test quét toàn bộ đường dẫn: đường dẫn mới thêm sau này nếu quên kiểm tra đăng nhập hoặc quyền quản trị thì test sẽ báo.

**Trong cùng phiên làm việc, ngay trước đợt này (5.27 đến 5.31)**

- Trợ lý AI: giao diện mới, nhập bằng giọng nói, đính kèm ảnh, trình bày câu trả lời có tiêu đề và danh sách.
- Nhắc nhở: sửa 6 lỗi, trang hộp việc mới, danh sách nhanh ở chuông.
- Mức kỹ năng và nhật ký hoạt động: sửa 7 lỗi hiển thị, lọc và phân trang.

Chi tiết từng bản nằm trong `UPGRADE_REPORT.md`.

---

## H. Những ý tưởng nâng cấp tiếp theo

Xếp theo giá trị mang lại so với công sức.

1. **Thêm câu hỏi thi cho mỗi kỹ năng × độ khó.** Tăng độ tin cậy của mức kỹ năng nhiều nhất; chỉ cần nội dung, không cần đổi kiến trúc.
2. **Test giao diện tự động cho 5 luồng chính** (đăng ký, làm bài thi, xem khoảng cách, học một bài, làm bài tổng hợp). Chặn lỗi hồi quy ở giao diện, hiện phải kiểm bằng tay.
3. **Lưu lộ trình và hồ sơ hoàn toàn trong cơ sở dữ liệu.** Điều kiện để chạy nhiều tiến trình và triển khai thật.
4. **Quy trình đóng góp và duyệt câu hỏi.** Mở rộng ngân hàng đề mà vẫn kiểm soát chất lượng.
5. **Sandbox chạy code trong container.** Cần trước khi mở cho người dùng ngoài nhóm.
6. **Chấm phần lập luận của bài viết bằng rubric có kiểm chứng.** Thay cho khớp từ khóa.
7. **Nhắc qua email hoặc thông báo đẩy.** Hiện nhắc chỉ hiện trong ứng dụng, nên người học phải tự quay lại.
8. **Hồ sơ năng lực chia sẻ được** (liên kết công khai có kiểm chứng). Tạo khác biệt so với nền tảng học thông thường: bằng chứng năng lực thay cho chứng chỉ hoàn thành khóa học.

---

## I. Kết luận

CareerAdapt AI ở mức **sẵn sàng để trình diễn và cho một nhóm nhỏ dùng thử**, chưa sẵn sàng để mở công khai.

- **Điểm mạnh:** mức kỹ năng chỉ đổi khi có bài làm được chấm bằng test case; phân quyền kín ở cả 174 đường dẫn; 1103 test tự động đạt; giao diện ổn định trên máy tính và điện thoại.
- **Rủi ro còn lại cho việc dùng thật:** mỗi kỹ năng được kết luận từ một câu hỏi; hệ thống chỉ chạy được một tiến trình; sandbox chưa cách ly bằng container; đường AI thật, email và micro chưa được kiểm trong đợt này.
- Ba lỗi mức HIGH tìm thấy đều thuộc loại "đánh giá dễ dãi" hoặc "coi tự khai là bằng chứng", đúng vào điểm cốt lõi của sản phẩm. Cả ba đã được sửa và có test giữ.
