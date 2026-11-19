# Phần C. Kiểm định chuyên sâu chất lượng hệ thống

Thuộc bộ báo cáo kiểm định ngày 12/11/2026. Tài liệu chính: [AUDIT_REPORT.md](../../AUDIT_REPORT.md).

## C1. Kiến trúc và chất lượng mã nguồn

**Điểm tốt**

- **Tách lớp rõ.** Các phần tính toán là hàm thuần, không gọi CSDL: `engine/gap_coverage.py`, `engine/roadmap_planner.py`, `engine/dag_scheduler.py`, `engine/exam_grader.py`. Nhờ vậy dễ test và kết quả lặp lại được.
- **Máy trạng thái chặt.** Các bước quy trình và trạng thái bài thi đổi bằng `UPDATE ... WHERE step = ?` hoặc `WHERE status = ?` (`career_process.advance`, `exam_service.submit/_grade`). Bấm hai lần, mở hai tab hay hết giờ đều không gây chấm hai lần.
- **Docstring nêu quy tắc nghiệp vụ.** Comment giải thích *vì sao*, ví dụ `verified_level`, `_same_result`, `_execute`.
- **Lỗi được chuẩn hóa** thành `{"error": {code, message, details}}` (`main.py`).

**Điểm yếu**

| Vấn đề | Bằng chứng | Hệ quả |
|---|---|---|
| Trạng thái người học nằm trong dict bộ nhớ của tiến trình (`store.profiles`, `store.roadmaps`) rồi ghi xuống một dòng JSON (`learner_state`) | `store.py:257` `persist_user_runtime` | Chỉ chạy được 1 tiến trình; không thể chạy nhiều worker hay nhiều máy |
| Một kết nối SQLite dùng chung, khóa bằng `RLock` | `database.py:272-274` | Mọi truy vấn xếp hàng nối tiếp; dict hồ sơ bị sửa từ nhiều luồng mà không có khóa (rủi ro, chưa tái hiện) |
| Router gắn hai lần (`/api/v1/...` và gốc) | `main.py:138-155`; OpenAPI cảnh báo trùng `operationId` | Gấp đôi bề mặt API cần bảo vệ và kiểm thử |
| GET có tác dụng phụ | `exam_service.current_attempt` chấm bài khi đọc; `/me/gap` gọi `reconfirm_levels` rồi có thể lập lại lộ trình | Khó dự đoán, khó cache, khó gỡ lỗi |
| Tệp lớn | `admin_crud.py` 609 dòng, `deterministic_grader.py` 617, `app.css` 1.394 | Khó review; nên tách theo miền |
| Nhiều nơi tự định nghĩa ngưỡng đạt | `PASS_THRESHOLD` 70 (bài thi, mini-test), `LESSON_PASS_THRESHOLD` 80, final 70 | Dễ lệch khi chỉnh; nên gom vào một cấu hình chính sách đánh giá |
| Logging hạn chế | Chủ yếu `history_events` và trace AI; ít log lỗi máy chủ có cấu trúc | Khó điều tra sự cố khi triển khai thật |

## C2. Cơ sở dữ liệu

- 43 bảng, `PRAGMA integrity_check` = ok (trên bản sao), **0 khóa ngoại khai báo**. Tài khoản ở CSDL riêng nên không thể ràng buộc chéo.
- **Migration an toàn:** mỗi lần đổi cấu trúc đều sao lưu trước (`*.pre-v2.bak`, `*.pre-ai1.bak`, `*.pre-roadmap1.bak`) và tăng số phiên bản schema.
- **Reset là lưu trữ, không xóa:** `archived_by_run` trên các bảng, ảnh chụp hồ sơ trong `career_runs.payload`. "Xóa toàn bộ dữ liệu học tập" là hành động riêng, có xác nhận.
- **Mô hình lai:** hồ sơ, lộ trình, lịch sử nằm trong JSON (`learner_state.payload`, `career_runs.payload`, `exam_attempts.payload`). Truy vấn thống kê như xếp hạng phải đọc JSON trong Python (`insights._population`), không lọc được bằng SQL.
- **Lịch sử đánh giá đầy đủ:** `final_assessments`, `test_case_results`, `rubric_scores`, `skill_evidence`, `ai_feedback_traces`. Truy vết được mức từ bằng chứng nào.
- **Rủi ro mất dữ liệu khi nhiều người thao tác:** thấp ở quy mô hiện tại vì có khóa và giao dịch. Cao nếu chạy nhiều tiến trình (C1).

## C3. AI và chất lượng đánh giá thông minh

