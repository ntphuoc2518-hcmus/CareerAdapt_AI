"""A user JD asking for two skills, for tests that need fewer questions than the default target."""
from v4_helpers import client

JD_TEXT = """Vị trí: Data Analyst Intern
Yêu cầu:
- Thành thạo SQL để truy vấn dữ liệu
- Có kinh nghiệm làm sạch dữ liệu và kiểm tra chất lượng dữ liệu
"""


JD_VIZ_ONLY = """Vị trí: Data Analyst Intern
Yêu cầu:
- Biết vẽ dashboard Power BI và trực quan hóa dữ liệu
"""


def confirm_two_skill_jd(headers) -> int:
    return confirm_jd(headers, JD_TEXT, {"SQL", "DATA_QUALITY"})


def confirm_jd(headers, text, keep) -> int:
    jd = client.post("/jds/import", data={"text": text, "title": "Data Analyst Intern"}, headers=headers).json()
    detail = client.get(f"/jds/{jd['jd_id']}/versions/{jd['jd_version']}", headers=headers).json()
    decisions = [{"requirement_id": item["requirement_id"], "decision": "CONFIRM" if item["skill_code"] in keep else "REJECT"} for item in detail["requirements"] if item["in_catalog"]]
    return client.post("/me/target-jd", json={"jd_id": jd["jd_id"], "jd_version": jd["jd_version"], "config_id": "INTERN", "decisions": decisions}, headers=headers).status_code
