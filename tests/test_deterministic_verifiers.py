"""Unit Test Suite: Tier-1 Deterministic Graders.

Covers:
1. DA01A (Store Revenue Analysis): SQL executed in the sandbox must return 630k, 540k, Nam/Bac/Unknown; 10 -> 9 -> 8 -> 7.
2. DA01B (Equivalent A/B Task Reassessment).
3. DA02A (Python Pandas & Visualization).
4. DA03A (Business Written Communication & Limitations, 100-300 word guard).
"""
import pytest
from backend.engine.deterministic_grader import (
    verify_da01a_submission, verify_da01b_submission,
    verify_da02a_submission, verify_da03a_submission
)
from sample_submissions import DA01A_LEVEL_2, DA03A_LEVEL_2, DA03A_LEVEL_3

PASSING_SAMPLE_DA01A = DA01A_LEVEL_2

FAILING_SAMPLE_DA01A = """
SELECT * FROM orders;
Tổng doanh thu khoảng 1 triệu đồng.
"""


def test_da01a_passing_benchmark_sample():
    """Passing benchmark sample must pass all numerical and logical checks -> Level 2."""
    res = verify_da01a_submission(PASSING_SAMPLE_DA01A)
    assert res["proposed_level"] == 2
    assert res["passed_all"] is True
    assert res["execution"]["executed"] is True
    # Only the zero-weight beyond-standard checks (CTE/window, validation) may remain open.
    assert {c["check_id"] for c in res["checks"] if not c["passed"]} <= {"SQL_ADVANCED", "DQ_VALIDATION"}


def test_da01a_failing_sample():
    """Failing sample with missing numbers and cleaning logic -> Level 0."""
    res = verify_da01a_submission(FAILING_SAMPLE_DA01A)
    assert res["proposed_level"] == 0
    assert res["passed_checks"] < 2


def test_da01b_ab_reassessment_task():
    """Equivalent A/B task DA01B must run same deterministic verifications."""
    res = verify_da01b_submission(PASSING_SAMPLE_DA01A)
    assert res["task_id"] == "DA01B"
    assert res["proposed_level"] == 2


def test_da02a_python_and_viz_verifier():
    """DA02A requires pandas, groupby, plot, and regional revenue numbers."""
    py_code = """
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('orders.csv')
regional = df.groupby('Region')['Revenue'].sum()
# Nam: 700000, Bac: 370000
regional.plot(kind='bar')
plt.title('Doanh thu theo Khu vực')
plt.ylabel('Doanh thu (VNĐ)')
plt.show()
"""
    res = verify_da02a_submission(py_code)
    assert res["proposed_level"] == 2
    assert res["passed_checks"] >= 2


def test_da03a_too_short_text_fails():
    """DA03A text below the 100-word minimum must fail the word-count check and stay at Level 0."""
    short_text = "Doanh thu giảm -14.29% trong tháng hai."
    res = verify_da03a_submission(short_text)
    assert res["proposed_level"] == 0
    # Min words check must fail
    word_check = next(c for c in res["checks"] if c["check_id"] == "COM_WORD_COUNT")
    assert word_check["passed"] is False


def test_da03a_valid_business_report():
    """DA03A report of 100-300 words with figures, trend, action and limitations -> Level 2."""
    res = verify_da03a_submission(DA03A_LEVEL_2)
    assert 100 <= res["word_count"] <= 300
    assert res["proposed_level"] == 2
    assert res["passed_all"] is True


def test_da03a_measurable_plan_reaches_level_3():
    """A measurable follow-up plan is the beyond-standard criterion for Level 3."""
    assert verify_da03a_submission(DA03A_LEVEL_3)["proposed_level"] == 3


def test_da01a_sql_is_executed_not_keyword_matched():
    """Correct numbers typed into the log cannot pass when the SQL output disagrees."""
    # Mislabel the NULL region in the SQL while the log still claims "Unknown = 100.000".
    # Only the region query selects "order_id, COALESCE(" (the monthly one also selects order_date).
    wrong_sql = DA01A_LEVEL_2.replace("order_id, COALESCE(NULLIF(region, ''), 'Unknown')", "order_id, COALESCE(NULLIF(region, ''), 'Khac')")
    assert wrong_sql != DA01A_LEVEL_2
    res = verify_da01a_submission(wrong_sql)
    region = next(c for c in res["checks"] if c["check_id"] == "SQL_REGION_RESULTS")
    assert region["passed"] is False
    assert res["passed_all"] is False
