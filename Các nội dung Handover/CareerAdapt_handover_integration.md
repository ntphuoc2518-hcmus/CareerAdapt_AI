# CareerAdapt AI --- Tài liệu bàn giao tích hợp cho nhóm

**Mục đích:** Tập hợp những phần việc của TV5 (Security/Data) cần phối
hợp với TV1--TV4 và TV6 khi gộp code. Đây là tài liệu bàn giao, không
thay thế code của thành viên khác.

**Trạng thái tổng quát:** Các test độc lập phần TV5 đã chạy không lỗi
theo xác nhận của người thực hiện. Việc tích hợp toàn nhóm chưa được coi
là hoàn tất cho đến khi các interface và kịch bản dưới đây được kiểm tra
trên code đã merge.

## 1. Vai trò và phần phối hợp

  -----------------------------------------------------------------------
  Thành viên              Vai trò                 Phần cần phối hợp
  ----------------------- ----------------------- -----------------------
  TV1                     UI/UX + nội dung nghề   Duyệt rubric, nội dung
                                                  nghề, mã O\*NET/ESCO

  TV2                     Frontend                Kết nối UI với API;
                                                  hiển thị lỗi và luồng
                                                  xem/xuất/xóa dữ liệu
                                                  nếu thuộc MVP

  TV3                     Backend/FastAPI         Auth, ownership,
                                                  endpoint upload/read,
                                                  data-access,
                                                  export/delete

  TV4                     AI integration/bài      Redact PII, xác minh
                          tập/LLM                 evidence, rubric và
                                                  dataset

  TV5                     Security/Data           Security utilities,
                                                  file storage,
                                                  data-access, lifecycle,
                                                  cleanup, docs

  TV6                     QA                      Chạy kịch bản upload
                                                  sai, nộp trùng, sai
                                                  quyền, xóa và hết hạn
  -----------------------------------------------------------------------

Không viết lại phần của thành viên khác chỉ để khớp module TV5. Trước
hết thống nhất interface, import path và kiểu dữ liệu.

## 2. Module TV5 cần tích hợp

### `src/security_utils.py`

Các hàm hiện có: - `normalize_nfc(text)`: chuẩn hóa Unicode NFC. -
`redact_pii(text)`: che email và số điện thoại theo quy tắc MVP. -
`verify_evidence_quote(submission_text, evidence_quote)`: kiểm tra quote
có xuất hiện trong bài nộp sau chuẩn hóa. -
`verify_ownership(resource_owner_id, authenticated_user_id)`: kiểm tra
ID chủ sở hữu với ID người dùng đã xác thực.

**TV3:** gọi ownership check ở phía server trước khi đọc/trả/sửa/xóa tài
nguyên riêng tư; không để user A truy cập dữ liệu user B; không tin
`user_id` do client tự khai.

**TV4:** gọi `redact_pii` trước khi tạo payload gửi nội dung người học
sang LLM; không gửi nguyên bài nộp có PII chưa xử lý; dùng
`verify_evidence_quote` để từ chối evidence/quote không có trong bài
nộp.

**Lưu ý:** Có hàm tiện ích không đồng nghĩa thành viên khác đã gọi nó
đúng chỗ trong luồng thực tế. MVP không được tuyên bố phát hiện mọi loại
PII.

### `src/file_storage_service.py`

Hiện hỗ trợ `.txt`, `.csv`, `.sql`, giới hạn mặc định 5 MB và tính
SHA-256.

**TV3 cần nối vào endpoint upload/submission:** - Kiểm tra file rỗng,
phần mở rộng, dung lượng, UTF-8 và byte NUL theo yêu cầu project. - Tạo
thư mục lưu nếu chưa tồn tại; tên lưu do server tạo, không dùng tên file
người dùng làm đường dẫn. - Gắn file với submission đúng chủ sở hữu;
kiểm tra ownership trước khi đọc file. - Chỉ xóa file đúng đường dẫn do
hệ thống quản lý; không dùng wildcard. - Thống nhất `STORAGE_ROOT`,
`.env`, kiểu dữ liệu đầu vào (ví dụ `UploadFile`/bytes), import path và
phản hồi lỗi.

### `src/data_access.py`

**TV3 cần kiểm tra:** - Endpoint gọi đúng hàm data-access, không tự viết
truy vấn bỏ điều kiện `user_id`. - ID người dùng lấy từ danh tính đã xác
thực ở server. - Kiểu UUID/string và transaction/connection tương thích
sau merge. - Truy cập chéo phải bị chặn; ghi audit `DENIED` theo thiết
kế hiện có.

### `src/user_data_lifecycle.py`

Phục vụ export dữ liệu cá nhân và xóa tài khoản/dữ liệu liên quan.

