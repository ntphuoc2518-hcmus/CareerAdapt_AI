"""Reference submissions for grading quality (spec section 12.1): at least 24 across DA01-DA03.

These are written and labelled by the development team, not by independent human graders, and the
set is small. The MAE below shows the rule engine agrees with the rubric on known cases; it is not
a calibration result on real learners.
"""
import pytest

from backend.engine.deterministic_grader import verify_submission
from backend.engine.rubric_engine import apply_critical_cap, get_blueprint, score_submission, validate_answers
from sample_submissions import DA01A_LEVEL_2, DA03A_LEVEL_2, DA03A_LEVEL_3
from v4_helpers import DA01_ALL_WRONG, DA01_GOOD, DA02_GOOD, SQL_ONLY

CTE_SQL = """WITH clean AS (SELECT DISTINCT order_id, order_date, COALESCE(NULLIF(region, ''), 'Unknown') AS region, quantity, unit_price, discount, status
                    FROM orders_raw WHERE quantity > 0 AND status = 'completed')
SELECT CAST(strftime('%m', order_date) AS INTEGER) AS month, SUM(quantity * unit_price * (1 - discount)) AS revenue FROM clean GROUP BY 1;
WITH clean AS (SELECT DISTINCT order_id, COALESCE(NULLIF(region, ''), 'Unknown') AS region, quantity, unit_price, discount, status
               FROM orders_raw WHERE quantity > 0 AND status = 'completed')
SELECT region, SUM(quantity * unit_price * (1 - discount)) AS revenue FROM clean GROUP BY region;"""
NO_DISCOUNT = SQL_ONLY.replace("quantity * unit_price * (1 - discount)", "quantity * unit_price")
NO_DEDUP = SQL_ONLY.replace("SELECT DISTINCT", "SELECT")
WITH_CANCELLED = SQL_ONLY.replace("WHERE status = 'completed'\nGROUP BY 1", "GROUP BY 1").replace("WHERE status = 'completed'\nGROUP BY region", "GROUP BY region")
MONTH_ONLY = SQL_ONLY.split("SELECT region")[0]
NO_UNKNOWN = SQL_ONLY.replace("COALESCE(NULLIF(region, ''), 'Unknown') AS region", "region")

DA02_NO_LABELS = {**DA02_GOOD, "Q1_CODE": DA02_GOOD["Q1_CODE"].replace("plt.xlabel('Khu vực (Region)')\n", "").replace("plt.ylabel('Doanh thu (VNĐ)')\n", "")}
DA02_NO_CHART = {**DA02_GOOD, "Q1_CODE": DA02_GOOD["Q1_CODE"].split("regional.plot")[0]}
DA02_NO_GROUP = {**DA02_GOOD, "Q1_CODE": "import pandas as pd\ndf = pd.read_csv('orders_da01a.csv')\nprint(df.head())\n"}
SHORT_REPORT = "Doanh thu tháng 2 giảm so với tháng 1."
NO_LIMIT_REPORT = DA03A_LEVEL_2.split("Về giới hạn dữ liệu")[0] + "Kết luận, cần tiếp tục theo dõi tình hình kinh doanh trong các tháng tiếp theo và đề xuất tăng ngân sách quảng cáo."
WRONG_TREND_REPORT = DA03A_LEVEL_2.replace("doanh thu giảm -14.29%", "doanh thu tăng 14.29%").replace("doanh thu đang giảm nhẹ", "doanh thu đang tăng nhẹ")

