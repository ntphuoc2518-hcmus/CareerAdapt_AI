"""Conservative, evidence-based assessment verifiers for published tasks.

Each verifier returns rubric checks (which set the skill level) and test-case results (which the
rule engine turns into points). SQL is judged by what it returns in the sandbox, so any syntax
that produces the right output is accepted. Python is analysed statically and never executed.
Reference values are computed from the task's dataset, so an A/B variant has its own answers.
"""
from __future__ import annotations

import ast
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from backend.engine.skill_report import normalize
from backend.engine.sql_sandbox import execute_readonly_sql, load_dataset
from backend.engine.test_engine import _to_number


RUBRIC_PATH = Path(__file__).resolve().parents[2] / "data" / "assessment_rubrics_v1.json"
with RUBRIC_PATH.open("r", encoding="utf-8") as rubric_file:
    ASSESSMENT_RUBRICS: dict[str, Any] = json.load(rubric_file)


def _extract_section(text: str, headings: tuple[str, ...], stop_headings: tuple[str, ...] = ()) -> str:
    lowered = text.lower()
    for heading in headings:
        start = lowered.find(heading.lower())
        if start < 0:
            continue
        start = text.find("\n", start)
        if start < 0:
            return ""
        start += 1
        ends = [lowered.find(stop.lower(), start) for stop in stop_headings if lowered.find(stop.lower(), start) >= 0]
        return text[start:min(ends)] if ends else text[start:]
    return text


def _check(check_id: str, label: str, skill: str, weight: float, passed: bool, detail: str) -> dict:
    return {
        "check_id": check_id,
        "description": label,
        "skill_code": skill,
        "weight": weight,
        "passed": bool(passed),
        "detail": detail,
    }


def _labelled_value(text: str, label_pattern: str, value_patterns: tuple[str, ...]) -> bool:
    """Only accept a number close to its named month/category to avoid digit matches."""
    for line in text.splitlines():
        normalized = line.casefold()
        if re.search(label_pattern, normalized, re.IGNORECASE):
            value_area = re.sub(r"\s+", "", normalized)
            if any(re.search(pattern, value_area, re.IGNORECASE) for pattern in value_patterns):
                return True
    return False


def _near_label(text: str, label: str, value_pattern: str, distance: int = 45) -> bool:
    normalized = re.sub(r"\s+", " ", text.casefold())
    return bool(
        re.search(rf"{label}.{{0,{distance}}}{value_pattern}", normalized, re.IGNORECASE)
        or re.search(rf"{value_pattern}.{{0,{distance}}}{label}", normalized, re.IGNORECASE)
    )


AMOUNT_TOLERANCE_RATIO = 0.001
PERCENT_TOLERANCE = 0.01
NUMBER_TOKEN = re.compile(r"[-−–]?\s?\d[\d.,]*\s*(?:k\b|tr\b|triệu|trieu|nghìn|nghin|ngàn|ngan)?", re.IGNORECASE)


def _near_amount(value: float, amount: float) -> bool:
    return abs(value - amount) <= max(1.0, abs(amount) * AMOUNT_TOLERANCE_RATIO)


def _numbers_in(text: str) -> list[float]:
    """Numbers written in a text, accepting 630.000, 630,000, 630k and 1,17 triệu."""
    values = []
    for match in NUMBER_TOKEN.finditer(text):
        token = match.group(0).replace("−", "-").replace("–", "-").strip()
        unit = re.search(r"[a-zA-Zàệìgâ]+$", token)
        scale = 1.0
        if unit:
            word = unit.group(0).casefold()
            scale = 1_000.0 if word in {"k", "nghìn", "nghin", "ngàn", "ngan"} else 1_000_000.0
            token = token[: unit.start()].strip()
        number = _to_number(token.rstrip(".,"))
        if number is not None:
            values.append(number * scale)
    return values


def _mentions_amount(text: str, amount: float) -> bool:
    return any(_near_amount(value, amount) for value in _numbers_in(text))


@lru_cache(maxsize=8)
def _dataset_reference_cached(dataset_name: str) -> str:
    columns, rows = load_dataset(dataset_name)

    def net(row: dict, discount_as_amount: bool = False, ignore_discount: bool = False) -> float:
        quantity, price, discount = float(row["quantity"]), float(row["unit_price"]), float(row["discount"] or 0)
        if ignore_discount:
            return quantity * price
        if discount_as_amount:
            return quantity * price - discount
        return quantity * price * (1 - discount)

    unique, seen = [], set()
    for row in rows:
        key = tuple(row.get(column) for column in columns)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    positive = [row for row in unique if float(row["quantity"]) > 0]
    completed = [row for row in positive if row["status"] == "completed"]
    months = sorted({row["order_date"][:7] for row in completed})

    def by_month(source: list[dict], **options: Any) -> dict[str, float]:
        return {month: round(sum(net(row, **options) for row in source if row["order_date"].startswith(month)), 2) for month in months}

    monthly = by_month(completed)
    regions: dict[str, float] = {}
    for row in completed:
        label = row["region"].strip() or "Unknown"
        regions[label] = round(regions.get(label, 0.0) + net(row), 2)
    first, second = monthly[months[0]], monthly[months[1]]
    reference = {
        "rows": {"initial": len(rows), "after_dedup": len(unique), "after_nonzero": len(positive), "valid_completed": len(completed)},
        "months": months,
        "monthly": monthly,
        "total": round(first + second, 2),
        "regions": regions,
        "change_percent": round((second - first) / first * 100, 2),
        "wrong_base_percent": round((second - first) / second * 100, 2),
        "wrong_values": {
            "CG_CANCELLED_INCLUDED": sorted(set(by_month([row for row in positive]).values()) - set(monthly.values())),
            "CG_DUPLICATE_KEPT": sorted(set(by_month([row for row in rows if float(row["quantity"]) > 0 and row["status"] == "completed"]).values()) - set(monthly.values())),
            "CG_FORMULA_WRONG": sorted((set(by_month(completed, ignore_discount=True).values()) | set(by_month(completed, discount_as_amount=True).values())) - set(monthly.values())),
        },
    }
    return json.dumps(reference)


