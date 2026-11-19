# Báo cáo kiểm định CareerAdapt AI

| | |
|---|---|
| Ngày kiểm định | 12/11/2026 |
| Phiên bản | 5.17.0 (`backend/config.py`) |
| Phạm vi | Toàn bộ backend, frontend, dữ liệu, test, tài liệu |
| Nguyên tắc | Chỉ đọc và kiểm thử. Không sửa mã, giao diện, cấu trúc CSDL hay dữ liệu thật. Mọi thao tác ghi chạy trên bản sao CSDL trong thư mục tạm, đã xóa sau khi xong |

Báo cáo chi tiết gồm 5 phần:

- [A. Khảo sát dự án và kiến trúc](docs/audit_2026-11-12/01_khao_sat_kien_truc.md): công nghệ, sơ đồ, luồng dữ liệu, module, phần nào là AI thật.
- [B. Kiểm thử chức năng và kịch bản](docs/audit_2026-11-12/02_kiem_thu_chuc_nang.md): ma trận 50 chức năng, 7 kịch bản người dùng.
- [C. Chất lượng hệ thống](docs/audit_2026-11-12/03_chat_luong_he_thong.md): mã nguồn, CSDL, AI, test, bảo mật, UI/UX, hiệu năng.
- [D. Danh sách vấn đề chi tiết](docs/audit_2026-11-12/04_danh_sach_van_de.md): mỗi vấn đề đủ 12 mục.
- [E. Điều chỉnh, ý tưởng mới, lộ trình](docs/audit_2026-11-12/05_y_tuong_va_lo_trinh.md).

---

## Phần 1. Đánh giá tổng quan

**Mức độ hoàn thiện.** Đây là một sản phẩm chạy được trọn vòng cho nghề Data Analyst:

- đăng ký → khai kỹ năng → chọn JD → bài kiểm tra có chạy code thật → khoảng cách kỹ năng → lộ trình theo tuần → học có đồng hồ → kiểm tra hoàn thành → ôn tập định kỳ → đánh giá tổng hợp → xếp hạng và lương tham khảo;
- song ngữ, có quản trị nội dung;
- 898/898 test đạt.

Hai nghề còn lại (Backend, QA) chỉ là giao diện mô phỏng.

**Điểm mạnh nổi bật**

1. **Chấm bằng chạy thật.**
   - SQL chạy trong tiến trình riêng với authorizer chỉ cho đọc; Python chạy với giới hạn CPU, bộ nhớ, tệp và mạng.
   - Đáp án tính từ dữ liệu bằng truy vấn tin cậy, ngân hàng đề không chứa sẵn con số đáp án.
2. **Tính khách quan được bảo vệ.**
   - AI không được cộng điểm. Nhận xét của AI phải trích đúng bài làm; lệch nhiều so với máy thì bài đi duyệt.
   - Mức tự khai không thành bằng chứng; thời gian học không thành điểm.
3. **Dữ liệu an toàn.**
   - Reset là lưu trữ chứ không xóa; mỗi migration có bản sao lưu.
   - Không thấy truy cập chéo tài khoản; CSRF bao phủ 140/140 API ghi.
4. **Minh bạch.**
   - Mỗi mức kỹ năng truy được về test case và bài làm.
   - Lộ trình ghi lý do cho hoạt động không xếp được; trang "Kết quả dựa trên gì" liệt kê nguồn.

**Điểm yếu nghiêm trọng**

1. **Mức tự khai quyết định mức tối đa chứng minh được** (A-01, đã tái hiện): làm đúng 100% nhưng khai thấp thì vẫn bị ghi thiếu mức.
2. **Bài viết chấm theo từ khóa** (A-02, đã tái hiện): câu Thống kê khó đạt 100/100, mức 3 với một dòng gồm 2 con số và 4 từ khóa.
3. **Bằng chứng sau lộ trình yếu hơn bài đầu vào** (A-03): trắc nghiệm làm lại ngay có thể xác nhận tới mức 3.
4. **Ngân hàng đề rất nhỏ** (A-04): 18 câu, 2 bộ dữ liệu 10 dòng, đáp án hiện ra sau khi chấm.
5. **Không đổi được mục tiêu mà giữ năng lực** (A-05).

