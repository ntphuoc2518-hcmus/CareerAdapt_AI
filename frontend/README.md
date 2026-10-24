# CareerAdapt AI — Frontend Prototype

Prototype Frontend sử dụng HTML, CSS và JavaScript thuần. Phiên bản này là môi trường demo phía trình duyệt, chưa kết nối Backend.

## Chạy dự án

1. Giải nén thư mục dự án.
2. Mở thư mục bằng VS Code.
3. Dùng Live Server để mở `index.html` (khuyến nghị), hoặc mở trực tiếp bằng trình duyệt.
4. Mở Developer Tools → Console để kiểm tra lỗi JavaScript.

## Cấu trúc

- `index.html`: cấu trúc các màn hình và giao diện.
- `js/app.js`: xử lý tương tác, trạng thái demo và render dữ liệu.
- `js/state.js`: ghi chú về vị trí state; hiện state vẫn nằm trong `app.js` để tương thích với prototype gốc.
- `css/styles.css`: stylesheet tham khảo có sẵn từ prototype ban đầu.
- `data/skill_framework.json`: dữ liệu mẫu khung kỹ năng.
- `data/mini_tasks.json`: danh mục bài thử mẫu; DA02/DA03 mới ở mức mô tả.

## Chức năng demo

- Đăng nhập/đăng ký giả lập, chế độ khách.
- Lưu quỹ thời gian học trong hồ sơ.
- Hiển thị Skill Gap, Coverage và Readiness dựa trên state mẫu.
- Hiển thị lộ trình, đánh dấu hoạt động hoàn thành, lịch sử và nhắc nhở.
- Lưu một số dữ liệu demo trong `localStorage` để không mất sau khi tải lại trang.

## Giới hạn hiện tại

- Không có xác thực thật; không dùng mật khẩu thật.
- `localStorage` chỉ phục vụ demo trên trình duyệt hiện tại, không thay thế cơ sở dữ liệu.
- Nút nộp bài chỉ ghi nhận thao tác vào lịch sử; chưa gửi bài đến máy chủ và chưa gọi dịch vụ AI.
- Đăng nhập Google/Facebook/Apple là mô phỏng, không phải OAuth.
- DA02/DA03 chưa có biểu mẫu và logic đánh giá riêng.
- Dữ liệu JSON mẫu chưa tự động được tải vào state JavaScript; cần tích hợp loader hoặc API trong bước tiếp theo.

## Quy trình Git đề xuất

```bash
git switch main
git pull origin main
git switch -c feat/frontend-demo-improvements
# chỉnh sửa và kiểm thử code
git add index.html js/app.js js/state.js data README.md
git commit -m "feat: improve frontend demo interactions"
git push -u origin feat/frontend-demo-improvements
```

Hãy thay `main` bằng branch đích mà leader quy định nếu nhóm sử dụng `develop` hoặc branch khác. Tạo Pull Request để leader review; không tự merge khi chưa được phép.
