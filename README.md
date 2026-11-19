# CareerAdapt AI

Phiên bản 5.59.2 (19/11/2026). Lịch sử thay đổi và kết quả kiểm định: `CAREERADAPT_AI_FINAL_AUDIT_REPORT.md` (mới nhất), `FINAL_IMPLEMENTATION_AND_UPGRADE_REPORT.md`, `UPGRADE_REPORT.md`, `CAREERADAPT_AI_FULL_SYSTEM_AUDIT_REPORT.md`, `AUDIT_REPORT.md`.

Hệ thống phát triển năng lực Data Analyst bằng đánh giá có bằng chứng, mục tiêu theo JD và lộ trình học cá nhân hóa.
Đồ án môn Tư duy Tính toán, HCMUS. Đặc tả: `CareerAdapt_AI_v1_upgrade.pdf`.

Hệ thống có hai màn hình. Màn hình chính gồm Bảng điều khiển, Quy trình Career Adapt, Kế hoạch Career Adapt, Tài nguyên và Tài khoản. Màn hình phụ là không gian riêng của quy trình: báo cáo kỹ năng → chọn JD → làm bài kiểm tra một lần → xem kết quả → tạo lộ trình → hoàn tất. Sau đó người học theo lộ trình, đặt chu kỳ, làm mini-test ở mục Kế hoạch.

Hệ thống hiện thực cho nghề Data Analyst. Backend Developer và QA Tester chỉ là giao diện mô phỏng, có nhãn rõ và bị máy chủ từ chối khi bắt đầu quy trình.

CareerAdapt AI không phải chứng chỉ nghề và không bảo đảm được nhận thực tập. Kết quả chỉ phản ánh tiêu chí và phạm vi các bài đã đo. Các ngưỡng, trọng số và mức mục tiêu là cấu hình khởi tạo của prototype, chưa phải chuẩn tuyển dụng đã kiểm định.

## Tải về và chạy lần đầu

Cần Python 3.10 trở lên (khuyến nghị 3.12 hoặc 3.13) và Git.

```bash
git clone https://github.com/ntphuoc2518-hcmus/CareerAdapt_AI.git
cd CareerAdapt_AI
```

**Windows:** nhấp đúp `start.bat`. Script tự tạo môi trường `.venv`, cài thư viện, chạy máy chủ và mở trang đăng nhập.

**Windows (thủ công), macOS, Linux:**

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Mở `http://127.0.0.1:8000/login`, bấm **Đăng ký** để tạo tài khoản học viên.

Repository không chứa dữ liệu người dùng: cơ sở dữ liệu SQLite được tạo mới trong `data/` ở lần chạy đầu, từ các tệp dữ liệu khởi tạo (`data/*.json`, `data/*.csv`). Không cần tệp `.env`: khi thiếu, hệ thống chạy với cấu hình mặc định, không có AI (`LLM_PROVIDER=mock`), và vẫn chấm bài, tạo lộ trình đầy đủ. Muốn bật Gemini, sao chép `.env.example` thành `.env` rồi điền `LLM_PROVIDER=gemini` và khóa của bạn vào `LLM_API_KEY`. Không đưa `.env` lên Git.

## Chạy ứng dụng

Trên Windows, nhấp đúp `start.bat`. Script tự chuẩn bị môi trường và thư viện.

Hoặc chạy thủ công:

```bash
pip install -r requirements.txt
```

Muốn cài đúng các phiên bản thư viện mà bộ test 5.46 đã chạy đạt, dùng `pip install -r requirements.lock` thay cho lệnh trên (thêm công cụ test giao diện: `pip install -r requirements-dev.lock`).

```bash
python run.py
```

Mở `http://127.0.0.1:8000/login`. Tài liệu API ở `http://127.0.0.1:8000/docs`.

Đăng ký công khai chỉ tạo tài khoản học viên. Tạo tài khoản quản trị bằng lệnh:

```bash
python -m backend.create_admin
```

Lần chạy đầu, hệ thống tạo `data/careeradapt.sqlite3` và `data/accounts.sqlite3`. Nếu có tệp `data/learner_state_v1.json` từ bản cũ, dữ liệu trong đó được nhập một lần và tệp JSON gốc được giữ nguyên làm bản sao. Các tệp này chứa dữ liệu người dùng nên không được đưa lên Git (xem `.gitignore`).

Khi nâng lên V5.1, lần chạy đầu tự sao lưu thành `data/careeradapt.sqlite3.pre-ai1.bak` rồi thêm các bảng AI, không đụng bảng cũ.

Khi nâng từ V4, lần chạy đầu tự sao lưu database thành `data/careeradapt.sqlite3.pre-v2.bak` rồi mới thêm bảng và cột mới. Migration chỉ thêm, không sửa dữ liệu cũ. Kết quả cũ của học viên được chuyển vào lưu trữ khi họ bắt đầu quy trình mới.

### Cấu hình