| Câu hỏi | Trả lời có bằng chứng |
|---|---|
| 1. Phần nào dùng AI thật? | Tóm tắt JD, nhận xét bài thi, trợ lý hội thoại và tác vụ, embedding kho kiến thức ([Phần A6](01_khao_sat_kien_truc.md)) |
| 2. Phần nào là luật? | Phân tích JD, gợi ý mức, chấm điểm, khoảng cách, lộ trình, xếp hạng |
| 3. AI có đủ ngữ cảnh? | Trợ lý gọi công cụ đọc dữ liệu thật của chính phiên đăng nhập (`tool_registry.py`). Nhận xét bài thi nhận đề, rubric, điểm máy và câu trả lời đã ẩn danh |
| 4. Có bám dữ liệu đầu vào? | Nhận xét phải trích đúng nguyên văn bài làm (`verify_evidence_quote`), sai thì bị loại |
| 5. Nguy cơ bịa? | Có ở trợ lý (câu trả lời tự do), giảm bằng guardrails và kho kiến thức có duyệt. Chưa đo được với AI thật |
| 6. Ổn định giữa các lần? | Điểm và mức hoàn toàn tất định. Nhận xét AI không ổn định nhưng không ảnh hưởng điểm |
| 7. Có kiểm tra đầu ra AI? | Có: kiểm tra schema, kiểm tra trích dẫn, AI không được đề xuất mức cao hơn máy, lệch ≥2 mức thì chuyển duyệt |
| 8. Giải thích cụ thể? | Có, do máy viết từ test case ("Đúng/Sai: …, Đáp án đúng: …") cùng câu kết luận theo kỹ năng; AI bổ sung nếu bật |
| 9. Cá nhân hóa? | Hiện chỉ cá nhân hóa theo mức và JD. Có thể thêm: chọn bài học theo lỗi cụ thể (test case trượt), nhịp học thực tế, ôn tập theo đường quên (xem [Phần E](05_y_tuong_va_lo_trinh.md)) |
| 10. Đo chất lượng đánh giá khách quan? | Có sẵn mầm: `test_v4_reference_set.py` đo sai số tuyệt đối trung bình so với bộ bài mẫu đã gán mức, và `item-analysis` cho câu trắc nghiệm. Thiếu: bộ bài mẫu cho ngân hàng 5.x, chấm chéo bởi người (inter-rater), độ tin cậy giữa hai lần làm, phân tích độ khó và độ phân biệt cho bài tự luận |

**Nhận định chính:** tên "AI" phần lớn nằm ở lớp giải thích. Đánh giá năng lực thực chất là chạy code và luật đối chiếu văn bản. Luật số liệu khá chặt (rải 4.000 con số chỉ được 25/100). Luật văn bản dựa trên từ khóa thì dễ lách (STAT-3 100/100 với 4 từ khóa). Khi AI tắt, không có lớp nào phát hiện điều này. Khi AI bật, chỉ khi AI cho thấp hơn máy ≥2 mức thì bài mới bị đưa đi duyệt.

## C4. Kiểm thử và độ tin cậy

- **Toàn bộ bộ test:** 908 ca → **898 đạt, 0 thất bại, 10 bỏ qua**, thời gian 147 giây.
  - 10 ca bỏ qua là `tests/test_ai_live.py`, do chủ đích: test không đọc `.env` nên không có khóa.
  - 1 cảnh báo: Starlette khuyến nghị đổi `httpx` sang `httpx2` cho TestClient.
- **Ca chậm nhất:** `test_memory_and_time_limits_stop_the_run` 11,9 giây (cố ý chạy tới giới hạn).
- **Thiếu test:**
  - Không có test khẳng định "trả lời đúng hết thì đạt mức JD yêu cầu bất kể mức tự khai" (A-01). Hiện các test v5 đều khai mức trước rồi mới so.
  - Không có test chống lách bằng từ khóa cho bài viết khó (A-02).
  - Không có test cho tuần trễ hạn trong lộ trình (B-01).
  - Không có test tải hay đồng thời nhiều luồng cho cùng người dùng.
  - Không đo được coverage vì chưa cài công cụ.
- **Hồi quy:** các nhóm test cũ v4 vẫn chạy cùng v5, nên các module cũ còn tương thích.
- **Ghi chú trung thực:** trong lần làm trước có một lần chạy toàn bộ gặp 1 lỗi không tái hiện được. Lần này chạy lại toàn bộ không có lỗi. Có thể còn một test phụ thuộc thời gian (flaky).

