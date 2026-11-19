# Checklist kiểm định UI/UX nội bộ · CareerAdapt AI

Lập ngày 19/11/2026 cho đợt 5.57.0. Dùng lại cho mọi lần sửa giao diện sau này.

Cách kiểm:
- Chạy server trên dữ liệu tạm, không mở `data/`. Dùng `scripts/dev_server_isolated.py`, hoặc một thư mục dữ liệu tạm có tài khoản đã hoàn thành quy trình.
- Mở bằng Microsoft Edge thật qua Playwright.
- Kiểm 4 khổ: 1440 × 900, 1280 × 800, 1024 × 768 (tablet), 390 × 844 (điện thoại, có cảm ứng).
- Kiểm cả giao diện sáng, giao diện tối và tiếng Anh.
- Mỗi trang phải không có lỗi console, không có `pageerror`, không có API trả 5xx và không tràn ngang (`scrollWidth - innerWidth <= 0`).

Ký hiệu: ✅ đạt · ⚠️ đạt một phần, có ghi chú · ❌ chưa đạt · — không áp dụng.

## A. Design system

| # | Tiêu chí | Cách kiểm |
| --- | --- | --- |
| A1 | Màu chỉ lấy từ token (`--brand`, `--text`, `--surface`, `--good/--warn/--bad`…). Giao diện tối định nghĩa lại cùng token đó. | Đọc `:root` và `:root[data-theme="dark"]`. |
| A2 | Cỡ chữ theo thang `--fs-*`, độ đậm theo `--fw-*`. Không dùng cỡ lẻ nửa pixel. | `grep "font-size: [0-9.]*px"` trong `app.css`. |
| A3 | Khoảng cách theo lưới 4px (`--sp-*`). | Đọc các thành phần chung. |
| A4 | Bo góc theo thang `--radius-*`. | `grep border-radius`. |
| A5 | Bóng đổ theo cấp `--shadow-xs` … `--shadow-xl`. | Đọc các thành phần chung. |
| A6 | Chiều cao nút và ô nhập theo `--control-*`. Trên màn hình cảm ứng, vùng chạm tối thiểu 44px. | Đo bằng DevTools ở khổ 390 cảm ứng. |
| A7 | Thời lượng và easing của chuyển động theo `--dur-*` và `--ease-*`. | `grep transition` trong `app.css` và `effects.css`. |
| A8 | z-index theo lớp `--z-*`: header, menu con, scrim, ngăn kéo, nút nổi, panel trợ lý, modal, toast, tooltip. | `grep z-index`. |
| A9 | Không có khai báo CSS chết, tức khai báo bị cùng selector ghi đè sau đó. | Script so sánh computed style trước và sau khi dọn phải ra 0 khác biệt. |

## B. Thành phần chung

| # | Thành phần | Tiêu chí |
| --- | --- | --- |
| B1 | Nút | Có đủ trạng thái hover, focus nhìn thấy được, nhấn, disabled và đang xử lý (`aria-busy`). Có các cỡ sm, md, lg. |
| B2 | Ô nhập / chọn / vùng văn bản | Có hover, vòng focus và trạng thái lỗi (`aria-invalid`). Trạng thái disabled phân biệt rõ. Màu chữ gợi ý đủ tương phản. |
| B3 | Tab | Phải có `role="tab"` và `aria-selected`. Mũi tên trái/phải/lên/xuống, Home và End chuyển được tab. Hàng tab cuộn ngang thì có mép mờ báo còn nội dung. |
| B4 | Badge | Cùng chiều cao và cỡ chữ. Mỗi tông màu đạt tương phản AA ở cả hai giao diện. |
| B5 | Toast | Có biểu tượng theo tông và nút đóng. Thông báo lỗi dùng `role="alert"`. Di chuột vào thì dừng đếm giờ. Có hiệu ứng vào/ra. Tối đa 4 toast cùng lúc. Chữ đạt AA ở giao diện tối. |
| B6 | Modal | Có `aria-modal` và `aria-labelledby`. Tab không thoát ra ngoài hộp thoại. Esc đóng hộp thoại. Đóng xong, focus trả về nút đã mở nó. Trang nền không cuộn theo. |
| B7 | Đang tải | Dùng khung xương (skeleton) theo bố cục trang và có chữ cho trình đọc màn hình (`role="status"`). Tắt hiệu ứng khi người dùng chọn giảm chuyển động. |
| B8 | Trống | Có biểu tượng, tiêu đề, một câu hướng dẫn và nút hành động nếu có. |
| B9 | Lỗi | Có `role="alert"`, biểu tượng, nội dung lỗi từ máy chủ và nút "Thử lại". |
| B10 | Thanh tiến độ | Độ dài lấy từ dữ liệu thật và chạy tới giá trị đó. Có chữ số đi kèm. |