**Khả năng sử dụng thực tế.**

- Tốt cho đồ án, demo và một nhóm nhỏ chạy trên một máy.
- Chưa sẵn sàng triển khai công khai:
  - trạng thái nằm trong bộ nhớ một tiến trình (B-03);
  - chấm bài đồng bộ (B-04);
  - sandbox Python chưa cách ly bằng container (B-05);
  - cần cấu hình Host và proxy (B-06, B-07).

**Mức đáp ứng mục tiêu CareerAdapt AI.**

- Đáp ứng tốt "xác định khoảng cách kỹ năng" và "lộ trình học tập".
- Đáp ứng một phần "đánh giá năng lực thực tế": phần code rất tốt, phần bài viết và cơ chế chọn độ khó còn sai lệch.
- Phần "AI" chủ yếu là giải thích và trợ lý. Các quyết định là luật, và đó là lựa chọn đúng.

**Hạn chế lớn nhất cần giải quyết trước tiên:** độ tin cậy của mức kỹ năng (A-01 đến A-04). Mọi chức năng phía sau (gap, lộ trình, xếp hạng, readiness) đều dựa trên mức này.

## Phần 2. Bảng tổng hợp kiểm định

| Module | Trạng thái | Vấn đề phát hiện | Ưu tiên | Hướng xử lý |
|---|---|---|---|---|
| Tài khoản, phiên, phân quyền | Tốt | Liên kết email theo Host; giới hạn theo IP sau proxy | P2 | URL công khai cấu hình; proxy tin cậy |
| Hồ sơ, xuất/xóa dữ liệu | Tốt | – | – | Giữ |
| Quy trình Career Adapt | Tốt, cứng | Không đổi được mục tiêu mà giữ năng lực | P1 | Luồng "Đổi mục tiêu" |
| Khai báo kỹ năng | Tốt | Mức tự khai ảnh hưởng độ khó đề (xem Đánh giá) | P1 | Xem A-01 |
| JD (thư viện, tự nhập) | Tốt | JD cũ chưa ánh xạ lại kỹ năng mới | P3 | Ánh xạ lại thành phiên bản mới |
| Bài kiểm tra đầu vào | Cần sửa | Trần do tự khai; ngân hàng nhỏ; lộ đáp án | P1 | Độ khó theo JD; sinh dữ liệu; ẩn con số đáp án |
| Chấm bài code (SQL/Python) | Tốt | Đồng bộ trong request; sandbox Windows | P2 | Hàng đợi nền; container |
| Chấm bài viết | Cần sửa | Lách bằng từ khóa | P1 | Giới hạn điểm regex; kiểm tra lập luận; duyệt khi AI tắt |
| Giám sát bài thi | Hạn chế | Do client tự báo | P2 | Tín hiệu phía máy chủ |
| Khoảng cách kỹ năng | Tốt | Đúng công thức; sai theo đầu vào A-01 | – | Giữ công thức |
| Lộ trình | Tốt | Không báo trễ, không dời lịch | P2 | Trạng thái trễ + dời lịch |
| Học tập, kiểm tra hoàn thành | Hạn chế | Trắc nghiệm làm lại ngay xác nhận tới mức 3 | P1 | Thời gian chờ; câu thực hành |
| Ôn tập, nhắc nhở | Tốt | – | – | Giữ |
| Đánh giá tổng hợp | Tốt | – | – | Giữ |
| Xếp hạng, lương | Tốt | Thước đo 5 kỹ năng khung, không theo JD | P3 | Thêm xếp theo readiness |
| Trợ lý AI | Chưa xác minh với AI thật | Test AI thật bị bỏ qua | P2 | Chạy với khóa test; bộ đánh giá AI |
| Quản trị | Tốt | – | – | Giữ |
| CSDL | Ổn | 0 khóa ngoại; JSON; một kết nối | P2 | Script kiểm tra nhất quán; tách bảng dần |
| Kiến trúc lưu trạng thái | Hạn chế | Chỉ 1 tiến trình | P2 | Khóa phiên bản; tách khỏi bộ nhớ |
| Tài liệu, phụ thuộc | Cũ | README V5.3; phụ thuộc không ghim | P3 | Cập nhật; khóa phiên bản |
| Giao diện | Tốt | Trễ hạn, điểm khó hiểu, thẻ lặp | P2/P3 | Xem Phần C6 |