def dataset_reference(dataset_name: str) -> dict:
    """Reference answers computed from the task dataset by trusted code."""
    return json.loads(_dataset_reference_cached(dataset_name))


def _month_labels(month: str) -> set[str]:
    number = int(month[5:7])
    return {str(number), f"{number:02d}", month, f"{month}-01", f"thang {number}", f"thang {number:02d}", f"month {number}", f"t{number}", f"{number}.0"}


def _result_rows(execution: dict) -> list[list[Any]]:
    return [row for result in execution.get("result_sets", []) for row in result.get("rows", [])]


def _row_matches(execution: dict, labels: set[str], amount: float) -> bool:
    """True when one output row holds the label and the expected amount."""
    for row in _result_rows(execution):
        cells = [normalize(str(cell)).strip() for cell in row]
        numbers = [float(cell) for cell in row if isinstance(cell, (int, float)) and not isinstance(cell, bool)]
        if any(cell in labels for cell in cells) and any(_near_amount(number, amount) for number in numbers):
            return True
    return False


def _value_near_label(text: str, label: str, amount: float, distance: int = 60) -> bool:
    """A number only counts when it sits next to the label it is claimed for."""
    normalized = normalize(text)
    key = normalize(label)
    for match in re.finditer(re.escape(key), normalized):
        window = normalized[max(0, match.start() - distance): match.end() + distance]
        if _mentions_amount(window, amount):
            return True
    return False


def _output_numbers(execution: dict) -> list[float]:
    return [float(cell) for row in _result_rows(execution) for cell in row if isinstance(cell, (int, float)) and not isinstance(cell, bool)]


def _test_case(passed: bool, expected: str, actual: str, failure_code: Optional[str] = None) -> dict:
    return {"passed": bool(passed), "expected_summary": expected, "actual_summary": actual[:300], "failure_code": None if passed else (failure_code or "VALUE_MISMATCH")}


def _level_for_skill(skill_rubric: dict, checks: list[dict], thresholds: dict) -> tuple[int, float]:
    ids = {check["check_id"] for check in checks if check["passed"]}
    total_weight = sum(float(item["weight"]) for item in skill_rubric.get("criteria", []) if float(item.get("weight", 0)) > 0)
    earned = sum(float(item["weight"]) for item in skill_rubric.get("criteria", []) if item["id"] in ids and float(item.get("weight", 0)) > 0)
    score = earned / total_weight if total_weight else 0.0
    level = 0
    if score >= float(thresholds.get("1", 0.25)):
        level = 1
    required_l2 = skill_rubric.get("level_2_requires", [])
    if score >= float(thresholds.get("2", 0.75)) and required_l2 and all(item in ids for item in required_l2):
        level = 2
    required_l3 = skill_rubric.get("level_3_requires", [])
    if level == 2 and required_l3 and all(item in ids for item in required_l3):
        level = 3
    return level, round(score, 4)


def _next_steps(checks: list[dict]) -> list[str]:
    """Actionable guidance for failed core checks first, then optional beyond-standard ones."""
    failed = sorted((c for c in checks if not c["passed"]), key=lambda c: c["weight"] <= 0)
    return [
        f"{c['description']}: {c['detail']}" + (" (tiêu chí nâng cao, không bắt buộc cho Level 2)" if c["weight"] <= 0 else "")
        for c in failed
    ]


def _skill_feedback(checks: list[dict]) -> str:
    core = [c for c in checks if c["weight"] > 0]
    passed = [c for c in core if c["passed"]]
    if not core:
        return ""
    if len(passed) == len(core):
        return f"Đạt đủ {len(core)}/{len(core)} tiêu chí cốt lõi."
    missing = [c for c in core if not c["passed"]]
    return (f"Đạt {len(passed)}/{len(core)} tiêu chí cốt lõi. Việc nên làm tiếp: "
            + " ".join(f"{c['description']} — {c['detail']}" for c in missing[:3]))


def _skill_results(task_id: str, checks: list[dict], supported: bool = True) -> dict[str, dict]:
    rubric = ASSESSMENT_RUBRICS["tasks"][task_id]
    if "same_as" in rubric:
        rubric = ASSESSMENT_RUBRICS["tasks"][rubric["same_as"]]
    result = {}
    for code, skill_rubric in rubric["skills"].items():
        skill_checks = [check for check in checks if check["skill_code"] == code]
        level, score = _level_for_skill(skill_rubric, skill_checks, rubric.get("level_thresholds", {}))
        result[code] = {
            "feedback": _skill_feedback(skill_checks),
            "next_steps": _next_steps(skill_checks),
            "skill_code": code,
            "deterministic_level": level,
            "level": level,
            "score": score,
            "confidence": 0.95 if supported else 0.0,
            "passed_checks": sum(check["passed"] for check in skill_checks),
            "total_checks": len(skill_checks),
            "checks": skill_checks,
        }
    return result


def _python_tree(source: str) -> ast.AST | None:
    candidate = source.strip()
    if not candidate:
        return None
    try:
        return ast.parse(candidate)
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
        return None


