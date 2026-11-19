"""Helpers and reference answers for the Career Adapt process tests."""
from datetime import timedelta

from backend import clock
from backend.engine.exam_grader import BANK
from backend.store import store
from v4_helpers import ADMIN, STUDENT, STUDENT_2, STUDENT_ID, client  # noqa: F401

P = "/api/v1/career-process"
FACTS = {
    "A": {"n": "7", "max": "320.000", "min": "50.000", "med": "170.000", "a1": "157.500", "a2": "180.000", "m1": "630.000", "m2": "540.000", "pct": "-14,29", "top": "Nam", "top_v": "700.000", "second": "Bac", "second_v": "370.000", "third_v": "100.000", "raw": "1.412.000", "clean": "1.170.000", "diff": "242.000", "dup": "ORD006", "zero": "ORD007", "miss": "ORD004"},
    "C": {"n": "7", "max": "270.000", "min": "136.000", "med": "200.000", "a1": "216.500", "a2": "162.000", "m1": "866.000", "m2": "486.000", "pct": "-43,88", "top": "Dong", "top_v": "710.000", "second": "Bac", "second_v": "502.000", "third_v": "140.000", "raw": "1.732.000", "clean": "1.352.000", "diff": "380.000", "dup": "ORC06", "zero": "ORC07", "miss": "ORC04"},
    "D": {"n": "7", "max": "234.000", "min": "120.000", "med": "180.000", "a1": "186.000", "a2": "170.000", "m1": "744.000", "m2": "510.000", "pct": "-31,45", "top": "Nam", "top_v": "604.000", "second": "Dong", "second_v": "530.000", "third_v": "120.000", "raw": "1.594.000", "clean": "1.254.000", "diff": "340.000", "dup": "ORE06", "zero": "ORE07", "miss": "ORE04"},
    "B": {"n": "7", "max": "300.000", "min": "90.000", "med": "180.000", "a1": "180.000", "a2": "186.000", "m1": "720.000", "m2": "558.000", "pct": "-22,5", "top": "Trung", "top_v": "618.000", "second": "Tay", "second_v": "540.000", "third_v": "120.000", "raw": "1.626.000", "clean": "1.278.000", "diff": "348.000", "dup": "ORB06", "zero": "ORB07", "miss": "ORB04"},
}
CLEAN_CTE = "WITH c AS (SELECT DISTINCT * FROM orders_raw WHERE status = 'completed' AND quantity > 0)"
CLEAN_PY = "import pandas as pd\ndf = pd.read_csv('orders.csv').drop_duplicates()\ndf = df[(df['status'] == 'completed') & (df['quantity'] > 0)].copy()\ndf['net'] = df['quantity'] * df['unit_price'] * (1 - df['discount'])\n"
GOOD = {
    "SQL-1": lambda f: "SELECT order_id, region, quantity FROM orders_raw WHERE status = 'completed' AND quantity > 0;",
    "SQL-2": lambda f: CLEAN_CTE + " SELECT COALESCE(NULLIF(TRIM(region), ''), 'Unknown') AS vung, SUM(quantity * unit_price * (1 - discount)) AS dt FROM c GROUP BY vung;",
    "SQL-3": lambda f: CLEAN_CTE + ", t AS (SELECT substr(order_date, 1, 7) AS thang, SUM(quantity * unit_price * (1 - discount)) AS dt FROM c GROUP BY thang) SELECT thang, dt, ROUND((dt - LAG(dt) OVER (ORDER BY thang)) * 100.0 / LAG(dt) OVER (ORDER BY thang), 2) AS pct FROM t;",
    "DQ-1": lambda f: f"1. Trùng: {f['dup']}\n2. Số lượng 0: {f['zero']}\n3. Thiếu vùng: {f['miss']}",
    "DQ-2": lambda f: "Ban đầu: 10 dòng.\nBỏ trùng còn 9 dòng.\nLoại số lượng bằng 0 còn 8 dòng.\nChỉ giữ completed còn 7 dòng.",
    "DQ-3": lambda f: f"Chưa làm sạch: {f['raw']}. Sau làm sạch: {f['clean']}. Chênh lệch: {f['diff']}. Quy tắc: order_id phải unique; số lượng phải lớn hơn 0 bằng ràng buộc check.",
    "PY-1": lambda f: "import pandas as pd\ndf = pd.read_csv('orders.csv')\nkq = df[df['status'] == 'completed']\nprint(len(kq))",
    "PY-2": lambda f: CLEAN_PY + "df['region'] = df['region'].fillna('Unknown')\nprint(df.groupby('region')['net'].sum())",
    "PY-3": lambda f: CLEAN_PY + "def monthly_change(df):\n    df = df.copy()\n    df['thang'] = pd.to_datetime(df['order_date']).dt.to_period('M')\n    kq = df.groupby('thang')['net'].sum()\n    truoc = kq.shift(1).replace(0, float('nan'))\n    return kq, (kq - truoc) / truoc * 100\nkq, pct = monthly_change(df)\nprint(round(pct.iloc[-1], 2))",
    "VIZ-1": lambda f: "Tôi chọn biểu đồ cột vì cần so sánh doanh thu giữa các vùng. Trục ngang là vùng, trục dọc là doanh thu.",
    "VIZ-2": lambda f: "import matplotlib.pyplot as plt\n" + CLEAN_PY + "kq = df.groupby('region')['net'].sum()\nplt.bar(kq.index, kq.values)\nplt.title('Doanh thu theo vùng')\nplt.xlabel('Vùng')\nplt.ylabel('Doanh thu')\nprint(kq.idxmax(), kq.max())",
    "VIZ-3": lambda f: f"Chỉ số: tổng doanh thu ròng {f['clean']}; số đơn hợp lệ 7; vùng cao nhất {f['top']}: {f['top_v']}. Dùng biểu đồ đường cho xu hướng tháng, biểu đồ cột so sánh vùng. Tránh cắt trục khác 0 vì gây hiểu sai.",
    "WC-1": lambda f: f"Tháng đầu doanh thu đạt {f['m1']} đồng. Tháng sau đạt {f['m2']} đồng. Như vậy doanh thu giảm so với tháng trước.",
    "WC-2": lambda f: f"Kính gửi anh chị. Doanh thu tháng đầu {f['m1']}, tháng sau {f['m2']}, tức là giảm. Tôi đề xuất rà soát đơn hủy. Dữ liệu chỉ có hai tháng nên chưa thể kết luận nguyên nhân.",
    "STAT-1": lambda f: f"1. Số đơn hợp lệ: {f['n']}\n2. Giá trị lớn nhất: {f['max']}\n3. Giá trị nhỏ nhất: {f['min']}\n4. Trung vị: {f['med']}",
    "STAT-2": lambda f: CLEAN_PY + "print('mean', df['net'].mean())\nprint('median', df['net'].median())",
    "STAT-3": lambda f: f"Giá trị đơn trung bình tháng đầu là {f['a1']} đồng, tháng sau là {f['a2']} đồng. Mỗi tháng chỉ có vài đơn nên cỡ mẫu quá nhỏ, chưa thể kết luận khác biệt có ý nghĩa thống kê. Tôi đề xuất chạy thử nghiệm A/B: chia khách ngẫu nhiên thành nhóm đối chứng và nhóm thử, rồi dùng kiểm định t với mức ý nghĩa 5%.",
    "WC-3": lambda f: f"Tóm tắt: doanh thu giảm {f['pct'].lstrip('-')}%.\nPhát hiện: vùng cao nhất {f['top']}: {f['top_v']}.\nKhuyến nghị: nhóm kinh doanh phụ trách rà soát trong tuần tới.\nGiới hạn: dữ liệu chỉ có hai tháng nên chưa đủ kết luận.",
}
WRONG = {"sql": "SELECT 1;", "python": "print('xin chao')", "text": "Em chưa rõ nội dung này nên trả lời đại."}


