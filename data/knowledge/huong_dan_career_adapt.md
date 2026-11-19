# Quy trình Career Adapt

Quy trình Career Adapt gồm sáu bước theo thứ tự cố định: báo cáo kỹ năng, chọn JD, làm bài kiểm tra, xem kết quả, tạo lộ trình và hoàn tất. Mỗi tài khoản chỉ có một quy trình. Máy chủ giữ bước hiện tại nên không thể bỏ qua bước hay quay lại bước trước. Muốn làm lại hoặc đổi nghề, người học phải reset quy trình.

Hệ thống hiện hỗ trợ đầy đủ nghề Data Analyst. Backend Developer và QA Tester chỉ là giao diện mô phỏng, chưa có dữ liệu thật và chưa có bài kiểm tra.

# Bài kiểm tra

Mỗi kỹ năng JD yêu cầu có đúng một câu hỏi, nên bài có từ 1 đến 5 câu. Độ khó của câu theo mức tự khai: mức 0 và 1 nhận câu Cơ bản, mức 2 nhận câu Trung bình, mức 3 nhận câu Khó. Mỗi quy trình chỉ có một lượt làm bài. Đồng hồ chạy trên máy chủ, câu trả lời được tự lưu, bài bị khóa sau khi nộp. Rời màn hình đến lần thứ ba thì bài tự nộp.

Trợ lý AI không hoạt động trong lúc làm bài kiểm tra.

# Mức xác thực và mức tự khai

Mức tự khai là điều người học tự báo cáo, chỉ dùng để so sánh với kết quả và không được xem là bằng chứng. Độ khó của mỗi câu theo mức JD yêu cầu. Mức xác thực là kết quả từ bài kiểm tra do máy chấm.

Đạt từ 70% số điểm của câu thì được công nhận đúng độ khó của câu. Đạt từ 40% đến dưới 70% thì thấp hơn một mức. Câu Khó có phần làm đúng được mức 1. Bỏ trống là mức 0. Mắc lỗi trọng yếu thì giới hạn ở mức 1. Câu Cơ bản không chứng minh được quá mức 1.

# Skill Gap, Coverage và Readiness

Skill Gap của một kỹ năng là số mức còn thiếu so với mức JD yêu cầu. Kỹ năng chưa có bằng chứng được ghi là chưa đánh giá, không phải mức 0.

Coverage là độ phủ bằng chứng, tính bằng tổng trọng số các kỹ năng đã có kết quả đánh giá hợp lệ.

Readiness là mức đáp ứng theo trọng số trên các kỹ năng đã đo. Readiness chỉ được tính khi Coverage đạt ít nhất 80% và mọi kỹ năng cốt lõi đã có bằng chứng; nếu chưa thì Readiness bị khóa. Readiness chỉ phản ánh mục tiêu đang chọn trong phạm vi các bài đã đo, không phải tỷ lệ thành thạo toàn bộ nghề hay khả năng được tuyển dụng.

# Lộ trình học tập

Lộ trình được xếp theo tuần từ khoảng cách kỹ năng, quan hệ tiên quyết giữa các học phần và quỹ giờ người học khai báo. Học phần chỉ dùng học liệu đã được duyệt. Sau khi quy trình hoàn tất, lộ trình được giữ nguyên.

# Tiến độ và mini-test

Người học cập nhật tiến độ từng học phần trong mục Kế hoạch. Đánh dấu hoàn thành không làm thay đổi năng lực. Mini-test đến hạn theo chu kỳ ôn tập; đạt mới được ghi nhận, mỗi bài tăng tối đa một mức và không bao giờ hạ mức.

# Reset

Reset chỉ tác động đến tài khoản của chính người học. Kỹ năng đã khai, JD, bài kiểm tra, mức xác thực, lộ trình, tiến độ và nhắc nhở được chuyển vào bản lưu trữ ẩn. Tài khoản, ngành học, giờ học và dữ liệu của người khác không bị ảnh hưởng. Không thể reset khi bài kiểm tra đang diễn ra.