def _python_calls(tree: ast.AST | None) -> set[str]:
    if tree is None:
        return set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id.lower())
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr.lower())
    return calls


def _format_amount(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _change_value_status(text: str, reference: dict) -> tuple[bool, bool, str]:
    """Return (correct, wrong_sign_or_base, actual summary) for the month-over-month answer."""
    expected = reference["change_percent"]
    normalized = normalize(text)
    numbers = _numbers_in(text)
    near = lambda value, target: abs(value - target) <= PERCENT_TOLERANCE
    falling_word = bool(re.search(r"giam|sut|decrease|decline|drop|fell", normalized))
    rising_word = bool(re.search(r"\btang\b|increase|grew|growth", normalized))
    if any(near(value, expected) for value in numbers):
        return True, False, f"{expected}%"
    if any(near(value, abs(expected)) for value in numbers):
        if expected < 0 and falling_word and not rising_word:
            return True, False, f"giảm {abs(expected)}%"
        if expected > 0 and rising_word and not falling_word:
            return True, False, f"tăng {abs(expected)}%"
        return False, True, "Sai dấu của tỷ lệ thay đổi."
    if any(near(value, reference["wrong_base_percent"]) or near(value, -reference["wrong_base_percent"]) for value in numbers):
        return False, True, "Chia nhầm cho tháng sau thay vì tháng gốc."
    return False, False, "Không tìm thấy giá trị đúng trong câu trả lời."


def verify_da01a_submission(submission_text: str, dataset_name: str = "orders_da01a.csv", answers: Optional[dict[str, str]] = None) -> dict:
    answers = answers or {}
    source = answers.get("Q2_SQL") if answers else None
    if source is None:
        source = _extract_section(
            submission_text,
            ("-- MÃ NGUỒN / TRUY VẤN:", "-- SQL:", "SQL:"),
            ("-- LOG THỰC NGHIỆM", "-- BÁO CÁO GIẢI TRÌNH"),
        )
    context = submission_text
    cleaning_text = answers.get("Q1_CLEANING", "") if answers else context
    change_text = answers.get("Q3_CHANGE", "") if answers else context
    limits_text = answers.get("Q4_LIMITS", "") if answers else context
    reference = dataset_reference(dataset_name)
    rows_ref = reference["rows"]
    month_a, month_b = reference["months"]
    amount_a, amount_b = reference["monthly"][month_a], reference["monthly"][month_b]
    sql = source.casefold()
    text = context.casefold()
    execution = execute_readonly_sql(source, dataset_name) if source.strip() else {"executed": False, "result_sets": [], "error": "Chưa có truy vấn."}
    month_a_ok = _row_matches(execution, _month_labels(month_a), amount_a)
    month_b_ok = _row_matches(execution, _month_labels(month_b), amount_b)
    monthly_correct = month_a_ok and month_b_ok
    region_status = {label: _row_matches(execution, {normalize(label)}, amount) for label, amount in reference["regions"].items()}
    region_correct = all(region_status.values())
    # Correct output proves the logic, so other valid syntaxes are not penalised.
    has_dedup = monthly_correct or bool(re.search(r"\bselect\s+distinct\b|group\s+by\s+[^;]*order_id|row_number\s*\(", sql))
    has_quantity_filter = monthly_correct or bool(re.search(r"quantity\s*(?:>|>=|!=|<>)\s*[01]", sql))
    has_status_filter = monthly_correct or bool(re.search(r"status\s*(?:=|in\s*\()\s*['\"]completed['\"]", sql) or re.search(r"['\"]completed['\"]\s*=\s*(?:lower\s*\()?status", sql))
    has_null_mapping = bool(re.search(r"(?:coalesce|ifnull|nullif)\s*\([^)]*region|region[^\n]{0,80}(?:unknown|'unknown')", sql)) or region_status.get("Unknown", False)
    has_formula = monthly_correct or bool(re.search(r"quantity\s*\*\s*(?:unit_?price|price)\s*\*\s*\(?\s*1\s*-\s*discount|\(\s*1\s*-\s*discount\s*\)\s*\*\s*quantity\s*\*\s*unit_?price|unit_?price\s*\*\s*quantity\s*\*\s*\(?\s*1\s*-\s*discount", sql))
    stage_text = cleaning_text
    chain = re.search(rf"\b{rows_ref['initial']}\D{{1,24}}{rows_ref['after_dedup']}\D{{1,24}}{rows_ref['after_nonzero']}\D{{1,24}}{rows_ref['valid_completed']}\b", stage_text)
    row_initial = bool(chain) or _near_label(stage_text, r"(?:ban đầu|initial|gốc|raw)", rf"\b{rows_ref['initial']}\b", 60)
    row_dedup = bool(chain) or _near_label(stage_text, r"(?:dedup|duplicate|trùng)", rf"\b{rows_ref['after_dedup']}\b", 90)
    row_quantity = bool(chain) or _near_label(stage_text, r"(?:quantity|số lượng|bất thường)", rf"\b{rows_ref['after_nonzero']}\b", 90)
    row_completed = bool(chain) or _near_label(stage_text, r"(?:completed|hoàn tất|hoàn thành|đơn hủy|hủy)", rf"\b{rows_ref['valid_completed']}\b", 100)
    change_ok, change_wrong, change_actual = _change_value_status(change_text, reference)
    executed = bool(execution.get("executed"))
    query_note = f"Truy vấn chưa chạy được: {execution['error']}. Sửa lỗi (cú pháp, tên bảng/cột) và chạy thử trên dữ liệu mẫu." if execution.get("error") else "Truy vấn phải chạy được và có SELECT/FROM kèm SUM hoặc GROUP BY."
    months_label = f"{_format_amount(amount_a)} và {_format_amount(amount_b)}"
    region_label = ", ".join(f"{label} {_format_amount(amount)}" for label, amount in reference["regions"].items())
    checks = [
        _check("SQL_QUERY", "Cấu trúc truy vấn SELECT/FROM kèm phép tổng hợp", "SQL", .15,
               bool(executed and re.search(r"\bselect\b", sql) and re.search(r"\bfrom\b", sql) and re.search(r"\b(?:sum|group\s+by)\b", sql)), query_note),
        _check("SQL_FORMULA", "Công thức quantity × unit_price × (1 − discount)", "SQL", .25, has_formula,
               "Cần thể hiện phép nhân số lượng, đơn giá và phần còn lại sau chiết khấu trong truy vấn."),
        _check("SQL_COMPLETED_FILTER", "Lọc status = completed trong truy vấn", "SQL", .2, has_status_filter,
               "Chỉ lời giải thích trong báo cáo không thay thế bộ lọc ở truy vấn SQL."),
        _check("SQL_MONTHLY_RESULTS", "Kết quả doanh thu từng tháng và tổng có gắn nhãn", "SQL", .2, monthly_correct,
               f"Đầu ra SQL phải trả về đúng doanh thu từng tháng trên bộ dữ liệu của đề ({months_label})."),
        _check("SQL_MOM", "Tỷ lệ biến động gắn với tháng gốc", "SQL", .1, monthly_correct and change_ok,
               "Cần tính tỷ lệ thay đổi từ kết quả tháng đã xác minh."),
        _check("SQL_REGION_RESULTS", "Doanh thu vùng đúng nhãn", "SQL", .1, region_correct,
               f"Đầu ra SQL phải khớp doanh thu theo vùng ({region_label})."),
        _check("SQL_ADVANCED", "Kỹ thuật SQL nâng cao (CTE/window/explain) có trong mã", "SQL", 0,
               bool(re.search(r"\bwith\s+\w+\s+as\s*\(|\bover\s*\(|\bexplain\s+(?:analyze|query\s+plan)", sql)),
               "Tiêu chí vượt chuẩn; từ khóa phải xuất hiện trong mã truy vấn."),
        _check("DQ_DEDUP", "Nêu thao tác loại trùng và đối chiếu số dòng", "DATA_QUALITY", .18,
               has_dedup and row_dedup and bool(re.search(r"dedup|duplicate|trùng", cleaning_text.casefold())),
               "Cần loại trùng thật trong truy vấn và đối chiếu số dòng sau bước đó."),
        _check("DQ_QUANTITY", "Lọc quantity <= 0 và ghi nhận kết quả", "DATA_QUALITY", .18, has_quantity_filter and row_quantity,
               "Truy vấn phải lọc quantity > 0 và ghi nhận số dòng sau bước lọc."),
        _check("DQ_COMPLETED_FILTER", "Loại giao dịch hủy/không hoàn tất", "DATA_QUALITY", .18, has_status_filter and row_completed,
               "Truy vấn phải lọc status = 'completed' và ghi nhận số dòng còn lại."),
        _check("DQ_NULL_REGION", "Xử lý Region NULL thành Unknown", "DATA_QUALITY", .18, has_null_mapping,
               "Mã SQL phải chuẩn hóa Region NULL/thiếu thành Unknown."),
        _check("DQ_ROW_STAGES", f"Đối chiếu đủ {rows_ref['initial']} → {rows_ref['after_dedup']} → {rows_ref['after_nonzero']} → {rows_ref['valid_completed']} theo từng giai đoạn", "DATA_QUALITY", .28,
               row_initial and row_dedup and row_quantity and row_completed and executed,
               "Mỗi mốc cần gắn với đúng bước; truy vấn phải chạy được trên bộ dữ liệu của đề."),
        _check("DQ_VALIDATION", "Có kiểm tra/assert/validation có thể lặp lại", "DATA_QUALITY", 0,
               bool(re.search(r"\b(?:assert|validate|validation|constraint|integrity check|kiểm tra toàn vẹn)\b", text)),
               "Tiêu chí vượt chuẩn; nêu hoặc cài kiểm tra tính toàn vẹn."),
    ]
    skills = _skill_results("DA01A", checks)
    # Evidence rule: Level 2+ always needs SQL that executed and returned the correct figures.
    # Below that, the rubric's Level 1 is "filters orders but aggregation has a material error":
    # a query that ran needs an aggregate with the filter or the formula right; one that did not
    # run needs both. Otherwise SQL stays at 0.
    if not executed or (not monthly_correct and not region_correct):
        passed_ids = {check["check_id"] for check in checks if check["passed"]}
        key_logic = {"SQL_FORMULA", "SQL_COMPLETED_FILTER"} & passed_ids
        sql_logic_sound = (executed and "SQL_QUERY" in passed_ids and bool(key_logic)) or len(key_logic) == 2
        sql_skill = skills["SQL"]
        sql_skill["level"] = sql_skill["deterministic_level"] = min(sql_skill["level"], 1) if sql_logic_sound else 0
        if not executed:
            error = execution.get("error") or "không rõ lỗi"
            for skill in skills.values():
                skill["level"] = skill["deterministic_level"] = min(skill["level"], 1)
                skill["confidence"] = 0.5
            note = (f"Truy vấn chưa chạy được trong sandbox ({error}). "
                    "Hãy chạy thử trên dữ liệu mẫu, sửa lỗi rồi nộp lại; chỉ kết quả chạy đúng mới đạt Level 2.")
        else:
            note = ("Truy vấn chạy được nhưng chưa trả về doanh thu theo tháng/vùng khớp dữ liệu của đề. "
                    "Hãy đối chiếu lại công thức, bộ lọc và cột nhãn (tháng, vùng) trong kết quả.")
        sql_skill["feedback"] = f"{note} {sql_skill['feedback']}".strip()
    # Cleaning that demonstrably worked but was not logged is the rubric's Level 1 for data quality.
    if monthly_correct and skills["DATA_QUALITY"]["level"] == 0:
        skills["DATA_QUALITY"]["level"] = skills["DATA_QUALITY"]["deterministic_level"] = 1

    output_numbers = _output_numbers(execution)
    actual_numbers = ", ".join(_format_amount(value) for value in output_numbers[:8]) or (execution.get("error") or "Không có kết quả từ truy vấn.")
    total_seen = any(_near_amount(value, reference["total"]) for value in output_numbers) or _mentions_amount(context if not answers else " ".join(answers.values()), reference["total"]) or monthly_correct
    region_items = list(reference["regions"].items())
    known_regions = [item for item in region_items if item[0] != "Unknown"]
    known_regions.sort(key=lambda item: -item[1])
    zero_rule = bool(re.search(
        r"(?:mẫu số|mau so|tháng trước|thang truoc|tháng gốc|thang goc|tháng 1|denominator|base|previous).{0,70}(?:=\s*0|bằng\s*0|bằng không|bang 0|zero|\b0\b)|nullif\s*\(|case\s+when[^;]{0,120}=\s*0|chia cho 0|chia cho không",
        f"{change_text}\n{source}", re.IGNORECASE | re.DOTALL))
    figures_in_conclusion = any(_mentions_amount(limits_text, amount) for amount in (amount_a, amount_b, reference["total"])) or any(abs(abs(value) - abs(reference["change_percent"])) <= PERCENT_TOLERANCE for value in _numbers_in(limits_text))
    limitation = bool(re.search(r"chưa đủ|không đủ|chưa thể|không thể kết luận|chưa kết luận|chưa rõ|thiếu dữ liệu|mẫu nhỏ|giới hạn|hạn chế|insufficient|cannot conclude|limited", limits_text.casefold()))
    test_cases = {
        "TC_ROW_INITIAL": _test_case(row_initial, f"{rows_ref['initial']} dòng", "Tìm thấy trong ghi chú." if row_initial else "Không tìm thấy mốc này gắn với bước tương ứng."),
        "TC_ROW_DEDUP": _test_case(row_dedup, f"{rows_ref['after_dedup']} dòng", "Tìm thấy trong ghi chú." if row_dedup else "Không tìm thấy mốc này gắn với bước tương ứng."),
        "TC_ROW_QUANTITY": _test_case(row_quantity, f"{rows_ref['after_nonzero']} dòng", "Tìm thấy trong ghi chú." if row_quantity else "Không tìm thấy mốc này gắn với bước tương ứng."),
        "TC_ROW_COMPLETED": _test_case(row_completed, f"{rows_ref['valid_completed']} dòng", "Tìm thấy trong ghi chú." if row_completed else "Không tìm thấy mốc này gắn với bước tương ứng."),
        "TC_NULL_REGION": _test_case(has_null_mapping, "Vùng thiếu được gán Unknown", "Có xử lý." if has_null_mapping else "Chưa thấy xử lý vùng thiếu."),
        "TC_MONTH_1": _test_case(month_a_ok, f"Tháng {int(month_a[5:7])} = {_format_amount(amount_a)}", actual_numbers),
        "TC_MONTH_2": _test_case(month_b_ok, f"Tháng {int(month_b[5:7])} = {_format_amount(amount_b)}", actual_numbers),
        "TC_TOTAL": _test_case(total_seen, f"Tổng = {_format_amount(reference['total'])}", actual_numbers),
        "TC_REGION_A": _test_case(region_status[known_regions[0][0]], f"{known_regions[0][0]} = {_format_amount(known_regions[0][1])}", actual_numbers),
        "TC_REGION_B": _test_case(region_status[known_regions[1][0]], f"{known_regions[1][0]} = {_format_amount(known_regions[1][1])}", actual_numbers),
        "TC_REGION_UNKNOWN": _test_case(region_status.get("Unknown", False), f"Unknown = {_format_amount(reference['regions'].get('Unknown', 0))}", actual_numbers),
        "TC_CHANGE_VALUE": _test_case(change_ok, f"{reference['change_percent']}%", change_actual),
        "TC_ZERO_BASE": _test_case(zero_rule, "Nêu cách xử lý khi tháng gốc bằng 0", "Có nêu." if zero_rule else "Chưa thấy nêu cách xử lý."),
        "TC_CONCLUSION_FIGURES": _test_case(figures_in_conclusion, "Kết luận có số liệu đúng", "Có số liệu đúng." if figures_in_conclusion else "Không thấy số liệu đúng trong kết luận."),
        "TC_LIMITATION": _test_case(limitation, "Nêu dữ liệu chưa đủ để kết luận nguyên nhân", "Có nêu." if limitation else "Chưa thấy nêu giới hạn."),
    }
    wrong = reference["wrong_values"]
    def signature(gate: str) -> bool:
        return any(_near_amount(number, value) for number in output_numbers for value in wrong[gate])
    critical = {}
    if not monthly_correct:
        critical = {
            "CG_CANCELLED_INCLUDED": signature("CG_CANCELLED_INCLUDED") or not has_status_filter,
            "CG_DUPLICATE_KEPT": signature("CG_DUPLICATE_KEPT") or not has_dedup,
            "CG_FORMULA_WRONG": signature("CG_FORMULA_WRONG") or not has_formula,
        }
    critical["CG_CHANGE_SIGN"] = change_wrong
    critical["CG_REGION_WRONG"] = not region_correct
    return {
        "task_id": "DA01A", "supported": True,
        "total_checks": len(checks), "passed_checks": sum(check["passed"] for check in checks),
        "proposed_level": max((item["level"] for item in skills.values()), default=0),
        "passed_all": all(check["passed"] for check in checks if check["weight"] > 0),
        "checks": checks, "skill_results": skills, "test_cases": test_cases, "critical": critical,
        "execution": {"executed": execution.get("executed", False), "error": execution.get("error"), "result_sets": execution.get("result_sets", [])},
    }


def verify_da01b_submission(submission_text: str, answers: Optional[dict[str, str]] = None) -> dict:
    result = verify_da01a_submission(submission_text, "orders_da01b.csv", answers)
    result["task_id"] = "DA01B"
    return result


def verify_da02a_submission(submission_text: str, answers: Optional[dict[str, str]] = None) -> dict:
    answers = answers or {}
    source = answers.get("Q1_CODE") if answers else None
    if source is None:
        source = _extract_section(
            submission_text,
            ("-- MÃ NGUỒN / TRUY VẤN:", "-- PYTHON:", "python:"),
            ("-- LOG THỰC NGHIỆM", "-- BÁO CÁO GIẢI TRÌNH"),
        )
    output_text = answers.get("Q2_OUTPUT", "") if answers else submission_text
    explain_text = answers.get("Q3_EXPLAIN", "") if answers else submission_text
    tree = _python_tree(source)
    calls = _python_calls(tree)
    imports_pandas = bool(tree and any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and any(alias.name.split(".")[0].lower() == "pandas" for alias in node.names)
        for node in ast.walk(tree)
    ))
    groupby_and_agg = "groupby" in calls and bool(calls.intersection({"sum", "agg", "mean", "median", "describe"}))
    axis_labels = bool(calls.intersection({"xlabel", "set_xlabel"}) and calls.intersection({"ylabel", "set_ylabel"}))
    chart_kind = bool(calls.intersection({"bar", "barh"})) or bool(re.search(r"plot\s*\([^\n]{0,100}kind\s*=\s*['\"](?:bar|barh)['\"]", source, re.IGNORECASE))
    ylabel_mentions_revenue = bool(re.search(r"(?:ylabel|set_ylabel).{0,100}(?:doanh thu|revenue)", source, re.IGNORECASE | re.DOTALL))
    xlabel_mentions_region = bool(re.search(r"(?:xlabel|set_xlabel).{0,100}(?:khu vực|region)", source, re.IGNORECASE | re.DOTALL))
    title = bool(calls.intersection({"title", "set_title"})) and bool(re.search(r"(?:doanh thu|revenue).{0,80}(?:vùng|khu vực|region)|(?:vùng|khu vực|region).{0,80}(?:doanh thu|revenue)", source, re.IGNORECASE | re.DOTALL))
    units = bool(re.search(r"vnđ|vnd|₫|đồng|currency", source, re.IGNORECASE))
    checks = [
        _check("PY_IMPORT", "Python parse được và import pandas", "PYTHON", .15, bool(tree and imports_pandas), "Mã Python phải hợp cú pháp và import pandas thật."),
        _check("PY_LOAD", "Đọc CSV bằng pandas.read_csv", "PYTHON", .25, bool(tree and "read_csv" in calls), "read_csv phải là lời gọi trong mã, không chỉ được nhắc trong phần mô tả."),
        _check("PY_AGGREGATE", "Dùng groupby kết hợp phép tổng hợp", "PYTHON", .35, bool(tree and groupby_and_agg), "Cần có lời gọi groupby và sum/agg/mean/median/describe."),
        _check("PY_CLEAN", "Có bước xử lý trùng, thiếu hoặc quantity không hợp lệ", "PYTHON", .25,
               bool(tree and calls.intersection({"drop_duplicates", "fillna", "dropna", "replace", "query"}) and re.search(r"quantity|region|duplicate|null|thiếu|trùng", source, re.IGNORECASE)),
               "Cần thao tác làm sạch có trong mã và áp dụng lên trường dữ liệu liên quan."),
        _check("PY_REUSABLE", "Có hàm tái sử dụng và xử lý lỗi", "PYTHON", 0, bool(tree and any(isinstance(node, ast.FunctionDef) for node in ast.walk(tree)) and "try" in source.casefold()), "Tiêu chí vượt chuẩn."),
        _check("VIZ_TYPE", "Mã tạo biểu đồ cột phù hợp dữ liệu theo vùng", "DATA_VIZ", .25, bool(tree and chart_kind), "Cần lệnh biểu đồ cột trong mã, không chỉ nhắc tên biểu đồ."),
        _check("VIZ_LABELS", "Mã đặt cả nhãn trục vùng và doanh thu", "DATA_VIZ", .3, bool(tree and axis_labels and ylabel_mentions_revenue and xlabel_mentions_region), "Nhãn trục X cần nêu vùng; trục Y nêu doanh thu."),
        _check("VIZ_TITLE", "Mã đặt tiêu đề có ý nghĩa", "DATA_VIZ", .15, bool(tree and title), "Tiêu đề cần liên hệ doanh thu với phân bổ vùng."),
        _check("VIZ_UNITS", "Mã hiển thị đơn vị tiền tệ", "DATA_VIZ", .3, bool(tree and units), "Nêu VNĐ/VND/đồng trong nhãn hoặc tiêu đề biểu đồ."),
        _check("VIZ_ANNOTATION", "Mã thêm chú thích/insight vào biểu đồ", "DATA_VIZ", 0, bool(tree and calls.intersection({"annotate", "text"})), "Tiêu chí vượt chuẩn."),
    ]
    skills = _skill_results("DA02A", checks)
    passed = {check["check_id"]: check["passed"] for check in checks}
    reference = dataset_reference("orders_da01a.csv")
    known = sorted(((label, amount) for label, amount in reference["regions"].items() if label != "Unknown"), key=lambda item: -item[1])

    def output_case(label: str, amount: float) -> dict:
        found = _value_near_label(output_text, label, amount)
        return _test_case(found, f"{label} = {_format_amount(amount)}", "Khớp." if found else "Không tìm thấy giá trị đúng gắn với vùng này.")

    insight = bool(_numbers_in(explain_text)) and any(_mentions_amount(explain_text, amount) for amount in reference["regions"].values())
    choice = bool(re.search(r"vì|bởi|do |because|so sánh|compare|phù hợp|suitable", explain_text.casefold())) and bool(re.search(r"cột|bar|column|biểu đồ|chart", explain_text.casefold()))
    code_case = lambda check_id, expected: _test_case(passed[check_id], expected, "Có trong mã." if passed[check_id] else "Chưa thấy trong mã.", "NOT_FOUND_IN_CODE")
    test_cases = {
        "TC_PY_PARSE": code_case("PY_IMPORT", "Mã hợp cú pháp và import pandas"),
        "TC_PY_READ": code_case("PY_LOAD", "Lời gọi read_csv"),
        "TC_PY_CLEAN": code_case("PY_CLEAN", "Thao tác làm sạch trên trường liên quan"),
        "TC_PY_GROUP": code_case("PY_AGGREGATE", "groupby kết hợp phép tổng hợp"),
        "TC_OUT_REGION_A": output_case(*known[0]),
        "TC_OUT_REGION_B": output_case(*known[1]),
        "TC_OUT_REGION_UNKNOWN": output_case("Unknown", reference["regions"]["Unknown"]),
        "TC_VIZ_TYPE": code_case("VIZ_TYPE", "Lệnh vẽ biểu đồ cột"),
        "TC_VIZ_LABELS": code_case("VIZ_LABELS", "Nhãn trục vùng và doanh thu"),
        "TC_VIZ_TITLE": code_case("VIZ_TITLE", "Tiêu đề nối doanh thu với vùng"),
        "TC_VIZ_UNITS": code_case("VIZ_UNITS", "Đơn vị tiền tệ trong biểu đồ"),
        "TC_EXPLAIN_CHOICE": _test_case(choice, "Nêu lý do chọn biểu đồ", "Có nêu." if choice else "Chưa thấy lý do chọn biểu đồ."),
        "TC_EXPLAIN_INSIGHT": _test_case(insight, "Nhận xét có số liệu đúng", "Có số liệu đúng." if insight else "Chưa thấy số liệu đúng trong nhận xét."),
    }
    return {
        "task_id": "DA02A", "supported": True,
        "total_checks": len(checks), "passed_checks": sum(check["passed"] for check in checks),
        "proposed_level": max((item["level"] for item in skills.values()), default=0),
        "passed_all": all(check["passed"] for check in checks if check["weight"] > 0),
        "checks": checks, "skill_results": skills, "test_cases": test_cases,
        "critical": {"CG_CODE_NOT_PARSED": tree is None},
        "execution": {"executed": False, "error": None, "note": "Mã Python được phân tích tĩnh, không chạy trên máy chủ."},
    }