**TV3/TV2 cần thống nhất:** - Endpoint/UI cho export và delete nếu thuộc
MVP. - Chỉ thao tác dữ liệu của người dùng đã xác thực; không tin
`user_id` từ body. - Export theo schema thực tế: tài khoản/hồ sơ,
submissions, file metadata, assessments/điểm/bằng chứng, roadmap/tiến
độ/nhắc nhở nếu các bảng có tồn tại. - Kiểm tra UUID/datetime/Decimal có
serialize được sang JSON. - Luồng xóa phải báo rõ file nào xóa thất bại;
không bỏ qua lỗi im lặng. - Test phá hủy chỉ trên `careeradapt_demo` và
user giả; không chạy trên DB `careeradapt`.

## 3. Auth/danh tính --- TV3 cần xác nhận

Trong project bundle được rà soát trước đó chưa xác nhận được
`auth_dependencies.py`; kiểm tra nhánh backend mới nhất xem file này tồn
tại hay đã đổi tên.

Yêu cầu: 1. `user_id` cho ownership phải lấy từ token đã được backend
xác thực. 2. Không lấy danh tính tin cậy từ header tùy ý như `X-User-Id`
hoặc request body. 3. Nếu backend đã có dependency auth, dùng dependency
thực tế đó, không tạo module trùng. 4. Ghi rõ tên dependency, kiểu ID
trả về (UUID/string) và cách truyền ID vào service/data-access. 5. Test
thiếu token, token sai và user A truy cập tài nguyên user B.

**Trạng thái:** Chờ TV3 xác nhận interface auth và điểm gọi dịch vụ.

## 4. TV1/TV4 --- rubric, nội dung nghề và LLM

**TV1 cần xác nhận:** rubric/tiêu chí chấm bài Data Analyst; nội dung
nghề; mã O\*NET/ESCO được chọn; phân biệt nội dung demo với nội dung đã
duyệt.

**TV4 cần đảm bảo:** dùng rubric và mã nghề đã được TV1 xác nhận; không
tự coi mã chưa duyệt là chính thức; redact PII trước khi gọi LLM; chỉ
chấp nhận evidence khi `verify_evidence_quote` hợp lệ; thống nhất schema
request/response giữa backend và AI.

**Trạng thái:** Chờ TV1 duyệt và TV4 xác nhận tích hợp.

## 5. Kịch bản bàn giao cho TV6 (QA)

Chạy trên môi trường demo, chỉ dùng user giả `@test.local`.

  -----------------------------------------------------------------------
  ID                      Kịch bản                Kết quả mong đợi
  ----------------------- ----------------------- -----------------------
  QA-01                   Upload file hợp lệ      Lưu thành công,
                          trong giới hạn          metadata/hash theo
                                                  thiết kế

  QA-02                   Upload file rỗng/quá    Bị từ chối, không để
                          dung lượng              file rác

  QA-03                   Upload phần mở rộng     Bị từ chối
                          không hỗ trợ            

  QA-04                   File không phải UTF-8   Bị từ chối theo quy tắc
                          hoặc có byte NUL        

  QA-05                   User A đọc file/bài nộp Không trả dữ liệu;
                          của user B              audit từ chối nếu thiết
                                                  kế yêu cầu

  QA-06                   Nộp lại cùng            Không tạo bản ghi trùng
                          `idempotency_key`       ngoài ý muốn

  QA-07                   Gọi endpoint riêng tư   Bị từ chối
                          không có token hợp lệ   

  QA-08                   User A export dữ liệu   Bị từ chối
                          của user B              

  QA-09                   Xóa tài khoản demo có   DB xử lý đúng; file xóa
                          file                    hoặc báo lỗi rõ

  QA-10                   Cleanup dữ liệu hết hạn Chỉ xử lý dữ liệu đủ
                                                  điều kiện

  QA-11                   Nội dung có email/điện  Payload đã redact trước
                          thoại gửi sang LLM      khi gửi

  QA-12                   AI đưa quote không có   Evidence bị từ chối
                          trong bài nộp           

  QA-13                   Kiểm tra dataset        File tồn tại hoặc trạng
                          DA01A/DA02A/DA03A       thái thiếu file được
                                                  báo rõ
  -----------------------------------------------------------------------

TV5 đã chạy độc lập các test `test_security.py`,
`test_security_scenarios.py`, `test_file_storage.py`,
`test_export_user_data.py`, `test_data_access.py`,
`test_delete_account.py`, `test_cleanup_job.py`; người thực hiện xác
nhận không lỗi. TV6 vẫn cần chạy kiểm thử tích hợp trên code đã merge.

## 6. Bước 20 --- dataset DA01A, DA02A, DA03A

Các đường dẫn đã khai báo trong SQL nhưng chưa tìm thấy file dữ liệu
tương ứng khi rà soát:

  Bài     Input                        Reference output
  ------- ---------------------------- --------------------------
  DA01A   `datasets/da01a_input.csv`   `datasets/da01a_ref.csv`
  DA02A   `datasets/da02a_input.csv`   `datasets/da02a_ref.csv`
  DA03A   `datasets/da03a_input.csv`   `datasets/da03a_ref.txt`