Sao chép `.env.example` thành `.env` nếu cần đổi cấu hình.

| Biến | Ý nghĩa |
|---|---|
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` | Dịch vụ AI: `mock`, `gemini`, hoặc `openai` (chỉ cho nhận xét bài chấm). Với `mock`, bài vẫn được chấm đầy đủ, Trợ lý vẫn tra cứu được và giao diện ghi rõ là không có AI. Mặc định của Gemini là `gemini-3.5-flash-lite`. |
| `AI_EMBEDDING_MODEL` | Mô hình vector cho tìm kiếm theo nghĩa. Mặc định `gemini-embedding-2`. Đổi mô hình sẽ tạo lại vector. |
| `LLM_MAX_RETRIES`, `LLM_TIMEOUT_SECONDS`, `AI_REQUEST_DEADLINE_SECONDS` | Số lần thử lại, thời gian chờ mỗi lần và tổng thời gian của một lượt hỏi. |
| `AI_CHAT_PER_MINUTE`, `AI_DAILY_TOKENS_PER_USER`, `AI_DAILY_TOKENS_TOTAL` | Giới hạn tốc độ và token theo ngày. Vượt tốc độ trả về 429; hết token thì Trợ lý trả lời không qua AI. |
| `AI_MAX_TOOL_ROUNDS`, `AI_CONTEXT_MESSAGES` | Số vòng gọi công cụ và số tin nhắn gửi kèm mỗi lượt. Phần cũ hơn được tóm tắt. |
| `PORT`, `HOST` | Cổng và địa chỉ máy chủ khi chạy `run.py` hoặc `start.bat` (mặc định `8000`, `127.0.0.1`). Đổi `PORT` nếu cổng 8000 đã có chương trình khác dùng. |
| `CAREERADAPT_OPEN_BROWSER` | `false` thì không tự mở trình duyệt khi khởi động. |
| `CAREERADAPT_ENABLE_DEMO_TOOLS` | Hiện nút "Giả lập đến hạn". Luôn tắt ở production. |
| `CAREERADAPT_ENABLE_FAULT_INJECTION` | Cho phép mô phỏng AI timeout, JSON sai, bất đồng, trích dẫn giả. Luôn tắt ở production. |
| `CAREERADAPT_AUTO_LINK_CHECK` | Tự kiểm tra lại link học liệu đến hạn (cần Internet). |
| `CAREERADAPT_LEGACY_ASSESSMENT_API` | Mở lại `POST /submissions` cho học viên. Chỉ dùng trong kiểm thử. |
| `CAREERADAPT_ENV=production` | Bật cookie bảo mật, HSTS và tắt Swagger. Chỉ dùng khi chạy qua HTTPS. |
| `CAREERADAPT_PUBLIC_URL` | Địa chỉ công khai dùng trong email đặt lại mật khẩu. Bắt buộc ở production; thiếu thì không gửi liên kết, để header Host giả không quyết định được liên kết. |
| `CAREERADAPT_ALLOWED_HOSTS` | Danh sách tên miền được phép ở production (cách nhau bằng dấu phẩy). Yêu cầu tới Host khác bị từ chối. |
| `CAREERADAPT_GRADING_WORKERS` | Số luồng chấm bài chạy nền (mặc định 2), cũng là số bài được chấm cùng lúc. |
| `CAREERADAPT_SYNC_GRADING` | `true` thì chấm ngay trong yêu cầu nộp bài như bản cũ. Chỉ dùng khi gỡ lỗi. |
| `CAREERADAPT_WORKERS` | Số tiến trình máy chủ khi chạy `run.py` (mặc định 1). Các tiến trình dùng chung một tệp SQLite: mỗi yêu cầu giữ khóa của người học và nạp lại phần tiến trình khác vừa đổi. |
| `CAREERADAPT_USER_LOCK_WAIT`, `CAREERADAPT_USER_LOCK_LEASE` | Thời gian chờ khóa của một người học (mặc định 25 giây, quá thì trả 503 kèm `Retry-After`) và thời hạn khóa nếu tiến trình giữ khóa bị tắt đột ngột (mặc định 120 giây). |
| `CAREERADAPT_SANDBOX` | Nơi chạy code SQL và Python của người học: `process` (mặc định, tiến trình con), `docker` (container, thiếu Docker thì không chạy code) hoặc `auto` (container nếu có, không thì tiến trình con). |
| `CAREERADAPT_SANDBOX_IMAGE`, `CAREERADAPT_DOCKER_BIN` | Tên image sandbox (mặc định `careeradapt-sandbox:1`, dựng bằng `docker build -t careeradapt-sandbox:1 sandbox`) và lệnh Docker. |
| `CAREERADAPT_TRUSTED_PROXIES` | Reverse proxy được phép gửi `X-Forwarded-For`, để giới hạn đăng nhập tính theo IP thật của người dùng. Mặc định `127.0.0.1`. |

Để thử nghiệm mà không chạm vào dữ liệu thật, chạy `python scripts/dev_server_isolated.py`. Lệnh này mở cổng 8765, dùng thư mục dữ liệu tạm và bật công cụ trình diễn.

## Kiểm thử

```bash
python -m pytest tests -q
```

```bash
python scripts/verify_seed.py
```

Test giao diện chạy Microsoft Edge hoặc Google Chrome có sẵn trên máy, ở chế độ không hiện cửa sổ. Cần cài Playwright một lần; thiếu thì các test này được bỏ qua:

```bash
pip install -r requirements-dev.txt
```

| Tệp | Nội dung |
|---|---|
| `tests/test_v4_jd.py` | JD-01 đến JD-04: nhập tệp, thư viện, ánh xạ, xác nhận, phiên bản, quyền riêng tư |
| `tests/test_v4_grading.py` | GR-01 đến GR-07, SEC-01: bài trống, bài sai, AI giả bằng chứng, timeout, nộp trùng, sandbox |
| `tests/test_v4_roadmap.py` | Gap, readiness, chu trình DAG, quỹ giờ, học liệu, RES-01 |
| `tests/test_v4_learning_cycle.py` | RM-01 đến RM-04: chu kỳ, múi giờ, nhắc trùng, hoãn, mini-test |
| `tests/test_v4_persistence.py` | Khởi động lại, nhập dữ liệu cũ, xóa dữ liệu, thời hạn lưu |
| `tests/test_v4_reference_set.py` | 24 bài tham chiếu cho DA01-DA03, tính MAE |
| `tests/test_v5_exam_bank.py` | Mọi câu trên cả hai bộ dữ liệu: đáp án đúng, sai, bỏ trống, lỗi trọng yếu, giới hạn mức |
| `tests/test_ai_gateway.py` | Adapter Gemini, thử lại, timeout, sai cấu trúc, không lộ khóa |
| `tests/test_ai_knowledge.py` | Phiên bản, duyệt, tìm kiếm lai, không có nội dung đề, migration |
| `tests/test_ai_assistant.py` | Công cụ, cách ly tài khoản, nguồn, injection, giới hạn, chặn khi thi, nghiệp vụ AI |
| `tests/test_ai_live.py` | Provider thật. Chỉ chạy với `CAREERADAPT_LIVE_AI=1` và khóa thật; bị bỏ qua nghĩa là chưa kiểm chứng |
| `tests/test_workspaces.py` | Chọn đúng công cụ, chạy SQL và Python thật, chặn thao tác nguy hiểm, chấm theo kết quả chạy |
| `tests/test_v5_process.py` | Thứ tự bước, một quy trình, khóa, timer, rời tab, AI lỗi, reset, cách ly tài khoản, migration |
| `tests/test_learning_roadmap_2.py` | Đồng hồ học, trạng thái bài học, kiểm tra hoàn thành, ôn tập định kỳ, luyện tập, bài đánh giá tổng hợp, lập lại lộ trình |
| `tests/test_background_grading.py` | Chấm nền: nộp trả về ngay, không chấm hai lần, chấm lại bài bị ngắt, giới hạn số luồng |
| `tests/test_multiprocess.py` | Nhiều tiến trình thật trên một tệp SQLite: không khóa thì mất cập nhật, có khóa thì đủ; hai máy chủ thấy thay đổi của nhau |
| `tests/test_container_sandbox.py` | Lệnh `docker run` (không mạng, chỉ đọc, giới hạn bộ nhớ, CPU, tiến trình, không quyền), thiếu Docker thì không chạy code, chạy qua bản thay thế docker; test container thật bị bỏ qua khi máy không có Docker |
| `tests/test_ui_e2e.py` | Trình duyệt thật: đăng ký, đăng nhập, sai mật khẩu, đăng xuất, mọi trang chính trên máy tính và điện thoại, nút giao diện, chuông, Trợ lý, menu điện thoại, bắt đầu quy trình; trang Quản trị nội dung (đủ 11 mục, liên kết từng mục, tìm kiếm, lưu kỹ năng tùy chọn, form hiệu chỉnh đủ kỹ năng, thanh mục trên điện thoại) |
| `tests/test_contributions.py` | Câu hỏi do chuyên gia đóng góp: quyền, kiểm tra tự động (đáp án mẫu, bài sai, cấu trúc, trùng lặp), duyệt bốn mắt, không tự duyệt, câu đã duyệt vào bài thi nhưng không bao giờ ra cho chính tác giả, ngừng dùng, xóa tài khoản; danh sách xác nhận của người duyệt, bản tiếng Anh (thiếu, còn tiếng Việt, mục thừa, chỉ phục vụ khi đã duyệt), migration cột mới |
| `tests/test_audit_fixes_2026_11.py` | Các sửa theo kiểm định 12/11/2026: độ khó theo JD, chống lách từ khóa, giới hạn trắc nghiệm, 4 bộ dữ liệu, đổi mục tiêu, tuần trễ hạn, so khớp JD, liên kết email |
| `tests/test_audit_2026_11_17.py` | Kiểm định 17/11/2026 (5.46): chống nhồi từ khóa (cụm đệm lặp, chép đề, câu liệt kê), mọi đáp án mẫu vẫn 100 trên 4 bộ dữ liệu, hủy đổi mục tiêu, bảng độ tin cậy, chính sách ngưỡng, bài tổng hợp bỏ dở được nộp nền, nhiều tab không ghi đè nhau, tín hiệu dán của máy chủ, lỗi thực tế trên trang bài học |
| `tests/test_proxy_and_hosts.py` | Máy chủ uvicorn thật: Host ngoài danh sách bị từ chối; giới hạn đăng nhập tính theo IP thật sau proxy tin cậy |

Bộ 24 bài tham chiếu do nhóm phát triển viết và gán nhãn. Kết quả cho thấy bộ quy tắc khớp rubric trên các ca đã biết, chưa phải số đo hiệu chỉnh trên người học thật.

## Kiến trúc

```
backend/
  main.py                    Ứng dụng FastAPI, CSRF, phục vụ giao diện
  database.py                SQLite: schema, giao dịch, ràng buộc duy nhất
  store.py                   Dữ liệu runtime ghi xuyên xuống SQLite
  catalog.py                 Thư viện JD và kho học liệu
  targeting.py               Mục tiêu đang dùng, gap kèm giải thích
  learning_cycle_service.py  Chu kỳ, quét đến hạn, chọn câu mini-test
  career_process.py          Máy trạng thái quy trình, khóa bước, reset có lưu trữ
  exam_service.py            Bài thi một lần: đồng hồ, tự lưu, vi phạm, nộp, chấm, kết luận
  background.py              Tác vụ nền: nhắc, chấm lại, kiểm tra link, thời hạn lưu
  ai_service/
    llm_grader.py            Quy trình chấm: máy kiểm tra, AI giải thích, máy chủ quyết định
    gateway.py               Cổng AI thống nhất: chat, JSON có schema, gọi công cụ, vector, thử lại, ghi mức dùng
    assessment_provider.py   Nhận xét bài chấm với schema chặt, Gemini đi qua gateway
    knowledge.py             Kho kiến thức: phiên bản, duyệt, chia đoạn, tìm kiếm lai có nguồn
    career_context.py        9 công cụ chỉ đọc theo tài khoản đang đăng nhập
    tool_registry.py         Danh sách công cụ mô hình được gọi, kiểm tra tham số
    guardrails.py            Chặn khi đang thi, giới hạn, kiểm tra trích dẫn và con số
    assistant.py             Trợ lý: vòng hội thoại, ngữ cảnh trang, tóm tắt lịch sử
    task_engine.py           7 nghiệp vụ giải thích, có phương án theo quy tắc
    security.py              Ẩn danh, xác minh trích dẫn
  engine/
    jd_parser.py             Đọc PDF/DOCX/TXT, trích xuất, ánh xạ kỹ năng
    deterministic_grader.py  Bộ kiểm tra DA01-DA03
    exam_grader.py           Ngân hàng đề theo độ khó, kiểm tra từng câu, giới hạn mức
    rubric_engine.py         Điểm, ngưỡng đạt, lỗi trọng yếu
    sql_sandbox.py           Chạy SQL trong tiến trình con dùng một lần
    sql_sandbox_worker.py    Tiến trình cô lập, chỉ đọc bộ dữ liệu của đề
    gap_coverage.py          Coverage, gap, readiness, ưu tiên
    roadmap_planner.py       Chọn hoạt động theo gap và học liệu
    dag_scheduler.py         Kiểm tra chu trình, xếp lịch theo tuần
    link_checker.py          Kiểm tra URL, chặn địa chỉ nội bộ
    test_engine.py           Ngân hàng câu hỏi và chấm câu hỏi khách quan
  api/                       career_process, jds, submissions, roadmaps, resources, learning_cycle, admin_crud, ...