## Phần 3. Danh sách lỗi và điểm cần sửa

Không có P0. Chi tiết đủ 12 mục trong [Phần D](docs/audit_2026-11-12/04_danh_sach_van_de.md).

| Mã | Ưu tiên | Tên | Loại | Độ phức tạp |
|---|---|---|---|---|
| A-01 | P1 | Mức tự khai quyết định mức tối đa chứng minh được | Lỗi đã xác nhận | Trung bình |
| A-02 | P1 | Bài viết chấm theo từ khóa, đạt mức cao không cần lập luận | Lỗi đã xác nhận | Trung bình |
| A-03 | P1 | Trắc nghiệm hoàn thành bài học làm lại ngay, xác nhận tới mức 3 | Rủi ro có bằng chứng | Trung bình |
| A-04 | P1 | Ngân hàng đề quá nhỏ, đáp án lộ sau khi chấm | Hạn chế thiết kế | Cao |
| A-05 | P1 | Đổi mục tiêu buộc reset, mất năng lực đã xác thực | Hạn chế thiết kế | Cao |
| B-01 | P2 | Lộ trình không báo trễ, không dời lịch | Lỗi đã xác nhận | Thấp–TB |
| B-02 | P2 | Giám sát rời màn hình do client tự báo | Hạn chế thiết kế | Trung bình |
| B-03 | P2 | Trạng thái trong bộ nhớ, chỉ 1 tiến trình | Rủi ro có bằng chứng | Cao |
| B-04 | P2 | Chấm bài đồng bộ trong request | Rủi ro có bằng chứng | Trung bình |
| B-05 | P2 | Sandbox Python Windows chưa phải ranh giới bảo mật | Hạn chế thiết kế | Trung bình |
| B-06 | P2 | Liên kết đặt lại mật khẩu theo header Host | Rủi ro có bằng chứng | Thấp |
| B-07 | P2 | Giới hạn tần suất theo IP kết nối trực tiếp | Rủi ro có bằng chứng | Thấp |
| B-08 | P2 | AI thật chưa kiểm chứng; là lớp duy nhất bắt bài lách | Chưa xác minh | Trung bình |
| B-09 | P2 | Không khóa ngoại; dữ liệu nghiệp vụ trong JSON | Hạn chế thiết kế | Trung bình |
| C-01 | P3 | README cũ (V5.3) | Lỗi đã xác nhận | Thấp |
| C-02 | P3 | Phụ thuộc không ghim; cảnh báo httpx | Lỗi đã xác nhận | Thấp |
| C-03 | P3 | Router gắn hai lần, trùng operationId | Lỗi đã xác nhận | Thấp |
| C-04 | P3 | GET có tác dụng phụ | Hạn chế thiết kế | Trung bình |
| C-05 | P3 | Gửi email đồng bộ làm lộ email tồn tại qua thời gian | Rủi ro | Thấp |
| C-06 | P3 | JD cũ hiển thị "chưa có bài đo" cho Thống kê | Quan sát | Thấp |
| C-07 | P3 | Nghề mô phỏng bấm được | Lỗi đã xác nhận | Thấp |
| C-08 | P3 | Ngưỡng đạt rải nhiều nơi | Hạn chế thiết kế | Thấp |
| C-09 | P3 | Xếp hạng không theo JD từng người | Hạn chế thiết kế | Thấp |
| C-10 | P3 | Cache kết quả Python với code ngẫu nhiên | Rủi ro thấp | Thấp |

**Bằng chứng then chốt (tái hiện được):**

