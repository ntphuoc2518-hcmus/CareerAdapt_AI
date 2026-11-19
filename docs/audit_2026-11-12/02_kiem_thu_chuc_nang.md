# Phần B. Kiểm thử chức năng và kịch bản người dùng

Thuộc bộ báo cáo kiểm định ngày 12/11/2026. Tài liệu chính: [AUDIT_REPORT.md](../../AUDIT_REPORT.md).

## B1. Cách kiểm thử

Mọi thao tác ghi dữ liệu chạy trên **bản sao** CSDL (sao bằng SQLite backup API ở chế độ chỉ đọc) trong thư mục tạm, AI ở chế độ `mock`. Các bản sao đã bị xóa sau khi kiểm thử. CSDL thật chỉ được đọc để sao chép.

Ký hiệu nguồn bằng chứng:

- **T**: bộ test tự động của dự án (chạy toàn bộ: 898 đạt, 0 lỗi, 10 bỏ qua).
- **P**: script thăm dò API viết trong lần kiểm định này, chạy trên bản sao (đăng ký thật, cookie thật, CSRF thật, hai tài khoản).
- **G**: thử nghiệm "lách" bộ chấm bằng câu trả lời dựng sẵn, gọi trực tiếp `exam_grader.verify_exam`.
- **U**: mở giao diện trên bản sao dữ liệu.
- **C**: đọc mã nguồn (chưa tái hiện khi chạy).

## B2. Ma trận chức năng

Trạng thái: **Tốt** (đúng nghiệp vụ, có bằng chứng), **Cần sửa** (chạy được nhưng có vấn đề nghiệp vụ), **Hạn chế** (đúng như thiết kế nhưng thiết kế còn yếu), **Chưa xác minh**.