## C5. Bảo mật

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Xác thực | Tốt | Argon2; phiên lưu dạng băm; 8 giờ; đổi mật khẩu thu hồi phiên khác |
| Phân quyền và truy cập chéo | Tốt | P: 404 với tài nguyên của người khác, 403 với admin; `_owned`, truy vấn luôn kèm `user_id` của phiên |
| SQL injection | Tốt | Truy vấn tham số hóa. f-string chỉ dùng cho tên bảng/cột lấy từ hằng số (`career_process.py`, `ARCHIVABLE_TABLES`). SQL của người học chạy trong tiến trình riêng với authorizer chỉ cho đọc bảng đề |
| XSS | Tốt | CSP `script-src 'self'`; markdown qua DOMPurify; test escape trong `test_audit_hardening.py` |
| CSRF | Tốt | Origin + double-submit gắn với phiên; 140/140 API ghi được bao phủ |
| Tải tệp | Tốt | Giới hạn dung lượng, số trang, phần mở rộng; không lưu tệp gốc |
| Secret | Tốt | `.env` trong `.gitignore`; test không đọc `.env`; gateway không ghi khóa vào log hay trace |
| Thực thi code người dùng | Hạn chế | Không chạy trong tiến trình API. Trên Windows chỉ có Job Object + audit hook, mã nguồn tự ghi là chưa đủ cho môi trường công khai (B-05) |
| Header Host / proxy | Rủi ro | Liên kết đặt lại mật khẩu dựng từ `request.base_url`; giới hạn tần suất theo `request.client.host` (B-06, B-07) |
| Thông tin lộ qua thời gian phản hồi | Rủi ro thấp | Gửi email đồng bộ trong `/password/forgot` (C-05) |

## C6. Giao diện và trải nghiệm

**Điểm tốt** (đã kiểm ở các lần trước và xem lại trên bản sao lần này):

- Hệ màu navy/xanh thống nhất, có chế độ tối.
- Chữ tối thiểu 12 px, nút ≥44 px trên màn hình cảm ứng.
- Bố cục 375 px không tràn ngang.
- Trạng thái rỗng, đang tải, lỗi có ở các trang chính.
- Không có lỗi console khi điều hướng.

**Điểm cần sửa, cụ thể theo trang:**

| Trang / thành phần | Vấn đề | Đề xuất |
|---|---|---|
| Kế hoạch → Lộ trình học tập, thẻ tuần | Tuần đã qua ngày kết thúc vẫn ghi "Chưa bắt đầu" (U: tuần 1 kết thúc 8/11, xem ngày 12/11) | Thêm nhãn "Trễ N ngày", thẻ cảnh báo đầu trang và nút "Dời lịch từ hôm nay" |
| Quy trình → bước Báo cáo kỹ năng | Không nói cho người học biết mức tự khai quyết định độ khó và mức tối đa có thể chứng minh | Nếu giữ cơ chế: hiện câu cảnh báo ngay tại ô chọn mức. Tốt hơn: sửa A-01 để khỏi cần cảnh báo |
| Kế hoạch → Khoảng cách kỹ năng | Dòng "Yêu cầu chưa có bài đo: Thống kê, …" vẫn hiện dù hệ thống đã có câu hỏi Thống kê từ 5.14 (U, JD Google) | Cho admin "ánh xạ lại JD" tạo phiên bản JD mới; hoặc giải thích vì sao yêu cầu này chưa được đo |
| Kết quả bài kiểm tra | Điểm 100/100 đi cùng "Đáp ứng 1/5 kỹ năng" (A-01) gây khó hiểu | Sửa A-01; trong lúc chờ, giải thích ngay dưới điểm |
| Đổi mục tiêu | Chỉ có nút Reset, câu chữ nói "làm lại từ đầu" | Thêm luồng "Đổi JD mục tiêu" giữ năng lực (A-05) |
| Bảng điều khiển | Nhiều thẻ điều hướng lặp lại menu bên (Kế hoạch, Kho tài liệu, Luyện tập) | Ưu tiên một "Việc cần làm tiếp theo" duy nhất ở đầu trang; thu gọn các thẻ lặp |
| Nghề mô phỏng (Backend, QA) | Hiện như lựa chọn nhưng bấm vào thì bị từ chối | Ghi rõ "Sắp có", làm mờ, không cho bấm |

## C7. Hiệu năng và khả năng mở rộng

- **API đọc rất nhanh ở quy mô hiện tại:** 7–13 ms (đo tốt nhất trong 3 lần). Lập lộ trình 138 ms. Nộp bài 1 câu SQL 1,35 s.
- **Điểm nghẽn tiềm ẩn:**
  - Chấm bài đồng bộ trong request. Mỗi câu Python có thể tới 20 giây và mỗi lần khởi động tiến trình nạp pandas mất vài giây. Nhiều người nộp cùng lúc sẽ dùng hết thread pool (mặc định 40) và các request khác phải chờ (B-04).
  - Xếp hạng tính trong Python trên toàn bộ người dùng mỗi lần gọi (`insights._population`), độ phức tạp O(n²) ở phần tính hạng. Ổn với vài trăm người, chậm khi lên hàng chục nghìn.
- **Mở rộng nội dung:** chỉ 1 nghề có dữ liệu. Mỗi kỹ năng có 3 câu thi (1 câu mỗi độ khó), 2 bộ dữ liệu, 13 hoạt động học, khoảng 20 câu trắc nghiệm. Thêm nghề mới phải viết đủ skills, mapping, bank, activities, resources. Đã có checklist trong bộ nhớ dự án nhưng chưa có công cụ kiểm tra tự động độ đầy đủ ngoài `validate_bank`.