```
# Kịch bản 5 – đáp án mẫu đúng 100%, khác nhau ở mức tự khai (bản sao dữ liệu)
declares only SQL=1        | score 100 | verified SQL1 DQ1 VIZ1 PY1 WC1 | target 2 2 2 1 2 | readiness 57.5
declares everything=target | score 100 | verified 2 2 2 1 2
overclaims 3 everywhere    | score 100 | verified 3 3 3 3 3

# Kịch bản 6 – câu trả lời dựng sẵn (exam_grader.verify_exam)
STAT-3 (Khó): "<2 số đúng>. Mẫu nhỏ. t-test. Ngẫu nhiên, nhóm đối chứng."  -> 100/100, mức 3
WC-3 (Khó): chỉ tiêu đề + từ khóa, không số liệu                          -> 60/100, mức 2
DQ-3: rải 4.000 con số                                                    -> 25/100, mức 1 (chặn tốt)
```

## Phần 4. Chức năng cần điều chỉnh

Tóm tắt; lý do đầy đủ ở [Phần E1](docs/audit_2026-11-12/05_y_tuong_va_lo_trinh.md).

- **Giữ nguyên:**
  - tài khoản và bảo mật;
  - máy trạng thái quy trình và bài thi;
  - chấm bằng chạy code;
  - công thức Gap/Readiness;
  - AI chỉ giải thích;
  - reset dạng lưu trữ;
  - lương có nguồn và xếp hạng ẩn danh.
- **Sửa chữa:** chọn độ khó (A-01), chấm bài viết (A-02), trạng thái tuần (B-01), URL email và proxy (B-06, B-07), README và phiên bản thư viện (C-01, C-02).
- **Nâng cấp:** kiểm tra hoàn thành (A-03), ngân hàng đề (A-04), chấm nền (B-04), giám sát thi (B-02), đánh giá AI (B-08).
- **Thiết kế lại:** luồng đổi mục tiêu (A-05), lớp lưu trạng thái người học (B-03).
- **Loại bỏ hoặc thay thế:** đường API trùng ở gốc (C-03), nghề mô phỏng bấm được (C-07), các thẻ điều hướng lặp trên bảng điều khiển.

## Phần 5. Ý tưởng chức năng mới

Xếp theo tổng điểm (giá trị, khả thi, phù hợp, chi phí; mỗi tiêu chí 1–5). Chi tiết ở [Phần E2–E3](docs/audit_2026-11-12/05_y_tuong_va_lo_trinh.md).

| Hạng | Ý tưởng | Tổng | Ghi chú |
|---|---|---|---|
| 1 | So khớp nhiều JD | 20 | Tận dụng `gap_coverage` sẵn có; chi phí thấp |
| 2 | Biểu đồ tiến bộ từng kỹ năng | 18 | API `/me/skill-history` đã có |
| 3 | Lộ trình theo lỗi cụ thể | 17 | Dùng `test_case_results` để chọn bài học đúng chỗ sai |
| 4 | Bảng chất lượng đánh giá | 15 | Chứng minh hệ thống đánh giá đúng; quan trọng với đồ án |
| 5 | Đóng góp câu hỏi có duyệt | 12 | Sau khi có sinh dữ liệu (A-04) |
| 5 | Đánh giá portfolio | 12 | Cho người có kinh nghiệm; cần người duyệt |
| 5 | Phỏng vấn thử | 12 | Chỉ luyện tập, không ghi bằng chứng |

Trùng với chức năng sẵn có nên **không làm mới**, chỉ nâng cấp: Career Readiness Score (đã có Readiness), AI Career Advisor (đã có trợ lý), Adaptive Assessment (là cách sửa A-01), Practical Assessment (đã có sandbox, nâng cấp qua A-04).

## Phần 6. Lộ trình cải thiện