| # | Chức năng | Trạng thái | Bằng chứng và ghi chú |
|---|---|---|---|
| 1 | Đăng ký | Tốt | P: 201; mật khẩu ≥12 ký tự 5 nhóm; giới hạn theo IP. T: `test_auth_sessions.py` |
| 2 | Đăng nhập, khóa sau nhiều lần sai | Tốt | P, T: `test_repeated_wrong_passwords_lock_the_email_for_a_while` |
| 3 | Đăng xuất, phiên hết hạn | Tốt | T; phiên 8 giờ, lưu dạng băm |
| 4 | Đổi mật khẩu, thu hồi phiên khác | Tốt | T |
| 5 | Quên/đặt lại mật khẩu | Tốt (có rủi ro triển khai) | T; liên kết lấy từ header Host (xem B-06) |
| 6 | Sửa hồ sơ | Tốt | P: tên chứa thẻ HTML được lưu nguyên văn; giao diện hiển thị qua escape (T: `test_audit_hardening.py`) |
| 7 | Phân quyền admin | Tốt | P: học viên gọi 3 API quản trị → 403 |
| 8 | Chống truy cập chéo tài khoản | Tốt | P: đọc/xóa hội thoại, JD riêng, xem bài đánh giá tổng hợp của người khác → 404; C: `_owned` cho phiên học |
| 9 | CSRF và kiểm tra Origin | Tốt | P: thiếu header CSRF → 403; Origin lạ → 403; toàn bộ 140 API ghi đều nằm trong vùng được kiểm tra |
| 10 | Xuất và xóa dữ liệu học tập | Tốt | T: `test_v4_persistence.py`, `test_v5_process.py` |
| 11 | Bắt đầu quy trình, nghề mô phỏng | Tốt | P: QA Tester → 409 với lý do rõ |
| 12 | Thứ tự bước bắt buộc | Tốt | P: chọn JD trước khi khai kỹ năng → 409; sửa kỹ năng sau khi xác nhận → 409 |
| 13 | Khai báo kỹ năng, gợi ý từ kinh nghiệm | Tốt | T; gợi ý là luật từ khóa có trích câu |
| 14 | Chọn JD thư viện | Tốt | P |
| 15 | Nhập JD riêng (PDF/DOCX/TXT) | Tốt | T: `test_v4_jd.py` (giới hạn 5 MB, 30 trang, ≥80 ký tự) |
| 16 | Tóm tắt JD bằng AI | Chưa xác minh | Chỉ chạy được ở chế độ luật; AI thật không gọi trong kiểm định |
| 17 | Đổi JD/nghề sau khi đã làm bài | Cần sửa | P: 409, chỉ có đường reset toàn bộ, mất mức đã xác thực (A-05) |
| 18 | Tạo bài kiểm tra | Hạn chế | P: 5 câu, 34 phút; độ khó theo mức tự khai (A-01); ngân hàng 18 câu (A-04) |
| 19 | Không lộ đáp án khi đang làm | Tốt | P: đề công khai không chứa `cases`, `expected_sql`, `wrong_sql` |
| 20 | Kiểm tra đầu vào bài làm | Tốt | P: vượt 20.000 ký tự → 422; câu không thuộc đề → 404; sai kiểu → 422 |
| 21 | Chạy SQL thật | Tốt | T: `test_workspaces.py`, `test_v4_grading.py` (authorizer, giới hạn thời gian) |
| 22 | Chạy Python thật | Tốt (giới hạn trên Windows) | T: giới hạn bộ nhớ và thời gian dừng được bài chạy vô hạn; mã nguồn tự ghi chú không phải ranh giới bảo mật (B-05) |
| 23 | Nộp bài, nộp trùng | Tốt | P: nộp lần 2 → `is_duplicate: true`, không chấm lại |
| 24 | Tự nộp khi hết giờ | Tốt | T; quét nền `finish_expired` |
| 25 | Theo dõi rời màn hình | Hạn chế | C: do trình duyệt tự báo, có thể bỏ qua (B-02) |
| 26 | Chấm câu bỏ trống, câu sai | Tốt | P: 1 câu SQL sai + 4 câu trống → 4,5/100, mức 0 mọi kỹ năng |
| 27 | Chấm bài viết | Cần sửa | G: câu khó Thống kê đạt 100/100 chỉ với số liệu + 4 từ khóa (A-02) |
| 28 | Giải thích kết quả | Tốt | P: từng ý đúng/sai kèm "Đáp án đúng"; câu kết luận theo kỹ năng |
| 29 | Lỗi trọng yếu (critical gate) | Tốt | G: nêu sai xu hướng → bị chặn mức |
| 30 | Khoảng cách kỹ năng | Tốt về công thức | P: coverage 1,0, readiness 0 sau bài kém; T: `test_engine_math.py` |
| 31 | Mức tự khai không thành bằng chứng | Cần sửa | Mức tự khai không được tính là bằng chứng, nhưng lại quyết định mức tối đa có thể chứng minh (A-01) |
| 32 | Lập lộ trình | Tốt | P: 138 ms; T: `test_v4_roadmap.py`; hoạt động không xếp được có lý do |
| 33 | Lộ trình theo ngày thực tế | Cần sửa | U: tuần 1–2 đã qua, 0% nhưng vẫn "Chưa bắt đầu", không báo trễ (B-01) |
| 34 | Đồng hồ học | Tốt | T: `test_learning_roadmap_2.py` (heartbeat, tự dừng sau 5 phút) |
| 35 | Kiểm tra hoàn thành bài học | Hạn chế | C: trắc nghiệm 3–8 câu, làm lại ngay không giới hạn, có thể nâng tới mức 3 (A-03) |
| 36 | Ôn tập định kỳ | Tốt | T; không hạ mức khi trượt ôn tập |
| 37 | Lập lại lộ trình (replan) | Tốt | T |
| 38 | Đánh giá tổng hợp cuối lộ trình | Tốt | T; mở khi mọi bài học đạt, làm lại sau 24 giờ |
| 39 | Luyện tập (13 bài) | Tốt | T: mọi đáp án mẫu đạt; không ghi bằng chứng |
| 40 | Trung tâm kiểm tra kiến thức | Tốt | T: `test_test_center.py` |
| 41 | Nhắc nhở | Tốt | T |
| 42 | Bảng điều khiển, báo cáo tiến độ | Tốt | U: không lỗi console |
| 43 | Báo cáo năng lực in PDF | Tốt | U (trước đây); chỉ in qua trình duyệt |
| 44 | Xếp hạng, so với nhóm | Tốt | T: `test_insights.py`; dữ liệu thật quá ít người nên phần nhóm bị ẩn đúng thiết kế |
| 45 | Lương tham khảo có nguồn | Tốt | T |
| 46 | Trợ lý AI | Chưa xác minh với AI thật | T (mock): công cụ đọc đúng tài khoản phiên, khóa trong lúc thi, không lộ đáp án |
| 47 | Kho kiến thức có duyệt | Tốt | T: `test_ai_knowledge.py` |
| 48 | Quản trị nội dung | Tốt | T: `test_admin_crud.py` |
| 49 | Song ngữ | Tốt | T: `test_i18n.py` |
| 50 | Thời gian phản hồi API đọc | Tốt | P: `/me/gap` 8 ms, `/me/journey` 9 ms, `/insights` 13 ms; nộp bài 1 câu SQL 1,35 s |

