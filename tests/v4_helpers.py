"""Shared fixtures and sample answers for the V4.0 acceptance tests."""
import uuid

from fastapi.testclient import TestClient

from backend.main import app
from sample_submissions import DA01A_LEVEL_2

client = TestClient(app)
STUDENT = {"Authorization": "Bearer token_student_1"}
STUDENT_2 = {"Authorization": "Bearer token_student_2"}
ADMIN = {"Authorization": "Bearer token_admin"}
STUDENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

SQL_ONLY = DA01A_LEVEL_2.split("-- LOG THỰC NGHIỆM:")[0].replace("-- MÃ NGUỒN / TRUY VẤN:\n", "")

DA01_GOOD = {
    "Q1_CLEANING": "Ban đầu: 10 dòng. Bỏ trùng ORD006 còn 9 dòng. Loại số lượng bằng 0 còn 8 dòng. Chỉ giữ đơn hoàn tất, loại đơn hủy còn 7 dòng.",
    "Q2_SQL": SQL_ONLY,
    "Q3_CHANGE": "Tỷ lệ thay đổi = (540000 - 630000) / 630000 = -14,29%. Nếu tháng trước bằng 0 thì không tính tỷ lệ và báo là không xác định.",
    "Q4_LIMITS": "Doanh thu giảm từ 630.000 xuống 540.000 đồng. Tuy nhiên dữ liệu chưa đủ để kết luận nguyên nhân vì mẫu nhỏ, chỉ có hai tháng.",
}
DA01_ALL_WRONG = {
    "Q1_CLEANING": "Ban đầu 100 dòng, sau đó còn 50 dòng.",
    "Q2_SQL": "SELECT region, 5 AS tong FROM orders_raw;",
    "Q3_CHANGE": "Tăng 99,99%.",
    "Q4_LIMITS": "Doanh thu rất tốt.",
}
DA02_GOOD = {
    "Q1_CODE": """import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('orders_da01a.csv')
df = df.drop_duplicates()
df = df[(df['quantity'] > 0) & (df['status'] == 'completed')].copy()
df['region'] = df['region'].fillna('Unknown')
df['net_revenue'] = df['quantity'] * df['unit_price'] * (1 - df['discount'])
regional = df.groupby('region')['net_revenue'].sum()
regional.plot(kind='bar')
plt.title('Doanh thu theo khu vực')
plt.xlabel('Khu vực (Region)')
plt.ylabel('Doanh thu (VNĐ)')
""",
    "Q2_OUTPUT": "Nam: 700.000\nBac: 370.000\nUnknown: 100.000",
    "Q3_EXPLAIN": "Tôi chọn biểu đồ cột vì cần so sánh các vùng với nhau. Vùng Nam dẫn đầu với 700.000 đồng.",
}


def key() -> str:
    return f"test-{uuid.uuid4()}"


def submit(answers=None, task_id="DA01A", mode="ASSESSMENT", headers=STUDENT, **extra):
    payload = {"task_id": task_id, "mode": mode, "idempotency_key": key(), **extra}
    if answers is not None:
        payload["answers"] = answers
    return client.post("/submissions", json=payload, headers=headers)


def assessment(response, headers=STUDENT):
    return client.get(f"/assessments/{response.json()['submission_id']}", headers=headers).json()