| Giai đoạn | Nội dung | Phụ thuộc | Nghiệm thu chính |
|---|---|---|---|
| 1. Ổn định (≈1 tuần) | B-06, B-07, C-01, C-02, C-03 | – | Test Host giả; cài mới trên máy sạch đạt 898 test |
| 2. Đánh giá đúng (2–3 tuần) | A-01 → A-02 → A-04 → A-03; bảng chất lượng đánh giá bản đầu | GĐ1 | Đúng hết không khai → đạt mức JD; bộ câu lách ≤ mức 1; 50 bộ dữ liệu ngẫu nhiên đáp án mẫu đều 100 |
| 3. Trải nghiệm (1–2 tuần) | A-05, B-01, chỉnh giao diện Phần C6 | A-01 | Đổi JD giữ mức; tuần trễ được báo và dời lịch |
| 4. Chức năng mới (2–3 tuần) | So khớp nhiều JD, lộ trình theo lỗi, biểu đồ tiến bộ | GĐ2, A-05 | Số liệu khớp trang Khoảng cách; hai người sai khác chủ đề nhận lộ trình khác |
| 5. Hồi quy, hoàn thiện (1–2 tuần) | B-04, B-03 bước đầu, B-05 nếu triển khai công khai, B-08 | Tất cả | 0 test thất bại; 10 bài nộp đồng thời đều được chấm; báo cáo tỷ lệ AI phát hiện bài lách |

Chi tiết từng công việc, thứ tự phụ thuộc và tiêu chí nghiệm thu ở [Phần E4](docs/audit_2026-11-12/05_y_tuong_va_lo_trinh.md).

## Phần 7. Đánh giá cuối cùng

| Tiêu chí | Điểm /10 | Lý do và bằng chứng |
|---|---|---|
| Kiến trúc và chất lượng mã | 7,0 | Engine thuần hàm, máy trạng thái chặt, docstring nêu quy tắc. Trừ điểm: trạng thái trong bộ nhớ, router gắn hai lần, GET có tác dụng phụ, vài tệp >600 dòng |
| Tính đúng đắn nghiệp vụ | 6,5 | Thứ tự bước, chống nộp trùng, gap đúng công thức (P, T). Trừ: A-01 (người đúng 100% bị ghi thiếu mức), A-05, B-01 |
| Chất lượng AI | 5,5 | Thiết kế an toàn (không cộng điểm, kiểm tra trích dẫn, công cụ đọc theo phiên). Nhưng AI chỉ giải thích; AI thật chưa được kiểm chứng (10 test bỏ qua); bài lách chỉ bị bắt khi AI bật và lệch ≥2 mức |
| Độ chính xác đánh giá kỹ năng | 5,0 | Phần code mạnh, chống rải số tốt. Yếu: 1 câu cho mỗi kỹ năng, trần do tự khai, từ khóa đạt mức 3 (G), trắc nghiệm làm lại đạt mức 3 |
| CSDL và quản lý dữ liệu | 6,5 | Migration có sao lưu, lưu trữ thay vì xóa, integrity ok, lịch sử đầy đủ. Trừ: 0 khóa ngoại, JSON lớn, một kết nối |
| UI/UX | 7,5 | Nhất quán, sáng/tối, 375 px không tràn, chữ ≥12 px, không lỗi console. Trừ: không báo trễ, điểm 100 mà "đáp ứng 1/5", không đổi mục tiêu được, thẻ lặp |
| Bảo mật | 8,0 | Không phát hiện lỗ hổng khi thăm dò; Argon2, CSRF, CSP, phân quyền. Trừ: rủi ro Host/proxy khi triển khai, sandbox Python trên Windows |
| Hiệu năng | 6,5 | API đọc 7–13 ms. Trừ: chấm đồng bộ, Python tới 20 s/câu, xếp hạng O(n²) |
| Khả năng mở rộng | 5,0 | 1 nghề thật; 18 câu thi; 13 hoạt động; chỉ 1 tiến trình; thêm nghề tốn công |
| Mức hoàn thiện tổng thể | 6,5 | Chạy trọn vòng, test dày (898). Độ tin cậy của mức kỹ năng chưa tương xứng với mức hoàn thiện của các phần còn lại |

## Thống kê kiểm định