## B3. Kịch bản người dùng

### Kịch bản 1: Người dùng mới (P, U)

| Bước | Mong đợi | Thực tế |
|---|---|---|
| Đăng ký, đăng nhập | Thành công, vào bảng điều khiển | Đúng |
| Gọi bài kiểm tra khi chưa có quy trình | Bị từ chối có lý do | 409 "Bài kiểm tra chỉ làm trong Quy trình Career Adapt." |
| Khai SQL=2, Python=1 | Lưu, sang bước JD | Đúng |
| Chọn JD mặc định | Sang bước Bài kiểm tra | Đúng |
| Bắt đầu bài | Đề theo JD | 5 câu: SQL độ Trung bình, 4 kỹ năng còn lại độ Cơ bản, 34 phút |
| Xem Skill Gap, lộ trình | Có lộ trình | Đúng; 138 ms |

**Điểm bất hợp lý:** 3 kỹ năng không khai (Chất lượng dữ liệu, Trực quan hóa, Giao tiếp viết) bị giao câu Cơ bản dù JD yêu cầu mức 2. Ảnh hưởng: cao (A-01).

### Kịch bản 2: Người dùng đang học (T, U, C)

Mở lộ trình → bài học → bấm Bắt đầu học (máy chủ tính giờ) → kiểm tra hoàn thành → mức cập nhật → ôn tập theo lịch → đánh giá tổng hợp. Toàn bộ luồng có test trong `test_learning_roadmap_2.py` (nhóm A–G).

**Điểm bất hợp lý:**

- Lịch tuần không trượt theo ngày thực tế (B-01).
- Bài kiểm tra hoàn thành là trắc nghiệm, cho làm lại ngay, có thể nâng mức tới 3 (A-03).

**Về ý tưởng "kiểm tra lại khi đánh dấu hoàn thành":** hệ thống hiện đã làm đúng tinh thần này. Đánh dấu hoàn thành không đổi mức; chỉ đạt bài kiểm tra mới đổi. Thời gian học không thành điểm. Ba điều kiện còn thiếu:

1. Bài kiểm tra phải mạnh ngang mức nó xác nhận (mức 2–3 cần một câu thực hành, không chỉ trắc nghiệm).
2. Cần thời gian chờ hoặc bộ câu mới giữa các lần làm lại.
3. Không nên bắt người đã chứng minh được mức ở bài đầu vào phải làm lại cho bài học của kỹ năng đó. Hiện đã có cơ chế `carried_over` cho bài đã xác nhận.

Rủi ro nếu làm quá chặt: người học chán vì bị kiểm tra liên tục. Nên giới hạn mỗi bài học một bài ngắn 5–8 phút.

### Kịch bản 3: Người dùng chưa đạt (P)

| Bước | Thực tế |
|---|---|
| Trả lời sai câu SQL, bỏ trống 4 câu, nộp | 4,5/100, không đạt, mức 0 ở cả 5 kỹ năng |
| Nộp lại lần nữa | `is_duplicate: true`, không chấm lại |
| Xem giải thích | Có giải thích từng ý, có "Đáp án đúng" (2 ý), câu kết luận "Khoảng cách lớn nhất là ở chủ đề tổng hợp doanh thu theo nhóm" |
| Đề xuất cải thiện | Lộ trình được tạo cho 5 kỹ năng |
| Đánh giá lại | Qua bài kiểm tra hoàn thành từng bài học và bài tổng hợp cuối lộ trình; muốn làm lại bài đầu vào phải reset |