## C. Tương tác và chuyển động

| # | Tiêu chí |
| --- | --- |
| C1 | Đổi trang: nội dung mới hiện mờ dần, chỉ đổi opacity, không dùng transform để không phá `position: fixed/sticky`. |
| C2 | Hover có chủ đích: thẻ dẫn tới trang khác thì nâng lên, nút đổi màu, mũi tên trượt nhẹ. |
| C3 | Focus luôn nhìn thấy được, kể cả trên nền navy của thanh bên và trên thanh chào mừng. |
| C4 | Nhấn: nút hơi thu nhỏ và có gợn sóng. |
| C5 | `prefers-reduced-motion: reduce` tắt mọi chuyển động trang trí. Riêng mắt robot vẫn chớp như quy ước cũ. |
| C6 | Không có chuyển động nào che nội dung hoặc chặn thao tác. |

## D. Responsive và accessibility

| # | Tiêu chí |
| --- | --- |
| D1 | Không tràn ngang ở 1440, 1280, 1024 và 390. Bảng rộng thì cuộn trong `.table-wrap`. |
| D2 | Ở 1024 trở xuống, menu dọc của Kế hoạch chuyển thành hàng ngang. Ở 390, thanh bên thành ngăn kéo, nút ☰ có `aria-expanded`. |
| D3 | Tương phản chữ thường ≥ 4.5:1, chữ lớn và biểu tượng ≥ 3:1, ở cả giao diện sáng và tối. |
| D4 | Có link "Bỏ qua điều hướng". Mỗi lần đổi trang, focus về vùng nội dung chính. |
| D5 | Ảnh trang trí có `alt=""` và `aria-hidden`. Nút chỉ có biểu tượng phải có `aria-label`. |
| D6 | Tiếng Anh: mọi chuỗi giao diện đều được dịch. Dữ liệu gốc như tên nguồn hay tên tài liệu được phép giữ nguyên tiếng Việt. |

## E. Từng trang

| Trang | Route | Điểm cần xem |
| --- | --- | --- |
| Đăng nhập / tạo tài khoản | `/login` | CSP `style-src 'self'` (không style inline). Robot đổi biểu cảm. Checklist mật khẩu. Thông báo lỗi. |
| Bảng điều khiển | `#/` | Thanh chào mừng có số liệu thật, các thẻ đi tắt, tiến độ, hoạt động, tài liệu, lộ trình. |
| Quy trình | `#/process`, `#/flow/…` | Chọn nghề, thanh bước, phòng thi, màn chấm, màn hoàn tất. |
| Kế hoạch | `#/plan/da/{overview, exam, gap, roadmap, rank, progress}` | Menu dọc (≥ 1200px) hoặc hàng ngang. Thẻ Trợ lý AI. Hero theo từng mục. |
| Kết quả đánh giá / Kiểm tra học phần / Bài tổng hợp | `#/result/…`, `#/mini/…`, `#/final-exam` | Chế độ phòng thi (`flow-mode`). |
| Học liệu | `#/resources` | Bộ lọc, số kết quả, thẻ học liệu, trạng thái trống. |
| Kiểm tra kiến thức | `#/tests`, `#/tests/run/…`, `#/tests/report/…` | Danh sách bài, lịch sử, trình chạy bài (bảng câu, đồng hồ), báo cáo. |
| Báo cáo năng lực | `#/report` | Bố cục in. |
| Hồ sơ | `#/profile` | Tab dọc có phím mũi tên. Ảnh đại diện. Đổi mật khẩu. |
| Quản trị | `#/admin/…` | 11 mục, bảng, skeleton riêng (`.adm-skeleton`), biểu mẫu thêm và sửa. |
| Đóng góp câu hỏi | `#/contribute` | Hero, bảng câu hỏi, biểu mẫu, báo cáo kiểm tra tự động. |
| Trợ lý AI | panel phải | Esc đóng panel. Chip gợi ý. Đính kèm ảnh. Giọng nói. Trạng thái khóa. |
| Nhắc nhở | chuông | Danh sách ngắn, Esc đóng, `aria-expanded`. |

Kết quả đợt 5.57.0 được ghi ở mục "Bổ sung 19/11/2026 · Phiên bản 5.57.0" trong `UPGRADE_REPORT.md`.