frontend/                    Giao diện ES module thuần, không cần build, không dùng CDN
data/                        Dữ liệu khởi tạo: blueprint, thư viện JD, học liệu, ánh xạ kỹ năng
tests/                       Bộ kiểm thử
```

### Quy tắc nghiệp vụ

Phần này do code tính, không giao cho AI và không tính ở trình duyệt.

- **Quy trình:** mỗi tài khoản chỉ có một quy trình chưa lưu trữ, ràng buộc bằng chỉ mục duy nhất. Máy chủ giữ bước hiện tại; API tự khai, JD, lộ trình từ chối yêu cầu sai bước. Sau khi có kết quả, người học có thể **đổi JD mục tiêu** (`POST /api/v1/career-process/change-goal`): mức đã xác thực, bài kiểm tra, bài học đã đạt và lịch sử được giữ, quy trình quay về bước chọn JD rồi sang thẳng bước lập lộ trình. Muốn làm lại toàn bộ thì reset; reset chỉ tác động đến tài khoản đó và giữ bản lưu trữ ẩn.
- **Bài kiểm tra:** mỗi kỹ năng JD yêu cầu có đúng một câu, nên số câu là từ 1 đến 6 và không trùng chủ đề. Độ khó theo **mức JD yêu cầu** (mức 1 Cơ bản, 2 Trung bình, 3 Khó), không theo mức tự khai, nên ai cũng có thể chứng minh đúng mức JD cần. Đề rút từ ngân hàng 18 dạng câu trên 4 bộ dữ liệu (A-D); làm lại sau reset nhận bộ dữ liệu chưa gặp. Một quy trình chỉ có một lượt làm, đồng hồ theo máy chủ, bài tự lưu, nộp xong khóa. Rời màn hình lần thứ 3 thì tự nộp.
- **Mức xác thực:** từ 70% đạt đúng độ khó của câu; từ 40% thấp hơn một mức; câu Khó có phần đúng được mức 1; bỏ trống là mức 0; lỗi trọng yếu giới hạn ở mức 1. Câu Cơ bản không chứng minh được quá mức 1.
- **Chống lách bài viết:** một khái niệm chỉ được tính khi nằm trong câu còn ít nhất 3 từ của chính người viết ngoài các từ khóa của ý đó (liệt kê "mẫu nhỏ, t-test" không được điểm). Từ 5.46, chữ chép nguyên từ đề (5 từ liền) và cụm đệm lặp lại ở hai câu (4 từ liền) không được tính là lời giải thích, và câu nêu từ 3 khái niệm trở lên mà số từ riêng ít hơn số khái niệm bị coi là danh sách từ khóa. Câu có kiểm tra số liệu mà không có số liệu đúng nào thì tối đa mức 1, dù nêu đủ khái niệm.
- **Chính sách ngưỡng:** mọi ngưỡng đạt và thời gian chờ nằm trong `backend/assessment_policy.py`; `GET /me/assessment-policy` trả đúng các số máy chủ đang áp dụng và trang Khoảng cách kỹ năng hiện chúng.
- **Độ tin cậy đánh giá:** `GET /me/assessment-reliability` cho biết mỗi mức kỹ năng dựa trên bao nhiêu bài làm và loại kiểm tra nào (chạy code, số liệu tự tính, chỉ cụm từ khóa, câu hỏi đóng, người duyệt), xếp Cao / Trung bình / Thấp kèm lý do. Bảng chỉ đọc, không đổi mức.
- **Lỗi thực tế:** trang bài học liệt kê các test case người học đã trượt ở bài làm thực hành gần nhất của kỹ năng đó (`backend/mistakes.py`), không đổi lịch hay mức.
- **Hủy đổi mục tiêu:** khi đã bấm Đổi JD mục tiêu mà chưa chọn JD mới, `POST /api/v1/career-process/change-goal/cancel` đưa quy trình về đúng bước, trạng thái và thời điểm hoàn tất trước đó.
- **Chấm nền:** nộp bài chỉ khóa câu trả lời rồi đưa bài vào hàng đợi chấm (`backend/grading_queue.py`), nên yêu cầu nộp trả về ngay. Một nhóm luồng cố định chấm bài, giới hạn số sandbox chạy cùng lúc. Bài bị ngắt khi máy chủ dừng được chấm lại ở lần quét nền kế tiếp; trạng thái `SUBMITTED → GRADING → GRADED` bảo đảm không chấm hai lần. Trong lúc chờ, giao diện hiện màn hình "Đang chấm bài" và tự mở kết quả.
- **Chấm bài:** bài được lưu trước. Bộ kiểm tra chạy test case, rule engine tính điểm và cổng lỗi trọng yếu. AI chỉ nhận xét, không thể cộng điểm.
- **Đạt:** từ 70/100 và không có lỗi trọng yếu. Mức 0-3 lấy từ hành vi rubric, không chỉ từ phần trăm.
- **AI trong bài kiểm tra:** AI lỗi hoặc trích dẫn giả chỉ làm mất nhận xét AI, kết quả máy vẫn có hiệu lực, bài được gắn cờ cho quản trị viên.
- **Trạng thái (bài theo API cũ):** `GRADED`, `NEEDS_REVIEW` (AI bất đồng hoặc trích dẫn giả), `PENDING_RETRY` (AI lỗi, tối đa 3 lần), `INCOMPLETE` (bài rỗng), `INVALID` (thiếu đầu ra bắt buộc). Chỉ `GRADED` và kết quả đã duyệt mới cập nhật hồ sơ, trong một giao dịch.
- **Coverage** = tổng trọng số kỹ năng có bằng chứng hợp lệ. **Gap** = max(0, mục tiêu − hiện tại). Kỹ năng chưa đánh giá không có gap, không phải mức 0.
- **Readiness** = 100 × tổng(trọng số × mức đạt) / coverage, chỉ mở khi coverage ≥ 80% và đủ kỹ năng cốt lõi.
- **Ưu tiên** = trọng số × (gap / mục tiêu) / giờ ước tính; hòa thì xét cốt lõi, trọng số, mã kỹ năng.
- **Roadmap:** kỹ năng chưa đo được xếp bài đánh giá trước. Học phần cần học liệu đã duyệt. Hoạt động chỉ chia nhỏ khi được phép và chỉ xếp khi hoàn thành kịp hạn. Không tự tăng giờ. Mọi phần không xếp được đều có lý do.
- **Mini-test:** đạt mới được ghi nhận; một bài ôn tập ngắn tăng tối đa một mức và không bao giờ hạ mức. Đánh dấu hoàn thành học phần không làm thay đổi năng lực.
- **Kiểm tra hoàn thành bài học:** trắc nghiệm (chọn, số, sắp xếp) xác nhận tối đa mức 2; mức 3 cần bài làm thực hành ở bài kiểm tra đầu vào hoặc bài đánh giá tổng hợp. Trượt thì sau 6 giờ mới mở bài mới, để người học ôn lại thay vì làm lại đến khi nhớ đáp án.
- **Lịch học:** tuần đã qua ngày kết thúc mà còn bài chưa đạt được báo "Trễ N ngày"; nút "Dời lịch từ hôm nay" xếp lại các bài còn lại bắt đầu từ hôm nay và lưu thành phiên bản lộ trình mới.
- **So khớp JD:** trang Khoảng cách kỹ năng so năng lực đã xác thực với mọi JD đã duyệt trong thư viện, dùng cùng công thức với JD đang chọn. Kỹ năng chưa đo được ghi là chưa đo, không tính là 0.
- **Câu hỏi đóng góp:** chỉ tài khoản được quản trị viên cấp quyền mới viết được câu. Câu phải qua kiểm tra tự động trước khi gửi: đáp án mẫu đạt 100/100 trên cả 4 bộ dữ liệu, các bài sai điển hình dưới 40 điểm, cấu trúc hợp lệ, không trùng câu đã có. Sau đó một quản trị viên khác người viết đọc và quyết định (duyệt, yêu cầu sửa kèm lý do, không duyệt). Muốn duyệt, người duyệt phải xác nhận từng mục chỉ người mới đánh giá được (đã tự giải câu, đề rõ ràng, đúng độ khó, không lộ đáp án; và bản tiếng Anh cùng nghĩa nếu có); xác nhận được lưu cùng quyết định. Người viết có thể kèm bản tiếng Anh: phải dịch đủ mọi mục có chữ tiếng Việt hoặc bỏ trống toàn bộ; bản dịch chỉ được dùng sau khi duyệt. Khi duyệt, máy chủ kiểm tra lại lần nữa rồi mới xuất bản. Bài thi vẫn 1 câu mỗi kỹ năng, rút ngẫu nhiên trong các câu đã duyệt của ô đó, ưu tiên câu chưa gặp; tác giả không bao giờ nhận câu của chính mình.
- **Sau hoàn tất:** kết luận bài kiểm tra và lộ trình được giữ nguyên. Tiến độ, chu kỳ và mini-test vẫn cập nhật.

### An toàn và quyền riêng tư

- Python chạy trong tiến trình con riêng (`backend/engine/python_sandbox.py`): kiểm tra mã trước khi chạy, môi trường trống, thư mục tạm chỉ có tệp dữ liệu, giới hạn CPU 8 giây, thời gian 20 giây, bộ nhớ 900 MB, một tiến trình, và móc kiểm soát chặn file ngoài thư mục, mạng, lệnh hệ thống.
- SQL chạy trong tiến trình con riêng, không có biến môi trường, thư mục tạm, giới hạn thời gian và bộ nhớ, chỉ đọc bộ dữ liệu của đề. Bài Python trong quy trình được chạy thật trong sandbox nói trên.
- Bài làm được ẩn danh trước khi gửi AI và luôn được coi là dữ liệu không đáng tin.
- Bài thi mở ở hai tab: mỗi lần lưu gửi kèm thời điểm lưu trang đã biết; nếu tab khác đã lưu bản khác, máy chủ từ chối (409) thay vì ghi đè. Một lần lưu làm đáp án dài thêm từ 300 ký tự được máy chủ ghi nhận là dán, hiện ở phần kết quả để tham khảo, không ảnh hưởng điểm.
- Mỗi học viên chỉ chạy một lần chạy code tại một thời điểm, kể cả khi có nhiều tiến trình máy chủ (lease trong SQLite).
- Người dùng tải được dữ liệu và xóa toàn bộ hồ sơ, kể cả bản lưu trữ. Nội dung bài nộp theo API cũ tự xóa sau 90 ngày; bài kiểm tra trong quy trình được giữ để xem lại.

### Không gian làm bài

Mỗi câu trong `data/exam_items_v5.json` khai báo `workspace`, và `frontend/js/workspaces.js` chọn công cụ theo đúng trường này:

| `workspace` | Công cụ |
|---|---|
| `sql` | Trình soạn SQL, cấu trúc bảng, xem trước dữ liệu, chạy truy vấn thật, kết quả và lỗi |
| `python` | Trình soạn Python, chạy thật, console, lỗi, bảng DataFrame, biểu đồ |
| `report` | Soạn thảo Markdown có thanh định dạng, xem trước, đếm từ, tự lưu; bài cần thì có nút chèn các mục |
| `data_quality` | Bảng dữ liệu lọc, sắp xếp, tự đánh dấu dòng lỗi, kèm khung trả lời |
| `visualization` | Dựng biểu đồ xem trước, kèm khung trả lời |

Mọi công cụ đều lưu một đáp án dạng văn bản, nên việc lưu, nộp và chấm dùng chung một đường. Câu trắc nghiệm ở Kiểm tra kiến thức giữ giao diện chọn đáp án sẵn có, theo trường `type` của câu.

Python được chấm theo kết quả chạy thật: `py_parses` kiểm tra cú pháp, `py_runs` kiểm tra chạy xong không lỗi, các ca `section: output` đọc đúng những gì code in ra. Số viết trong comment không được tính. Thư viện editor nằm trong `frontend/js/vendor` vì chính sách bảo mật của trang không cho tải từ CDN.

### Giao diện và ngôn ngữ

- Sáng, Tối, Theo hệ thống: nút ở thanh trên, trang Hồ sơ và trang đăng nhập. Mặc định theo hệ thống, tự đổi khi thiết bị đổi và lưu trên trình duyệt.
- Tiếng Việt, tiếng Anh: nút VI/EN ở thanh trên, trang Hồ sơ và trang đăng nhập. Lựa chọn lưu theo trình duyệt và tài khoản.
- Tiếng Việt là bản gốc của mọi dữ liệu. Tiếng Anh được dịch lúc hiển thị (`frontend/js/translate.js`, `frontend/js/lang/en.json`), nên form quản trị không thể ghi đè nội dung gốc bằng bản dịch.
- Đề thi và ngân hàng câu hỏi dịch phía máy chủ (`data/i18n/sensitive_en.json`, `backend/i18n.py`), vì `en.json` là tệp công khai. Bài tự luận nhận từ khóa và số viết theo cả hai ngôn ngữ.
- Thêm chuỗi tiếng Việt mới thì phải thêm bản dịch: `tests/test_i18n.py` sẽ báo thiếu. Chuỗi không hiển thị cho người dùng ghi vào `tests/i18n_not_displayed.txt`. `scripts/i18n_extract.py` liệt kê toàn bộ chuỗi.

### Trợ lý CareerAdapt AI

- Trợ lý bị máy chủ từ chối (423) khi đang làm bài kiểm tra, bài Kiểm tra kiến thức tính điểm, hoặc mini-test đã mở trong 30 phút gần nhất. Nội dung gõ lúc đó không được lưu.
- Mô hình chỉ có công cụ đọc, không có công cụ ghi, không truyền được mã tài khoản và không tạo được SQL.
- Câu trả lời chuyên môn phải trích dẫn nguồn đã truy xuất; không có nguồn hoặc dữ liệu thì Trợ lý nói chưa đủ căn cứ. Số liệu cá nhân hiển thị trong khung riêng lấy trực tiếp từ backend.
- Ngân hàng đề, đề thi, rubric, blueprint và dữ liệu người dùng không được nhập vào kho kiến thức. Tài liệu tải lên lặp lại nội dung đề bị từ chối.
- Gửi cho nhà cung cấp AI nghĩa là gửi câu hỏi và kết quả công cụ đã ẩn danh. Theo điều khoản Gemini, gói không trả phí có thể dùng nội dung để cải thiện sản phẩm, nên dữ liệu học viên thật cần dự án có thanh toán.

## Giới hạn hiện tại

- Đã kiểm chứng với Gemini thật qua `tests/test_ai_live.py` (9 test). Đường nhận xét bài chấm bằng AI và provider OpenAI chưa thử với dịch vụ thật. Khi chưa có khóa, tóm tắt JD, giải thích và kết luận do quy tắc tạo ra và giao diện ghi rõ.
- Ngưỡng `MIN_COSINE` = 0,64 được đo trên 18 câu với `gemini-embedding-2`. Đổi mô hình vector thì phải đo lại.
- Tốc độ Gemini dao động: đã đo từ vài giây đến khoảng 26 giây mỗi lượt gọi. Nếu Trợ lý hay chuyển sang tra cứu, tăng `LLM_TIMEOUT_SECONDS` và `AI_REQUEST_DEADLINE_SECONDS`.
- Gói Gemini không trả phí có giới hạn tần suất thấp. Khi bị giới hạn, Trợ lý tự chuyển sang tra cứu không qua AI, và vector được tạo dần theo từng lượt nền.
- Kho kiến thức mới có dữ liệu danh mục, chưa có nội dung bài học. Dữ liệu danh mục mang trạng thái duyệt `seed-import`, chưa có người đọc lại. `data/knowledge/huong_dan_career_adapt.md` là bản nháp, cần quản trị viên duyệt trước khi Trợ lý dùng.
- Ẩn danh dựa trên mẫu và tên, email của chính tài khoản, nên có thể sót thông tin định danh do người dùng tự gõ.
- Kiểm tra con số chỉ xét phần trăm, điểm, giờ và mức. Câu trả lời đã có dữ liệu từ công cụ có thể kèm nhận định không có nguồn.
- Đề do hệ thống chọn từ ngân hàng đã có test case, không do AI sinh, để điểm luôn kiểm chứng được. Ngân hàng mới và mô tả mức tự khai do nhóm phát triển soạn, chưa qua người phụ trách nội dung duyệt.
- Trình duyệt chỉ phát hiện được chuyển tab, rời cửa sổ, dán và sao chép. Không phát hiện được điện thoại hay thiết bị thứ hai, nên không gọi là giám sát bằng AI.
- Mặc định sandbox chạy code trong tiến trình con. Nó chặn tốt lỗi vô ý và lạm dụng thông thường, nhưng móc kiểm soát của Python không phải ranh giới bảo mật tuyệt đối. Triển khai công khai nên đặt `CAREERADAPT_SANDBOX=docker`. Chế độ container đã được kiểm qua bản thay thế lệnh docker, chưa chạy với Docker thật vì máy phát triển không cài Docker.
- Ba bài cũ DA01-DA03 ở luồng quản trị vẫn phân tích tĩnh mã Python như trước.
- Bốn biến thể của một câu cùng dạng, chỉ khác bộ dữ liệu, nên reset nhiều lần vẫn có thể quen đề. Đã có chức năng để chuyên gia đóng góp câu (5.35), nhưng ngân hàng vẫn chỉ có 1 dạng câu mỗi ô kỹ năng × độ khó cho đến khi chuyên gia thật viết và được duyệt. Nhóm không dùng AI viết câu. Câu đóng góp không kèm bản tiếng Anh sẽ hiện bằng tiếng Việt ở giao diện tiếng Anh; hệ thống chỉ kiểm tra bản dịch đủ mục và không còn chữ tiếng Việt, còn nghĩa có đúng không do người duyệt xác nhận.
- Chạy được nhiều tiến trình trên một máy (`CAREERADAPT_WORKERS`), dùng chung một tệp SQLite. Mỗi tiến trình vẫn giữ bản sao trong bộ nhớ và nạp lại khi tiến trình khác thay đổi, nên chưa chạy được trên nhiều máy. Hàng đợi chấm dùng lease trong SQLite để một bài chỉ được một tiến trình chấm.
- Mục tiêu MAE trên tập giữ lại, độ ổn định AI, và thử với 12 người học cần dữ liệu thực nghiệm của nhóm.
- Học liệu và JD khởi tạo được kiểm tra link tự động ngày 01/11/2026 và gắn người duyệt `seed-import`. Người phụ trách nội dung vẫn cần xác nhận nội dung trước khi dùng chính thức. Thời lượng học liệu là ước tính của nhóm.
- JD ngân hàng VIB đang ở trạng thái cần duyệt vì trang nguồn tải bằng JavaScript nên chưa đối chiếu được.
- Ở chế độ `process`, giới hạn bộ nhớ của sandbox phụ thuộc hệ điều hành. Chế độ `docker` dùng giới hạn của container.
- Dùng SQLite, phù hợp một máy chủ. Khi cần nhiều máy chủ nên chuyển sang PostgreSQL.
- Khóa ngoại chỉ có giữa các bảng trong `careeradapt.sqlite3` (10 bảng con). Mã người dùng trỏ sang tệp `accounts.sqlite3` khác nên SQLite không ràng buộc được; tính nhất quán đó vẫn do code bảo đảm. `exam_responses` và `exam_events` chứa dòng của cả hai loại bài thi nên chưa có khóa ngoại.
- Ở tiếng Anh, nội dung người dùng tự viết, JD họ nhập và nhận xét hoặc tóm tắt AI đã lưu từ trước giữ nguyên ngôn ngữ gốc. Giá trị trong bộ dữ liệu đề (Nam, Bac, Trung, Tay) cũng giữ nguyên vì là dữ liệu của đề. Bản dịch do nhóm phát triển soạn, chưa qua người phụ trách nội dung duyệt. Email hệ thống chưa được kiểm tra theo ngôn ngữ.