| Hạng mục | Số lượng |
|---|---|
| Module đã khảo sát | 15 nhóm module, 95 tệp mã (65 Python, 30 JavaScript) |
| Chức năng đã kiểm tra | 50 (ma trận Phần B2) |
| Test tự động | 908 ca: **898 đạt, 0 thất bại, 10 bỏ qua** (AI thật, không có khóa trong môi trường test) |
| Thăm dò bổ sung | 2 script API trên bản sao (≈45 kiểm tra, 2 tài khoản), 5 câu trả lời dựng sẵn để thử lách bộ chấm, 1 lượt xem giao diện |
| Vấn đề theo mức | P0: 0 · P1: 5 · P2: 9 · P3: 10 (tổng 24) |
| Theo loại | Lỗi đã xác nhận: 7 (A-01, A-02, B-01, C-01, C-02, C-03, C-07) · Rủi ro có bằng chứng: 7 (A-03, B-03, B-04, B-06, B-07, C-05, C-10) · Hạn chế thiết kế: 8 (A-04, A-05, B-02, B-05, B-09, C-04, C-08, C-09) · Chưa xác minh: 1 (B-08) · Quan sát chưa rõ nguyên nhân: 1 (C-06) |
| Đề xuất điều chỉnh | 15 (5 sửa chữa, 5 nâng cấp, 2 thiết kế lại, 3 loại bỏ/thay thế) |
| Ý tưởng chức năng mới | 7 đề xuất + 4 ý tưởng trùng chức năng có sẵn (chuyển thành nâng cấp) |

**Chưa thể xác minh:**

- AI thật (Gemini): tóm tắt JD, nhận xét bài, trợ lý, embedding. Không gửi dữ liệu ra dịch vụ ngoài khi chưa được phép.
- Gửi email: không có SMTP.
- Tải cao và nhiều người đồng thời: không có công cụ, không cài thêm.
- Độ bao phủ mã: chưa cài công cụ đo.
- Trình đọc màn hình và các trình duyệt khác.
- A-03 chưa chạy trọn vòng "làm lại đến khi đạt".
- B-03 (ghi đè khi hai tab) chưa tái hiện.

**Không có thay đổi nào** với mã nguồn, giao diện, cấu trúc CSDL hay dữ liệu thật. Tệp mới duy nhất là báo cáo này và 5 tệp trong `docs/audit_2026-11-12/`.

Nhóm xem xét báo cáo, chọn hạng mục cần làm và cho chỉ thị cho giai đoạn phát triển tiếp theo.

---

## Tình trạng sau khi sửa · Phiên bản 5.18.0 (13/11/2026)

Thực hiện theo lộ trình ở Phần 6, ưu tiên các vấn đề làm sai mức kỹ năng. Sao lưu trước khi sửa: `CareerAdapt_AI_backup_truoc_sua_kiem_dinh_20261113`. Test hồi quy mới: `tests/test_audit_fixes_2026_11.py`.

**Toàn bộ test:** 1029 đạt, 0 thất bại, 10 bỏ qua (AI thật, như trước). Trước khi sửa là 898 đạt.

