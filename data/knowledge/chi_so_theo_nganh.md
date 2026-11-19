# Chỉ số thường gặp theo ngành cho Data Analyst

Tài liệu này giải thích các chỉ số mà Data Analyst hay gặp ở từng ngành, công thức tính và điều cần kiểm tra trước khi báo cáo. Đây là kiến thức nền để đọc JD và đề bài, không phải số liệu thị trường. Mỗi doanh nghiệp có thể định nghĩa chỉ số hơi khác, nên luôn hỏi lại định nghĩa đang dùng.

## Thương mại điện tử và bán lẻ

- Doanh thu ròng: tổng số lượng nhân đơn giá, trừ giảm giá, chỉ tính đơn hoàn thành.
- GMV (tổng giá trị giao dịch): tổng giá trị đơn đặt, thường chưa trừ đơn hủy và hoàn. GMV luôn lớn hơn hoặc bằng doanh thu ròng.
- Giá trị đơn trung bình (AOV): doanh thu chia cho số đơn.
- Tỷ lệ chuyển đổi: số đơn chia cho số phiên truy cập (hoặc số khách truy cập, tùy định nghĩa).
- Tỷ lệ hủy, tỷ lệ hoàn: số đơn hủy hoặc hoàn chia cho tổng số đơn đặt.
- Tỷ lệ khách quay lại: số khách mua từ lần thứ hai chia cho tổng số khách mua trong kỳ.

Câu hỏi thường gặp: doanh thu thay đổi do số đơn hay do giá trị mỗi đơn; vùng hoặc nhóm hàng nào kéo doanh thu xuống; khuyến mãi có làm tăng đơn hay chỉ làm giảm biên lợi nhuận.

Cần kiểm tra: đơn trùng, đơn có số lượng bằng 0, đơn hủy bị tính vào doanh thu, đơn thiếu vùng.

## Ngân hàng và tài chính

- Dư nợ: tổng số tiền khách hàng còn nợ tại một thời điểm.
- Tỷ lệ nợ xấu (NPL): dư nợ nhóm 3 đến nhóm 5 chia cho tổng dư nợ.
- Tỷ lệ CASA: tiền gửi không kỳ hạn chia cho tổng tiền gửi.
- Biên lãi ròng (NIM): thu nhập lãi thuần chia cho tài sản sinh lãi bình quân.
- Tỷ lệ rời bỏ: số khách ngừng sử dụng trong kỳ chia cho số khách đầu kỳ.

Câu hỏi thường gặp: nhóm khách hàng nào có rủi ro trả chậm cao; sản phẩm nào đóng góp nhiều vào tiền gửi; khách rời bỏ có dấu hiệu gì trước đó.

Cần kiểm tra: số liệu tại thời điểm (dư nợ) khác số liệu trong kỳ (doanh số giải ngân); dữ liệu khách hàng là dữ liệu nhạy cảm, chỉ dùng bản đã ẩn danh và đúng quyền truy cập.

## Marketing số

- CTR (tỷ lệ nhấp): số lượt nhấp chia cho số lượt hiển thị.
- CPC (chi phí mỗi lượt nhấp): chi phí chia cho số lượt nhấp.
- CPA (chi phí mỗi chuyển đổi): chi phí chia cho số chuyển đổi.
- ROAS: doanh thu từ quảng cáo chia cho chi phí quảng cáo.
- CAC (chi phí có được một khách hàng): tổng chi phí bán hàng và marketing chia cho số khách hàng mới.

Câu hỏi thường gặp: kênh nào mang lại chuyển đổi rẻ nhất; chiến dịch có tạo thêm doanh thu hay chỉ ghi nhận đơn vốn đã có.

Cần kiểm tra: cách gán chuyển đổi cho kênh (lần nhấp cuối hay nhiều điểm chạm); khung thời gian ghi nhận chuyển đổi; trùng lặp giữa các nền tảng quảng cáo.

## Sản phẩm số và phần mềm thuê bao

- DAU, MAU: số người dùng hoạt động trong ngày, trong tháng.
- Tỷ lệ giữ chân ngày N: số người dùng quay lại vào ngày thứ N chia cho số người dùng bắt đầu cùng ngày.
- Tỷ lệ rời bỏ (churn): số thuê bao hủy trong kỳ chia cho số thuê bao đầu kỳ.
- MRR: doanh thu định kỳ hàng tháng.
- ARPU: doanh thu chia cho số người dùng trong kỳ.

Câu hỏi thường gặp: tính năng mới có làm tăng giữ chân không; người dùng rời bỏ ở bước nào của phễu; thử nghiệm A/B có đủ mẫu để kết luận chưa.

Cần kiểm tra: định nghĩa "hoạt động"; người dùng thử nghiệm và tài khoản nội bộ; múi giờ khi cắt ngày.

## Vận hành và giao nhận

- Tỷ lệ giao đúng hẹn: số đơn giao trong thời gian cam kết chia cho tổng số đơn giao.
- Thời gian giao trung bình: trung bình thời gian từ lúc đặt đến lúc giao thành công.
- Tỷ lệ giao thành công lần đầu: số đơn giao được ở lần giao đầu tiên chia cho tổng số đơn.
- Vòng quay tồn kho: giá vốn hàng bán chia cho tồn kho bình quân.

Câu hỏi thường gặp: tuyến hoặc kho nào chậm; nguyên nhân giao thất bại; tồn kho có đủ cho đợt cao điểm không.

Cần kiểm tra: giá trị thời gian âm hoặc quá lớn do sai múi giờ; đơn bị tách thành nhiều kiện; trung bình bị kéo lệch bởi vài đơn rất trễ, nên xem thêm trung vị.

## Cách dùng khi đọc JD

Khi JD ghi "kiến thức miền" của một ngành, nhà tuyển dụng thường muốn bạn hiểu chỉ số của ngành đó, biết dữ liệu nào tạo ra chỉ số và biết các lỗi dữ liệu hay gặp. Hệ thống chưa có bài đo kiến thức miền, nên phần này không được tính vào mức kỹ năng đã xác thực.