# (case id, task, answers, skill, expected level, expected to pass)
REFERENCE = [
    ("DA01-01 đúng hoàn toàn", "DA01A", DA01_GOOD, "SQL", 2, True),
    ("DA01-02 đúng, dùng CTE", "DA01A", {**DA01_GOOD, "Q2_SQL": CTE_SQL}, "SQL", 3, True),
    ("DA01-03 sai toàn bộ", "DA01A", DA01_ALL_WRONG, "SQL", 0, False),
    ("DA01-04 quên giảm giá", "DA01A", {**DA01_GOOD, "Q2_SQL": NO_DISCOUNT}, "SQL", 1, False),
    ("DA01-05 không bỏ trùng", "DA01A", {**DA01_GOOD, "Q2_SQL": NO_DEDUP}, "SQL", 1, False),
    ("DA01-06 cộng đơn hủy", "DA01A", {**DA01_GOOD, "Q2_SQL": WITH_CANCELLED}, "SQL", 1, False),
    ("DA01-07 chỉ có theo tháng", "DA01A", {**DA01_GOOD, "Q2_SQL": MONTH_ONLY}, "SQL", 1, False),
    ("DA01-08 bỏ mất vùng NULL", "DA01A", {**DA01_GOOD, "Q2_SQL": NO_UNKNOWN}, "DATA_QUALITY", 1, False),
    ("DA01-09 thiếu nhật ký làm sạch", "DA01A", {**DA01_GOOD, "Q1_CLEANING": ""}, "DATA_QUALITY", 1, True),
    ("DA01-10 đủ cả", "DA01A", DA01_GOOD, "DATA_QUALITY", 2, True),
    ("DA01-11 sai dấu tỷ lệ", "DA01A", {**DA01_GOOD, "Q3_CHANGE": "Doanh thu tăng 14,29%. Nếu tháng trước bằng 0 thì không tính."}, "SQL", 1, False),
    ("DA01-12 chia nhầm tháng gốc", "DA01A", {**DA01_GOOD, "Q3_CHANGE": "Tỷ lệ thay đổi là -16,67%. Nếu mẫu số bằng 0 thì bỏ qua."}, "SQL", 1, False),
    ("DA02-01 đúng hoàn toàn", "DA02A", DA02_GOOD, "PYTHON", 2, True),
    ("DA02-02 đúng hoàn toàn", "DA02A", DA02_GOOD, "DATA_VIZ", 2, True),
    ("DA02-03 thiếu nhãn trục", "DA02A", DA02_NO_LABELS, "DATA_VIZ", 1, True),
    ("DA02-04 không vẽ biểu đồ", "DA02A", DA02_NO_CHART, "DATA_VIZ", 0, False),
    ("DA02-05 không tổng hợp", "DA02A", DA02_NO_GROUP, "PYTHON", 1, False),
    ("DA02-06 không phải Python", "DA02A", {**DA02_GOOD, "Q1_CODE": "SELECT * FROM orders ((("}, "PYTHON", 0, False),
    ("DA03-01 đúng", "DA03A", {"Q1_REPORT": DA03A_LEVEL_2}, "WRITTEN_COMM", 2, True),
    ("DA03-02 có kế hoạch đo lường", "DA03A", {"Q1_REPORT": DA03A_LEVEL_3}, "WRITTEN_COMM", 3, True),
    ("DA03-03 quá ngắn", "DA03A", {"Q1_REPORT": SHORT_REPORT}, "WRITTEN_COMM", 0, False),
    ("DA03-04 thiếu giới hạn", "DA03A", {"Q1_REPORT": NO_LIMIT_REPORT}, "WRITTEN_COMM", 1, True),
    ("DA03-05 sai chiều xu hướng", "DA03A", {"Q1_REPORT": WRONG_TREND_REPORT}, "WRITTEN_COMM", 1, False),
    ("DA03-06 không liên quan", "DA03A", {"Q1_REPORT": "Hôm nay trời đẹp và tôi rất thích đi dạo cùng bạn bè ở công viên gần nhà."}, "WRITTEN_COMM", 0, False),
]


def grade(task_id, answers):
    blueprint = get_blueprint(task_id)
    validation = validate_answers(blueprint, answers)
    verifier = verify_submission(task_id, "\n".join(answers.values()), {"dataset_preview": "orders_da01a.csv"}, answers)
    scoring = score_submission(blueprint, verifier, validation["blank_questions"])
    apply_critical_cap(verifier["skill_results"], blueprint, scoring)
    return verifier, scoring


def test_reference_set_has_at_least_24_cases_across_three_tasks():
    assert len(REFERENCE) >= 24
    assert {item[1] for item in REFERENCE} == {"DA01A", "DA02A", "DA03A"}


@pytest.mark.parametrize("case", REFERENCE, ids=[item[0] for item in REFERENCE])
def test_reference_case(case):
    _, task_id, answers, skill, expected_level, expected_pass = case
    verifier, scoring = grade(task_id, answers)
    assert verifier["skill_results"][skill]["level"] == expected_level
    assert scoring["passed"] is expected_pass


def test_mean_absolute_error_meets_the_target():
    errors = []
    for _, task_id, answers, skill, expected_level, _ in REFERENCE:
        verifier, _ = grade(task_id, answers)
        errors.append(abs(verifier["skill_results"][skill]["level"] - expected_level))
    assert sum(errors) / len(errors) <= 0.5


def test_no_wrong_submission_ever_passes():
    for _, task_id, answers, _, _, expected_pass in REFERENCE:
        if not expected_pass:
            assert grade(task_id, answers)[1]["passed"] is False


def test_grading_is_reproducible():
    first = grade("DA01A", DA01_GOOD)[1]
    second = grade("DA01A", DA01_GOOD)[1]
    assert first == second


def test_legacy_single_text_still_grades():
    verifier, scoring = grade("DA01A", {"Q2_SQL": SQL_ONLY})
    assert verifier["execution"]["executed"] and scoring["final_score"] < 100
    assert DA01A_LEVEL_2