| Mã | Trạng thái | Đã làm | Bằng chứng |
|---|---|---|---|
| A-01 | Đã sửa | Độ khó theo mức JD yêu cầu (`tier_for_target`), mức tự khai không còn ảnh hưởng | Test: không khai gì, làm đúng hết → đạt đúng mức JD ở mọi kỹ năng |
| A-02 | Đã sửa | Khái niệm chỉ được tính khi câu chứa nó còn ≥3 từ ngoài từ khóa; không có số liệu đúng nào thì tối đa mức 1 | STAT-3 lách: 100 điểm/mức 3 → 30 điểm/mức 1. WC-3 chỉ tiêu đề: 60/mức 2 → 40/mức 1. Mọi đáp án mẫu tiếng Việt và tiếng Anh vẫn 100 |
| A-03 | Đã sửa | Trắc nghiệm hoàn thành bài học xác nhận tối đa mức 2; trượt thì 6 giờ sau mới làm lại; giao diện báo giờ mở lại và nói rõ mức 3 cần bài thực hành | Test: bài mục tiêu mức 3 đạt trắc nghiệm → mức 2, bài học hoàn thành, gap còn 1 |
| A-04 | Sửa một phần | Thêm 2 bộ dữ liệu (C, D) → 4 biến thể mỗi câu, ngân hàng EX-DA-1.3 | Đáp án mẫu đạt 100 trên cả 4 bộ; đáp án của bộ này sai trên bộ khác. Còn thiếu: nhiều dạng câu hơn cho mỗi ô kỹ năng × độ khó (cần người soạn nội dung). Vẫn hiển thị "Đáp án đúng" vì con số khác nhau giữa các bộ dữ liệu |
| A-05 | Đã sửa | Nút "Đổi JD mục tiêu": giữ mức đã xác thực, bài kiểm tra, bài học đã đạt, lịch sử; chọn JD mới rồi lập lại lộ trình | Test API + chạy trọn vòng trên giao diện (bản sao dữ liệu) |
| B-01 | Đã sửa | Tuần quá hạn hiện "Trễ N ngày", cảnh báo đầu trang, nút "Dời lịch từ hôm nay". Sửa kèm một lỗi cũ: nút "Cập nhật lộ trình" không dời ngày khi không có gì khác thay đổi | Test đồng hồ giả; kiểm tra trên giao diện: tuần 1 chuyển từ 2/11 sang 13/11 |
| B-06 | Đã sửa | `CAREERADAPT_PUBLIC_URL` cho liên kết email; production thiếu cấu hình thì không gửi; `CAREERADAPT_ALLOWED_HOSTS` bật kiểm tra Host | Test Host giả |
| B-07 | Đã sửa | `CAREERADAPT_TRUSTED_PROXIES` truyền vào uvicorn `forwarded_allow_ips` | Cấu hình; chưa thử sau proxy thật |
| C-01 | Đã sửa | README cập nhật 5.18.0, quy tắc mới, biến cấu hình mới | – |
| C-02 | Đã sửa một phần | `requirements.lock` ghi đúng phiên bản đang chạy; không đổi thư viện | Cảnh báo `httpx2` vẫn còn (đổi thư viện cần nhóm đồng ý) |
| C-03 | Đã sửa | Đường gốc vẫn chạy (test và đặc tả dùng) nhưng ẩn khỏi tài liệu API; sửa operationId trùng | 164 thao tác, không còn cảnh báo |
| C-05 | Đã sửa | Email đặt lại mật khẩu gửi sau khi trả lời | Test |
| C-07 | Đã sửa | Nghề mô phỏng ghi "Sắp có" | – |
| B-04 | Đã sửa (5.19.0) | Nộp bài chỉ khóa câu trả lời rồi đưa vào hàng đợi chấm nền (`backend/grading_queue.py`, 2 luồng, chỉnh bằng `CAREERADAPT_GRADING_WORKERS`). Bài bị ngắt khi máy chủ dừng được chấm lại ở lần quét nền. Giao diện có màn hình "Đang chấm bài" tự mở kết quả. Áp dụng cho bài kiểm tra đầu vào và bài đánh giá tổng hợp | Máy chủ thật trên bản sao dữ liệu: nộp trả về sau 9 ms, chấm xong ở nền sau 3,7 giây (trước đây yêu cầu nộp phải chờ hết thời gian chấm). `tests/test_background_grading.py`: không chấm hai lần, chấm lại bài bị ngắt, không vượt số luồng. Toàn bộ test 5.19.0: 1036 đạt, 0 lỗi |
| Ý tưởng 2 | Đã làm | So khớp năng lực với mọi JD đã duyệt, trên trang Khoảng cách kỹ năng | Test: số liệu JD đang chọn khớp đúng trang Khoảng cách |

**Còn mở** (cần hạ tầng, dữ liệu hoặc quyết định của nhóm): B-02, B-03, B-05, B-08, B-09, C-04, C-06, C-08, C-09, C-10, phần còn lại của A-04, và các ý tưởng 1, 3, 4, 5, 6, 7.

**Lưu ý về test cũ:** 8 test cũ khẳng định đúng hành vi mà kiểm định xác định là lỗi, nên đã được sửa kỳ vọng. Mỗi chỗ có ghi chú "Audit A-0x" trong mã test:

- độ khó theo mức tự khai và mức chứng minh được khi khai thấp (5 test);
- làm lại kiểm tra hoàn thành ngay sau khi trượt (2 test);
- số bộ dữ liệu bằng 2 (1 test).

Không test nào bị xóa.