Quy tắc DA01A trong `db/migrations/006_seed_data.sql`: - Số dòng qua
bước xử lý: `10 → 9 → 8`. - `valid_completed_rows`: `7`. -
`total_revenue`: `1,170,000`. - Doanh thu vùng: Nam `700,000`; Bắc
`370,000`; Unknown `100,000`. - `mom_pct`: `-14.29`.

**Việc cần làm:** 1. Hỏi TV4/người thiết kế bài tập có đặc tả hoặc
dataset gốc không. 2. Nếu có, thêm đúng file vào `datasets/` và kiểm tra
kết quả tham chiếu. 3. Nếu chưa có, giữ trạng thái "chờ xác nhận"; không
tự tạo dữ liệu rồi coi là dataset chuẩn. 4. Báo TV4 rằng DA02A/DA03A
cũng đang trỏ tới file chưa tìm thấy. 5. Khi dataset được bổ sung, kiểm
thử kết quả thực tế so với reference output.

**Trạng thái:** Chưa hoàn tất; chờ đặc tả/dataset gốc.

## 7. Bước 10 --- thu thập JD thật

Không tạo dữ liệu tuyển dụng giả. CSV cần các cột:

`company_name, job_title, job_level, posting_url, source_site, collected_on, salary_text, jd_summary, extracted_skills`

Giá trị `job_level`: `INTERN`, `FRESHER`, `JUNIOR`, `OTHER`.\
Giá trị `source_site`: `TOPCV`, `ITVIEC`, `LINKEDIN`, `OTHER`.

Giữ URL gốc và ngày thu thập; không đoán lương nếu tin không ghi;
summary/kỹ năng phải dựa trên JD thật; thống nhất UTF-8 và quy ước giá
trị thiếu trước khi commit.

## 8. Tài liệu và cấu hình cần rà soát

Theo kế hoạch, kiểm tra các tài liệu sau khi merge: - ERD Mermaid hiển
thị được trên GitHub. - Data dictionary theo bảng/cột. - Ma trận quyền
truy cập. - Chính sách retention, backup và audit/log. - Threat model,
checklist và báo cáo bảo mật. - Thông báo dữ liệu cho người tham gia
(mốc 90 ngày theo kế hoạch). - Handover checklist, README và
`requirements.txt`.

Nếu backup ≤ 30 ngày chưa được nhóm chốt, ghi "đề xuất, chờ xác nhận",
không trình bày như chính sách đã duyệt.

Rà soát cấu hình: - Không commit `.env`, mật khẩu, token, dữ liệu cá
nhân thật hoặc backup thật. - Kiểm tra `.gitignore`, dependencies và
hướng dẫn chạy. - Test phá hủy chỉ trên database demo riêng.

## 9. Các mục chưa được đánh dấu hoàn tất

-   [ ] TV3 xác nhận auth dependency và lấy `user_id` từ token đã xác
    thực.
-   [ ] TV3 nối file storage/data-access vào endpoint và kiểm tra
    ownership.
-   [ ] TV3/TV2 thống nhất export/delete nếu thuộc MVP.
-   [ ] TV4 gọi redact PII/evidence verification đúng luồng, không gửi
    bài nộp thô sang LLM.
-   [ ] TV1 duyệt rubric, nội dung nghề và mã O\*NET/ESCO.
-   [ ] TV4 xác nhận đặc tả dataset; DA02A/DA03A còn thiếu file.
-   [ ] TV6 chạy QA tích hợp sau merge.
-   [ ] Bổ sung dataset hoặc ghi rõ chờ đặc tả.
-   [ ] Hoàn thành thu thập JD thật.
-   [ ] Rà soát tài liệu, `requirements.txt`, `.gitignore`,
    secret/config.
-   [ ] Chạy lại test sau merge và ghi kết quả thực tế.
-   [ ] Cuối cùng mới commit/push lên nhánh nhóm; không push trực tiếp
    vào `main`.

## 10. Checklist buổi gộp code

-   [ ] TV3 xác nhận interface auth và kiểu ID.
-   [ ] TV3 tích hợp upload/read + ownership + data-access.
-   [ ] TV2/TV3 thống nhất endpoint và giao diện export/delete nếu có.
-   [ ] TV4 tích hợp `redact_pii` và `verify_evidence_quote`.
-   [ ] TV1 xác nhận rubric và mã nghề.
-   [ ] TV4 phản hồi về dataset DA01A/DA02A/DA03A.
-   [ ] TV6 chạy toàn bộ kịch bản QA trên demo.
-   [ ] Rà soát tài liệu, dependency và cấu hình an toàn.
-   [ ] Chạy test lại sau merge.
-   [ ] Chỉ sau khi hoàn tất mới push code lên nhánh nhóm.

**Nguyên tắc báo cáo:** Chỉ ghi "hoàn thành" khi có file/code và kết quả
kiểm tra tương ứng. Việc chờ thành viên khác phải ghi "chờ xác nhận".