def verify_da03a_submission(submission_text: str, answers: Optional[dict[str, str]] = None) -> dict:
    report = (answers or {}).get("Q1_REPORT")
    if report is None:
        report = _extract_section(
            submission_text,
            ("-- BÁO CÁO GIẢI TRÌNH NGHIỆP VỤ:", "-- BÁO CÁO:", "báo cáo:"),
        )
    words = re.findall(r"[\wÀ-ỹ]+(?:[’'-][\wÀ-ỹ]+)*", report, re.UNICODE)
    word_count = len(words)
    text = report.casefold()
    numbers_ok = (
        bool(re.search(r"1[.,]?170[.,]?000|1170000", text))
        and bool(re.search(r"630[.,]?000|630k", text))
        and bool(re.search(r"540[.,]?000|540k", text))
        and bool(re.search(r"-\s*14[.,]29\s*%?", text))
    )
    trend_context = bool(re.search(r"(?:giảm|giảm\s*14|sụt giảm|decrease|decline|tăng).{0,80}-?\s*14[.,]29|(?:-?\s*14[.,]29).{0,80}(?:giảm|sụt|doanh thu|revenue|mom)", text))
    recommendation = bool(re.search(r"đề xuất|khuyến nghị|khuyến cáo|recommend|nên |cần .*?(?:tăng|giảm|theo dõi|kiểm tra|thử nghiệm)", text))
    # Merely mentioning "two months" is not a limitation; the sentence has to limit the conclusion.
    limitation = bool(re.search(r"mẫu nhỏ|mẫu chỉ|sample size|limited sample|(?:10 dòng|10 đơn|2 tháng|hai tháng).{0,100}(?:chưa|không|khó|giới hạn|nhân quả)|(?:chưa|không|khó).{0,70}(?:khái quát|suy rộng|nhân quả|đại diện)", text))
    structure = bool(re.search(r"kết luận|tóm lại|summary|therefore", text)) and recommendation and numbers_ok
    measurable_plan = bool(re.search(r"\b\d+\s*(?:ngày|tuần|tháng|%|đơn|khách|orders?)\b", text)) and bool(re.search(r"theo dõi|đo lường|mục tiêu|kpi|thử nghiệm", text))
    checks = [
        _check("COM_WORD_COUNT", "Báo cáo từ 100 đến 300 từ", "WRITTEN_COMM", .1, 100 <= word_count <= 300, f"Đếm được {word_count} từ; yêu cầu 100–300."),
        _check("COM_DATA_EVIDENCE", "Có đủ bốn số liệu đúng, có ngữ cảnh", "WRITTEN_COMM", .25, numbers_ok, "Cần đối chiếu tổng, cả hai tháng và tỷ lệ giảm."),
        _check("COM_TREND", "Diễn giải xu hướng gắn với số liệu âm", "WRITTEN_COMM", .2, trend_context, "Cần nêu đúng doanh thu giảm khoảng 14,29%; không được kết luận tăng."),
        _check("COM_ACTION", "Có khuyến nghị hành động cụ thể", "WRITTEN_COMM", .2, recommendation, "Khuyến nghị phải là hành động, không chỉ dùng từ 'đề xuất'."),
        _check("COM_LIMITATION", "Nêu giới hạn mẫu nhỏ/phạm vi hai tháng", "WRITTEN_COMM", .15, limitation, "Cần cảnh báo phạm vi kết luận từ 10 dòng và 2 tháng."),
        _check("COM_STRUCTURE", "Kết luận gắn với bằng chứng và hành động", "WRITTEN_COMM", .1, structure, "Cần có kết luận, số liệu và bước tiếp theo."),
        _check("COM_MEASURABLE_PLAN", "Kế hoạch có chỉ số hoặc thời hạn", "WRITTEN_COMM", 0, measurable_plan, "Tiêu chí vượt chuẩn."),
    ]
    skills = _skill_results("DA03A", checks)
    reference = dataset_reference("orders_da01a.csv")
    amount_a, amount_b = (reference["monthly"][month] for month in reference["months"])
    change_ok = bool(re.search(r"-\s*14[.,]29", text)) or bool(re.search(r"giảm.{0,30}14[.,]29|14[.,]29.{0,30}giảm", text))
    wrong_trend = bool(re.search(r"(?:doanh thu|revenue)[^.\n]{0,40}\b(?:tăng|increase|grew)\b", text)) and not re.search(r"(?:doanh thu|revenue)[^.\n]{0,60}(?:giảm|decrease|decline)", text)
    mention = lambda amount: _mentions_amount(report, amount)
    found = "Có trong báo cáo."
    missing = "Không tìm thấy trong báo cáo."
    test_cases = {
        "TC_FIG_TOTAL": _test_case(mention(reference["total"]), _format_amount(reference["total"]), found if mention(reference["total"]) else missing),
        "TC_FIG_M1": _test_case(mention(amount_a), _format_amount(amount_a), found if mention(amount_a) else missing),
        "TC_FIG_M2": _test_case(mention(amount_b), _format_amount(amount_b), found if mention(amount_b) else missing),
        "TC_FIG_CHANGE": _test_case(change_ok, f"{reference['change_percent']}%", found if change_ok else missing),
        "TC_TREND": _test_case(trend_context and not wrong_trend, "Doanh thu giảm", found if trend_context and not wrong_trend else "Chưa nêu đúng xu hướng giảm."),
        "TC_ACTION": _test_case(recommendation, "Có khuyến nghị hành động", found if recommendation else missing),
        "TC_LIMIT": _test_case(limitation, "Nêu giới hạn mẫu và phạm vi kết luận", found if limitation else missing),
        "TC_WORDS": _test_case(100 <= word_count <= 300, "100–300 từ", f"{word_count} từ"),
        "TC_STRUCTURE": _test_case(structure, "Kết luận, bằng chứng, hành động", found if structure else missing),
    }
    return {
        "task_id": "DA03A", "supported": True, "word_count": word_count,
        "total_checks": len(checks), "passed_checks": sum(check["passed"] for check in checks),
        "proposed_level": skills["WRITTEN_COMM"]["level"],
        "passed_all": all(check["passed"] for check in checks if check["weight"] > 0),
        "checks": checks, "skill_results": skills, "test_cases": test_cases,
        "critical": {"CG_WRONG_TREND": wrong_trend},
        "execution": {"executed": False, "error": None},
    }


def verify_submission(task_id: str, submission_text: str, task: dict | None = None, answers: Optional[dict[str, str]] = None) -> dict:
    """Dispatch only known task rubrics; never auto-pass on generic text length."""
    normalized_id = task_id.upper().strip()
    if normalized_id in {"DA01", "DA01A"}:
        return verify_da01a_submission(submission_text, (task or {}).get("dataset_preview", "orders_da01a.csv"), answers)
    if normalized_id == "DA01B":
        return verify_da01b_submission(submission_text, answers)
    if normalized_id in {"DA02", "DA02A"}:
        return verify_da02a_submission(submission_text, answers)
    if normalized_id in {"DA03", "DA03A"}:
        return verify_da03a_submission(submission_text, answers)
    return {
        "task_id": normalized_id,
        "supported": False,
        "total_checks": 0,
        "passed_checks": 0,
        "proposed_level": 0,
        "passed_all": False,
        "checks": [],
        "skill_results": {},
        "notice": "Bài này chưa có bộ tiêu chí xác định đã hiệu chuẩn; không thể tự động cập nhật năng lực.",
    }
