"""Benchmark submissions that satisfy the current Tier-1 rubrics.

The DA01A SQL is executed by the read-only sandbox against data/orders_da01a.csv,
so it must be valid SQLite and actually return the reference values.
"""

DA01A_LEVEL_2 = """-- MÃ NGUỒN / TRUY VẤN:
SELECT CAST(strftime('%m', order_date) AS INTEGER) AS month,
       SUM(quantity * unit_price * (1 - discount)) AS net_revenue
FROM (
    SELECT DISTINCT order_id, order_date, COALESCE(NULLIF(region, ''), 'Unknown') AS region,
           quantity, unit_price, discount, status
    FROM orders_raw
    WHERE quantity > 0
) AS cleaned_orders
WHERE status = 'completed'
GROUP BY 1
ORDER BY 1;
SELECT region, SUM(quantity * unit_price * (1 - discount)) AS net_revenue
FROM (
    SELECT DISTINCT order_id, COALESCE(NULLIF(region, ''), 'Unknown') AS region,
           quantity, unit_price, discount, status
    FROM orders_raw
    WHERE quantity > 0
) AS cleaned_orders
WHERE status = 'completed'
GROUP BY region;
-- mom_growth = (540000 - 630000) / 630000 = -14.29%
-- LOG THỰC NGHIỆM:
- Ban đầu: 10 bản ghi đơn hàng.
- Deduplication: loại 1 bản ghi trùng ORD006 -> còn 9 bản ghi.
- Lọc đơn bất thường quantity = 0 (ORD007) -> còn 8 bản ghi.
- Lọc đơn hủy ORD008, chỉ giữ completed -> còn 7 bản ghi.
- Region NULL của ORD004 được chuẩn hóa thành Unknown.
- Tháng 1 = 630.000 VNĐ; Tháng 2 = 540.000 VNĐ; Tổng = 1.170.000 VNĐ; MoM = -14.29%.
- Vùng: Nam = 700.000 VNĐ, Bắc = 370.000 VNĐ, Unknown = 100.000 VNĐ.
"""

DA02A_LEVEL_2 = """import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('orders_da01a.csv')
df = df.drop_duplicates()
df = df[(df['quantity'] > 0) & (df['status'] == 'completed')].copy()
df['region'] = df['region'].fillna('Unknown')
df['net_revenue'] = df['quantity'] * df['unit_price'] * (1 - df['discount'])
regional = df.groupby('region')['net_revenue'].sum()
# Nam: 700.000, Bac: 370.000, Unknown: 100.000
regional.plot(kind='bar')
plt.title('Doanh thu theo khu vực')
plt.xlabel('Khu vực (Region)')
plt.ylabel('Doanh thu (VNĐ)')
"""

DA03A_LEVEL_2 = """Kính gửi Ban Giám Đốc,
Qua phân tích dữ liệu bán lẻ hai tháng đầu năm 2026, tổng doanh thu ròng của cửa hàng đạt 1.170.000 VNĐ.
Trong đó, Tháng 1 đạt 630.000 VNĐ và Tháng 2 đạt 540.000 VNĐ, nghĩa là doanh thu giảm -14.29% so với tháng trước.
Nguyên nhân chính đến từ việc một đơn hàng tại khu vực phía Bắc bị hủy và số đơn hoàn tất trong tháng hai thấp hơn.
Chúng tôi khuyến nghị đội kinh doanh tăng cường chương trình chăm sóc khách hàng tại miền Bắc, đồng thời kiểm tra lý do hủy đơn để giảm tỷ lệ hủy trong các tháng tới.
Về giới hạn dữ liệu, phân tích dựa trên mẫu nhỏ chỉ gồm 10 đơn hàng trong hai tháng nên chưa thể khái quát cho xu hướng cả năm hoặc kết luận nhân quả.
Kết luận, doanh thu đang giảm nhẹ và cần bổ sung thêm dữ liệu của các tháng sau trước khi đưa ra quyết định đầu tư lớn hơn cho khu vực này.
"""

# Adds a measurable follow-up plan (number + KPI wording): the Level 3 criterion.
DA03A_LEVEL_3 = DA03A_LEVEL_2 + "Đề xuất theo dõi KPI tỷ lệ hủy đơn trong 3 tháng tới với mục tiêu dưới 5%.\n"