**Điểm bất hợp lý:** đáp án đúng hiện ra sau khi chấm, trong khi ngân hàng chỉ có 1 câu cho mỗi ô kỹ năng × độ khó và 2 bộ dữ liệu, nên đáp án dễ lan truyền (A-04).

### Kịch bản 4: Người dùng đổi mục tiêu (P)

| Bước | Thực tế |
|---|---|
| Đổi JD sau khi hoàn tất | 409 "Quy trình Career Adapt đã hoàn tất nên không thể đổi JD. Muốn làm lại, hãy reset quy trình" |
| Xem trước reset | Mất khỏi tầm nhìn: kỹ năng đã khai, JD, bài kiểm tra, 5 mức đã xác thực, lộ trình |

**Kết luận:** không có luồng "đổi mục tiêu" giữ lại năng lực đã chứng minh. Người học phải làm lại toàn bộ bài kiểm tra. Ảnh hưởng: cao (A-05).

### Kịch bản 5: Người dùng có kinh nghiệm (P)

Ba tài khoản cùng nộp **đáp án mẫu đúng 100%**:

| Cách khai | Điểm | Mức xác thực (SQL, DQ, VIZ, PY, WC) | Mục tiêu JD |
|---|---|---|---|
| Chỉ khai SQL=1 | 100 | 1, 1, 1, 1, 1 | 2, 2, 2, 1, 2 |
| Khai đúng mức mục tiêu | 100 | 2, 2, 2, 1, 2 | 2, 2, 2, 1, 2 |
| Khai 3 cho tất cả | 100 | 3, 3, 3, 3, 3 | 2, 2, 2, 1, 2 |

Người khiêm tốn làm đúng 100% vẫn bị ghi "thiếu 1 mức" ở 4 kỹ năng, readiness 57,5 và nhận lộ trình học lại những thứ đã biết. Người khai cao và làm được bài khó được mức 3. Khai thấp không có lợi gì, nên hệ thống vô tình khuyến khích khai cao.

### Kịch bản 6 (bổ sung): Người cố tình lách bộ chấm (G)

| Câu | Câu trả lời dựng sẵn | Kết quả |
|---|---|---|
| VIZ-1 (Cơ bản) | "Biểu đồ cột, so sánh vùng và doanh thu." | 100/100, mức 1 |
| STAT-3 (Khó) | Hai số trung bình đúng + "Mẫu nhỏ. t-test. Ngẫu nhiên, nhóm đối chứng." | 100/100, **mức 3** |
| WC-3 (Khó) | Chỉ có 4 tiêu đề và từ khóa, không có số liệu | 60/100, **mức 2** |
| WC-1 | Đoán sai xu hướng | 0, bị chặn lỗi trọng yếu (đúng) |
| DQ-3 | Rải 4.000 con số | 25/100, mức 1 (bộ chấm số chống rải số tốt) |

### Kịch bản 7 (bổ sung): Truy cập chéo tài khoản (P)

Tài khoản B thử đọc hoặc xóa hội thoại AI, JD riêng, bài đánh giá tổng hợp của người khác → đều 404. B gọi API quản trị → 403. Gửi POST thiếu CSRF hoặc khác Origin → 403. Không phát hiện lỗ hổng.

## B4. Những gì chưa kiểm được

| Nội dung | Lý do |
|---|---|
| AI thật (Gemini): tóm tắt JD, nhận xét bài, trợ lý, embedding | Không gửi dữ liệu ra dịch vụ ngoài khi chưa được phép; 10 test AI thật bị bỏ qua vì môi trường test không đọc `.env` |
| Gửi email đặt lại mật khẩu | Không có SMTP |
| Tải cao, nhiều người dùng đồng thời | Không có công cụ load test trong dự án và không cài thêm theo quy định |
| Độ bao phủ mã (coverage %) | Chưa cài `pytest-cov`/`coverage`; không cài thêm theo quy định |
| Trình đọc màn hình, điều hướng bàn phím đầy đủ | Chỉ kiểm tra cấu trúc; chưa kiểm thử bằng công cụ hỗ trợ tiếp cận thật |
| Trình duyệt khác (Firefox, Safari) | Chỉ có trình duyệt tích hợp |