def item_key(question_item_id: str) -> tuple[str, str]:
    base, variant = question_item_id.rsplit("-", 1)
    return base, variant


def good_answer(item_id: str) -> str:
    base, variant = item_key(item_id)
    return GOOD[base](FACTS[variant])


def set_skills(levels=None, headers=STUDENT, method="PICK"):
    levels = levels if levels is not None else {"SQL": 2, "DATA_QUALITY": 1, "PYTHON": 0, "DATA_VIZ": 2, "WRITTEN_COMM": 3}
    return client.post("/api/v1/me/skill-report/confirm", json={"skills": [{"skill_code": code, "level": level} for code, level in levels.items()], "method": method}, headers=headers)


def set_default_jd(headers=STUDENT):
    return client.post("/me/target-jd", json={"use_default": True}, headers=headers)


def to_exam(headers=STUDENT, levels=None):
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=headers).status_code == 201
    assert set_skills(levels, headers).status_code == 200
    assert set_default_jd(headers).status_code == 200
    response = client.post(f"{P}/exam/start", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def attempt_row(run_step=None):
    return store.db.one("SELECT * FROM exam_attempts ORDER BY started_at DESC LIMIT 1")


def questions_of(attempt_id):
    import json
    row = store.db.one("SELECT payload FROM exam_attempts WHERE attempt_id = ?", (attempt_id,))
    return json.loads(row["payload"])["questions"]


def answer_all(exam, kind="good", headers=STUDENT):
    for question in questions_of(exam["attempt_id"]):
        text = good_answer(question["item_id"]) if kind == "good" else WRONG[question["answer_type"]]
        assert client.put(f"{P}/exam/responses/{question['question_id']}", json={"text": text}, headers=headers).status_code == 200


def complete_process(headers=STUDENT, levels=None, kind="good", weekly_hours=6, timeline_weeks=8):
    exam = to_exam(headers, levels)
    answer_all(exam, kind, headers)
    assert client.post(f"{P}/exam/submit", json={}, headers=headers).status_code == 200
    assert client.post(f"{P}/result/confirm", headers=headers).status_code == 200
    response = client.post(f"{P}/roadmap", json={"weekly_hours": weekly_hours, "timeline_weeks": timeline_weeks}, headers=headers)
    assert response.status_code == 200, response.text
    return exam


def step(headers=STUDENT):
    return (client.get(f"{P}/state", headers=headers).json()["run"] or {}).get("step")


__all__ = ["P", "BANK", "clock", "timedelta"]
