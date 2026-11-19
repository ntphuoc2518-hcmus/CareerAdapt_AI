"""Questions contributed by subject-matter experts (5.35).

An administrator grants the contributor right to an expert's account. The expert writes a question for the
Career Adapt exam (an open task graded by test cases) or for the Kiểm tra kiến thức bank (multiple choice),
then the system checks it mechanically before a person ever reads it:

* the structure (case types, points summing to 100, fields each case needs, safe regular expressions);
* every trusted SQL behind the cases runs on all four datasets;
* the expert's own reference answer scores 100/100 on every dataset with no critical error;
* obviously wrong answers ("SELECT 1", printing the whole table, "I don't know", keyword lists) stay under
  40 points, so the question cannot be passed without solving it;
* no existing or pending question has the same text, and near duplicates are listed for the reviewer.

A submitted question is published only when a reviewer who is not its author approves it. Approved exam
questions go to ``exam_bank_items``; the seed file is never edited. Nothing here writes questions with AI:
the system only checks what a person wrote.

English (5.36): the expert may add an English version of every text a learner reads. It is checked for
completeness and leftover Vietnamese, read by the reviewer, and served from the database once approved.
Without it the question is still valid; English pages then show it in Vietnamese and say so to the author.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import unicodedata
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status

from backend import i18n
from backend.clock import utcnow
from backend.database import dumps
from backend.store import store

BANKS = ("EXAM", "TEST")
OPEN_STATUSES = ("DRAFT", "SUBMITTED", "CHANGES_REQUESTED")
EDITABLE = ("DRAFT", "CHANGES_REQUESTED")
MAX_OPEN_PER_AUTHOR = 30
WEAK_LIMIT = 40  # points; at or above this a wrong answer would already prove a level (PARTIAL_RATIO)
SIMILAR_RATIO = 0.82

CASE_FIELDS = {
    "sql_runs": (), "sql_row_count": ("expected_sql",), "sql_result": ("expected_sql",), "sql_contains": ("expected_sql",),
    "code_regex": ("pattern",), "py_parses": (), "py_runs": (), "py_calls": (),
    "text_number": ("expected_sql",), "text_numbers_all": ("expected_sql",), "text_number_near": ("expected_sql", "labels"),
    "text_pairs": ("expected_sql",), "text_ids": ("expected_sql", "allowed_sql"), "text_regex": ("patterns", "min_matches"),
    "text_trend": ("expected_sql",), "text_percent": ("expected_sql",), "text_sentences": ("min",),
}
TYPES_BY_ANSWER = {
    "sql": {"sql_runs", "sql_row_count", "sql_result", "sql_contains", "code_regex"},
    "python": {"py_parses", "py_runs", "py_calls", "code_regex", "text_number", "text_numbers_all", "text_pairs", "text_percent", "text_number_near"},
    "text": {"text_number", "text_numbers_all", "text_number_near", "text_pairs", "text_ids", "text_regex", "text_trend", "text_percent", "text_sentences"},
}
WORKSPACES_BY_ANSWER = {"sql": {"sql"}, "python": {"python"}, "text": {"report", "data_quality", "visualization"}}
GATE_FIELDS = {"sql_equals": ("wrong_sql",), "sql_contains_all": ("wrong_sql", "right_sql"), "trend_opposite": ("case_id",)}
WEAK_ANSWERS = {
    "sql": [("Truy vấn không liên quan", "SELECT 1;"), ("Lấy toàn bộ bảng", "SELECT * FROM orders_raw;")],
    "python": [("In một dòng chữ", "print('xin chao')"), ("In toàn bộ bảng dữ liệu", "import pandas as pd\ndf = pd.read_csv('orders.csv')\nprint(df)")],
    "text": [("Không biết", "Em chưa rõ nội dung này nên trả lời đại."),
             ("Liệt kê từ khóa", "Kết luận: dữ liệu cho thấy doanh thu, khách hàng, xu hướng tăng, đơn trùng lặp và giá trị thiếu. "
                                  "Khuyến nghị: bộ phận phân tích cần kiểm tra lại số liệu trong tuần tới và báo cáo trưởng nhóm.")],
}
# Nested quantifiers such as (a+)+ can take exponential time on a crafted answer.
NESTED_QUANTIFIER = re.compile(r"\([^()]*[+*][^()]*\)[+*{]")


# A text with no accent mark and no d-bar reads the same in English (numbers, code, SQL keywords), so it needs no translation.
_MARKS = re.compile(r"[\u0300-\u036f\u0111\u0110]")


def _has_vietnamese(text: str) -> bool:
    return bool(_MARKS.search(unicodedata.normalize("NFD", text)))
MAX_ENGLISH_FIELDS = 80
# What only a person can judge. The reviewer confirms each point before approving; it is stored with the decision.
REVIEW_CHECKLIST = (
    ("correct", "Tôi đã tự giải câu này: nội dung và đáp án mẫu đúng chuyên môn."),
    ("clear", "Đề rõ ràng, đủ dữ kiện và chỉ có một cách hiểu."),
    ("level", "Độ khó khớp mức đã chọn cho kỹ năng này."),
    ("safe", "Đề không lộ đáp án, không chứa thông tin cá nhân hay nội dung không phù hợp."),
)
ENGLISH_CHECK = ("english", "Bản tiếng Anh cùng nghĩa với bản tiếng Việt và không lộ thêm gợi ý.")


def _now() -> str:
    return utcnow().isoformat()


def _key(user_id: Any) -> str:
    return str(user_id)


# ---------------------------------------------------------------------------
# Who may contribute
# ---------------------------------------------------------------------------

def is_contributor(user_id: Any) -> bool:
    return store.db.one("SELECT 1 AS yes FROM contributors WHERE user_id = ?", (_key(user_id),)) is not None


def can_contribute(user) -> bool:
    return user.role == "admin" or is_contributor(user.user_id)


def require_contributor(user) -> None:
    if not can_contribute(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản chưa được cấp quyền đóng góp câu hỏi. Hãy liên hệ quản trị viên.")


def grant(user_id: str, email: Optional[str], full_name: Optional[str], admin, note: str = "") -> dict:
    store.db.execute(
        "INSERT INTO contributors(user_id, email, full_name, granted_by, granted_at, note) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET email = excluded.email, full_name = excluded.full_name, note = excluded.note",
        (user_id, email, full_name, admin.email, _now(), note or None),
    )
    return store.db.one("SELECT * FROM contributors WHERE user_id = ?", (user_id,))


def revoke(user_id: str) -> bool:
    return store.db.execute("DELETE FROM contributors WHERE user_id = ?", (user_id,)).rowcount > 0


def list_contributors() -> list[dict]:
    rows = store.db.query("SELECT * FROM contributors ORDER BY granted_at DESC")
    counts = {row["author_id"]: row for row in store.db.query(
        "SELECT author_id, COUNT(*) AS total, SUM(status = 'APPROVED') AS approved, SUM(status = 'SUBMITTED') AS waiting FROM question_contributions GROUP BY author_id")}
    return [{**row, "total": (counts.get(row["user_id"]) or {}).get("total", 0), "approved": (counts.get(row["user_id"]) or {}).get("approved") or 0,
             "waiting": (counts.get(row["user_id"]) or {}).get("waiting") or 0} for row in rows]


# ---------------------------------------------------------------------------
# Banks as they are now
# ---------------------------------------------------------------------------

def contributed_exam_items(include_retired: bool = False) -> list[dict]:
    sql = "SELECT * FROM exam_bank_items" + ("" if include_retired else " WHERE status = 'ACTIVE'") + " ORDER BY approved_at"
    return [{**json.loads(row["payload"]), "item_id": row["item_id"], "skill_code": row["skill_code"], "tier": row["tier"], "author_id": row["author_id"],
             "status": row["status"], "contribution_id": row["contribution_id"]} for row in store.db.query(sql)]


def coverage() -> dict:
    """How many active questions each skill × level holds, so experts see where questions are missing."""
    from backend.engine.exam_grader import BANK

    exam: dict[str, dict[int, int]] = {}
    for item in [*BANK["items"], *contributed_exam_items()]:
        exam.setdefault(item["skill_code"], {1: 0, 2: 0, 3: 0})[int(item["tier"])] += 1
    test: dict[str, dict[int, int]] = {}
    for item in store.question_items:
        if item.get("status", "ACTIVE") == "ACTIVE":
            test.setdefault(item["skill_code"], {1: 0, 2: 0, 3: 0})[int(item["level"])] += 1
    return {"exam": exam, "test": test}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _text_of(bank: str, payload: dict) -> str:
    return payload.get("prompt" if bank == "EXAM" else "stem") or ""


def fingerprint(bank: str, payload: dict) -> str:
    from backend.engine.skill_report import normalize

    text = re.sub(r"\s+", " ", normalize(_text_of(bank, payload))).strip()
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _similar(bank: str, payload: dict, own_id: Optional[str]) -> list[dict]:
    """Questions in either bank, published or pending, whose text is the same or close."""
    from backend.engine.exam_grader import BANK
    from backend.engine.skill_report import normalize

    mine = normalize(_text_of(bank, payload))[:800]
    if len(mine) < 20:
        return []
    others = [("Đề thi (gốc)", item["item_id"], item["prompt"]) for item in BANK["items"]]
    others += [("Đề thi (đóng góp)", item["item_id"], item.get("prompt", "")) for item in contributed_exam_items(include_retired=True)]
    others += [("Trắc nghiệm", item["item_id"], item.get("stem", "")) for item in store.question_items]
    for row in store.db.query("SELECT contribution_id, bank, payload FROM question_contributions WHERE status NOT IN ('REJECTED') AND published_item_id IS NULL"):
        if row["contribution_id"] != own_id:
            others.append(("Câu đang chờ", row["contribution_id"][:8], _text_of(row["bank"], json.loads(row["payload"]))))
    found = []
    for source, ref, text in others:
        theirs = normalize(text)[:800]
        matcher = difflib.SequenceMatcher(None, mine, theirs, autojunk=False)
        if matcher.real_quick_ratio() < SIMILAR_RATIO or matcher.quick_ratio() < SIMILAR_RATIO:
            continue
        ratio = matcher.ratio()
        if ratio >= SIMILAR_RATIO:
            found.append({"source": source, "ref": ref, "similarity": round(ratio, 3), "excerpt": text[:160]})
    return sorted(found, key=lambda item: -item["similarity"])[:5]


def _regex_problem(pattern: Any) -> Optional[str]:
    if not isinstance(pattern, str) or not pattern or len(pattern) > 200:
        return "mẫu tìm kiếm phải là chuỗi 1-200 ký tự"
    if NESTED_QUANTIFIER.search(pattern):
        return "mẫu tìm kiếm có lượng từ lồng nhau (dễ làm treo bộ chấm)"
    try:
        re.compile(pattern)
    except re.error as error:
        return f"mẫu tìm kiếm không hợp lệ ({error})"
    return None


def _exam_structure(skill_code: str, level: int, payload: dict) -> list[str]:
    from backend.engine.exam_grader import BANK

    errors = []
    if skill_code not in {item["skill_code"] for item in BANK["items"]}:
        errors.append("Kỹ năng này chưa có trong đề thi Career Adapt.")
    answer_type = payload.get("answer_type")
    if answer_type not in TYPES_BY_ANSWER:
        return errors + ["Dạng trả lời phải là sql, python hoặc text."]
    if payload.get("workspace") not in WORKSPACES_BY_ANSWER[answer_type]:
        errors.append(f"Không gian làm bài phải là một trong: {', '.join(sorted(WORKSPACES_BY_ANSWER[answer_type]))}.")
    for field, low, high in (("topic", 3, 80), ("prompt", 30, 3000)):
        value = payload.get(field)
        if not isinstance(value, str) or not low <= len(value.strip()) <= high:
            errors.append(f"Trường {field} cần {low}-{high} ký tự.")
    if not isinstance(payload.get("minutes"), int) or not 3 <= payload["minutes"] <= 40:
        errors.append("Thời gian làm bài (minutes) phải là số nguyên 3-40.")
    if not isinstance(payload.get("max_chars"), int) or not 300 <= payload["max_chars"] <= 8000:
        errors.append("Độ dài tối đa (max_chars) phải là số nguyên 300-8000.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 10:
        return errors + ["Cần 1-10 tiêu chí chấm (cases)."]
    ids = []
    for index, case in enumerate(cases, start=1):
        where = f"Tiêu chí {index}"
        if not isinstance(case, dict):
            errors.append(f"{where}: phải là một đối tượng JSON.")
            continue
        case_id, kind = case.get("id"), case.get("type")
        ids.append(case_id)
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9_]{1,20}", case_id):
            errors.append(f"{where}: id chỉ gồm chữ thường, số, gạch dưới (1-20 ký tự).")
        if kind not in TYPES_BY_ANSWER[answer_type]:
            errors.append(f"{where}: loại {kind!r} không dùng cho bài {answer_type}.")
            continue
        if not isinstance(case.get("points"), int) or case["points"] <= 0:
            errors.append(f"{where}: points phải là số nguyên dương.")
        if not isinstance(case.get("description"), str) or not 5 <= len(case["description"].strip()) <= 160:
            errors.append(f"{where}: cần mô tả 5-160 ký tự (người học sẽ đọc mô tả này).")
        for field in CASE_FIELDS[kind]:
            if case.get(field) in (None, "", []):
                errors.append(f"{where}: loại {kind} cần trường {field}.")
        if kind == "code_regex" and case.get("pattern") is not None:
            problem = _regex_problem(case["pattern"])
            if problem:
                errors.append(f"{where}: {problem}.")
        if kind == "text_regex":
            patterns = case.get("patterns") or []
            if not isinstance(patterns, list) or not 1 <= len(patterns) <= 8:
                errors.append(f"{where}: patterns phải là danh sách 1-8 mẫu.")
            for pattern in [*(patterns if isinstance(patterns, list) else []), *(case.get("forbid") or [])]:
                problem = _regex_problem(pattern)
                if problem:
                    errors.append(f"{where}: {problem}.")
            if not isinstance(case.get("min_matches"), int) or not 1 <= case["min_matches"] <= max(1, len(patterns) if isinstance(patterns, list) else 1):
                errors.append(f"{where}: min_matches phải từ 1 đến số mẫu.")
        if kind == "py_calls" and not (case.get("all") or case.get("any")):
            errors.append(f"{where}: py_calls cần danh sách all hoặc any.")
        if answer_type == "python" and kind.startswith("text_") and case.get("section") != "output":
            errors.append(f"{where}: với bài Python, kết quả phải đọc từ phần in ra (section = \"output\").")
    if len(set(ids)) != len(ids):
        errors.append("Các tiêu chí phải có id khác nhau.")
    if all(isinstance(case, dict) and isinstance(case.get("points"), int) for case in cases) and sum(case["points"] for case in cases) != 100:
        errors.append("Tổng điểm các tiêu chí phải bằng 100.")
    from backend.engine.exam_grader import FOUNDATION_CASES

    if all(isinstance(case, dict) and case.get("type") in FOUNDATION_CASES for case in cases):
        errors.append("Cần ít nhất một tiêu chí kiểm tra yêu cầu của đề, không chỉ \"chạy được\".")
    for index, gate in enumerate(payload.get("gates") or [], start=1):
        if not isinstance(gate, dict) or gate.get("type") not in GATE_FIELDS:
            errors.append(f"Lỗi trọng yếu {index}: loại phải là {', '.join(GATE_FIELDS)}.")
            continue
        if not re.fullmatch(r"CG_[A-Z0-9_]{2,40}", str(gate.get("gate_id", ""))) or not str(gate.get("label", "")).strip():
            errors.append(f"Lỗi trọng yếu {index}: cần gate_id dạng CG_... và nhãn.")
        for field in GATE_FIELDS[gate["type"]]:
            if not gate.get(field):
                errors.append(f"Lỗi trọng yếu {index}: cần trường {field}.")
        if gate["type"] == "sql_equals" and "result" not in ids:
            errors.append(f"Lỗi trọng yếu {index}: loại sql_equals cần một tiêu chí có id \"result\".")
    references = payload.get("reference_answers")
    if not isinstance(references, dict) or not references:
        errors.append("Cần đáp án mẫu của chuyên gia (reference_answers).")
    elif answer_type == "text":
        missing = [variant for variant in BANK["datasets"] if not str(references.get(variant, "")).strip()]
        if missing:
            errors.append(f"Bài viết cần đáp án mẫu cho từng bộ dữ liệu; còn thiếu: {', '.join(missing)}.")
    elif not str(references.get("*", "")).strip():
        errors.append("Bài code cần một đáp án mẫu (reference_answers[\"*\"]) dùng cho cả bốn bộ dữ liệu.")
    return errors


# ---------------------------------------------------------------------------
# English version (5.36)
# ---------------------------------------------------------------------------

def english_fields(bank: str, payload: dict) -> list[dict]:
    """Every text a learner reads, keyed the way ``payload["en"]`` stores its English."""
    fields: list[tuple[str, str, Any]] = [("topic", "Chủ đề", payload.get("topic"))]
    if bank == "EXAM":
        fields += [("prompt", "Đề bài", payload.get("prompt")), ("placeholder", "Gợi ý trong ô trả lời", payload.get("placeholder"))]
        fields += [(f"cases.{case.get('id')}", f"Tiêu chí {case.get('id')}", case.get("description")) for case in payload.get("cases") or [] if isinstance(case, dict)]
        fields += [(f"gates.{gate.get('gate_id')}", f"Lỗi trọng yếu {gate.get('gate_id')}", gate.get("label")) for gate in payload.get("gates") or [] if isinstance(gate, dict)]
        fields += [(f"report_sections.{index}", f"Mục báo cáo {index + 1}", section) for index, section in enumerate(payload.get("report_sections") or [])]
    else:
        fields += [("stem", "Câu hỏi", payload.get("stem"))]
        fields += [(f"options.{option.get('id')}", f"Lựa chọn {option.get('id')}", option.get("text")) for option in payload.get("options") or [] if isinstance(option, dict)]
        fields += [("unit", "Đơn vị", payload.get("unit")), ("explanation", "Giải thích", payload.get("explanation"))]
    english = payload.get("en") if isinstance(payload.get("en"), dict) else {}
    return [{"key": key, "label": label, "vi": text.strip(), "en": str(english.get(key) or "").strip(), "needed": _has_vietnamese(text)}
            for key, label, text in fields if isinstance(text, str) and text.strip()]


def _english_report(bank: str, payload: dict) -> tuple[list[str], list[str], dict]:
    fields = english_fields(bank, payload)
    english = payload.get("en") if isinstance(payload.get("en"), dict) else {}
    needed = [field for field in fields if field["needed"]]
    given = [field for field in fields if field["en"]]
    summary = {"needed": len(needed), "given": len([field for field in needed if field["en"]]), "complete": False}
    if not any(str(value).strip() for value in english.values()):
        return [], ["Chưa có bản tiếng Anh: người học dùng giao diện tiếng Anh sẽ thấy câu này bằng tiếng Việt."] if needed else [], {**summary, "complete": not needed}
    errors = []
    missing = [field["label"] for field in needed if not field["en"]]
    if missing:
        errors.append("Bản tiếng Anh còn thiếu: " + ", ".join(missing) + ". Dịch đủ hoặc xóa hết để chỉ dùng tiếng Việt.")
    leftover = [field["label"] for field in given if _has_vietnamese(field["en"])]
    if leftover:
        errors.append("Bản tiếng Anh còn chữ tiếng Việt ở: " + ", ".join(leftover) + ".")
    stale = sorted(set(key for key, value in english.items() if str(value).strip()) - {field["key"] for field in fields})
    if stale:
        errors.append("Bản tiếng Anh có mục không còn trong câu (đã đổi mã?): " + ", ".join(stale) + ".")
    too_long = [field["label"] for field in given if len(field["en"]) > 2 * len(field["vi"]) + 200]
    if too_long:
        errors.append("Bản tiếng Anh dài bất thường so với tiếng Việt ở: " + ", ".join(too_long) + ".")
    return errors, [], {**summary, "complete": not errors}


def review_items(bank: str, payload: dict) -> list[dict]:
    items = list(REVIEW_CHECKLIST)
    if any(field["en"] for field in english_fields(bank, payload)):
        items.append(ENGLISH_CHECK)
    return [{"key": key, "label": label} for key, label in items]


def _translation_version() -> Any:
    try:
        row = store.db.one("SELECT COUNT(*) AS n, MAX(updated_at) AS at FROM question_contributions WHERE status IN ('APPROVED', 'RETIRED')")
    except Exception:  # noqa: BLE001 - no database yet: nothing contributed to translate
        return None
    return (row["n"], row["at"]) if row else None


def _published_translations() -> tuple[dict[str, str], dict[str, str]]:
    """English of approved questions (retired ones too: earlier attempts still show them)."""
    exact: dict[str, str] = {}
    phrases: dict[str, str] = {}
    try:
        rows = store.db.query("SELECT bank, payload FROM question_contributions WHERE status IN ('APPROVED', 'RETIRED') ORDER BY decided_at")
    except Exception:  # noqa: BLE001
        return exact, phrases
    for row in rows:
        payload = json.loads(row["payload"])
        for field in english_fields(row["bank"], payload):
            if field["en"]:
                exact[field["vi"]] = field["en"]
                if field["key"] == "topic":
                    # The topic is also quoted inside the verdict sentence.
                    phrases[field["vi"]] = field["en"]
    return exact, phrases


i18n.register_source(_translation_version, _published_translations)


def _exam_question(skill_code: str, level: int, payload: dict, dataset: str) -> dict:
    return {"skill_code": skill_code, "tier": level, "answer_type": payload["answer_type"], "cases": payload["cases"], "gates": payload.get("gates") or [], "dataset": dataset}


def _score(question: dict, answer: str) -> tuple[int, dict, list[str]]:
    from backend.engine.exam_grader import evaluate_question

    outcomes, violated = evaluate_question(question, answer)
    earned = sum(case["points"] for case in question["cases"] if outcomes.get(case["id"], {}).get("passed"))
    return earned, outcomes, violated


def _check_exam(skill_code: str, level: int, payload: dict) -> dict:
    from backend.engine.exam_grader import BANK
    from backend.engine.sql_sandbox import execute_readonly_sql

    report: dict[str, Any] = {"datasets": {}, "weak": [], "errors": [], "warnings": []}
    sqls = [(case["id"], field, case[field]) for case in payload["cases"] for field in ("expected_sql", "allowed_sql") if case.get(field)]
    sqls += [(gate["gate_id"], field, gate[field]) for gate in payload.get("gates") or [] for field in ("wrong_sql", "right_sql") if gate.get(field)]
    for variant, dataset in BANK["datasets"].items():
        for owner, field, sql in sqls:
            run = execute_readonly_sql(sql, dataset)
            if not run.get("executed") or not run.get("result_sets"):
                report["errors"].append(f"Bộ dữ liệu {variant}: SQL {field} của {owner} không chạy được ({run.get('error') or 'không có kết quả'}).")
            elif field == "expected_sql" and not run["result_sets"][-1]["rows"]:
                report["errors"].append(f"Bộ dữ liệu {variant}: SQL {field} của {owner} không trả về dòng nào.")
    if report["errors"]:
        return report
    references = payload["reference_answers"]
    for variant, dataset in BANK["datasets"].items():
        question = _exam_question(skill_code, level, payload, dataset)
        answer = references.get(variant) or references.get("*", "")
        earned, outcomes, violated = _score(question, answer)
        report["datasets"][variant] = {"score": earned, "violated": violated, "cases": [
            {"id": case["id"], "description": case["description"], "passed": bool(outcomes.get(case["id"], {}).get("passed")),
             "expected": str(outcomes.get(case["id"], {}).get("expected_summary", ""))[:200], "actual": str(outcomes.get(case["id"], {}).get("actual_summary", ""))[:200]}
            for case in payload["cases"]]}
        if earned != 100:
            failed = [case["id"] for case in payload["cases"] if not outcomes.get(case["id"], {}).get("passed")]
            report["errors"].append(f"Bộ dữ liệu {variant}: đáp án mẫu chỉ đạt {earned}/100 (trượt: {', '.join(failed)}).")
        if violated:
            report["errors"].append(f"Bộ dữ liệu {variant}: đáp án mẫu phạm lỗi trọng yếu {', '.join(violated)}.")
    first = next(iter(BANK["datasets"].values()))
    for label, answer in WEAK_ANSWERS[payload["answer_type"]]:
        earned, _, _ = _score(_exam_question(skill_code, level, payload, first), answer)
        report["weak"].append({"label": label, "answer": answer, "score": earned})
        if earned >= WEAK_LIMIT:
            report["errors"].append(f"Bài làm sai \"{label}\" vẫn được {earned}/100: tiêu chí quá dễ đạt, hãy kiểm tra yêu cầu của đề.")
    return report


def _test_item(item_id: str, skill_code: str, level: int, payload: dict) -> dict:
    """The multiple-choice item in the bank's own format, checked by the same rules the admin editor uses."""
    from backend.api.test_center import QuestionItemRequest, _validate_item

    body = QuestionItemRequest(item_id=item_id, skill_code=skill_code, level=level, status="ACTIVE",
                               **{key: payload.get(key) for key in ("type", "topic", "stem", "code", "options", "answer", "tolerance", "unit", "explanation") if payload.get(key) is not None})
    return _validate_item(body)


def _check_test(skill_code: str, level: int, payload: dict) -> dict:
    from backend.engine.test_engine import score_item

    report: dict[str, Any] = {"datasets": {}, "weak": [], "errors": [], "warnings": []}
    if len(str(payload.get("explanation") or "").strip()) < 20:
        report["errors"].append("Cần lời giải thích ít nhất 20 ký tự: người học đọc nó sau khi nộp bài.")
    try:
        item = _test_item("C-CHECK", skill_code, level, payload)
    except HTTPException as error:
        report["errors"].append(str(error.detail))
        return report
    except (ValueError, TypeError) as error:
        report["errors"].append(f"Câu hỏi chưa đúng định dạng: {str(error)[:200]}")
        return report
    if score_item(item, item["answer"]) != 1.0:
        report["errors"].append("Đáp án đúng không đạt trọn điểm khi chấm thử.")
    if item["type"] in ("single", "multiple"):
        texts = [option["text"].strip().lower() for option in item["options"]]
        if len(set(texts)) != len(texts):
            report["errors"].append("Hai lựa chọn có nội dung trùng nhau.")
        wrong = [option["id"] for option in item["options"] if option["id"] not in (item["answer"] if isinstance(item["answer"], list) else [item["answer"]])]
        if not wrong:
            report["errors"].append("Cần ít nhất một lựa chọn sai.")
        elif score_item(item, wrong[0] if item["type"] == "single" else [wrong[0]]) > 0:
            report["errors"].append("Chọn một phương án sai vẫn được điểm.")
        if item["type"] == "single" and len(item["options"]) < 3:
            report["warnings"].append("Câu một đáp án chỉ có 2 lựa chọn: đoán đúng 50%.")
    if item["type"] == "ordering" and score_item(item, list(reversed(item["answer"]))) >= 1.0:
        report["errors"].append("Thứ tự đảo ngược vẫn đạt trọn điểm.")
    report["weak"].append({"label": "Bỏ trống", "answer": "", "score": round(100 * score_item(item, None))})
    return report


def validate(bank: str, skill_code: str, level: int, payload: dict, own_id: Optional[str] = None) -> dict:
    """Everything the system can check without a person. ``ok`` is True only when no error was found."""
    errors = _exam_structure(skill_code, level, payload) if bank == "EXAM" else []
    report: dict[str, Any] = {"datasets": {}, "weak": [], "errors": errors, "warnings": []}
    if not errors:
        checked = _check_exam(skill_code, level, payload) if bank == "EXAM" else _check_test(skill_code, level, payload)
        report.update({key: checked[key] for key in ("datasets", "weak", "warnings")})
        report["errors"] = checked["errors"]
    english_errors, english_warnings, report["english"] = _english_report(bank, payload)
    report["errors"] += english_errors
    report["warnings"] += english_warnings
    exact = store.db.one("SELECT contribution_id FROM question_contributions WHERE fingerprint = ? AND status != 'REJECTED' AND contribution_id != ?",
                         (fingerprint(bank, payload), own_id or ""))
    similar = _similar(bank, payload, own_id)
    if exact or any(item["similarity"] >= 0.999 for item in similar):
        report["errors"].append("Đã có câu hỏi trùng nội dung trong ngân hàng hoặc đang chờ duyệt.")
    elif similar:
        report["warnings"].append(f"Có {len(similar)} câu gần giống; người duyệt sẽ so sánh.")
    report.update(similar=similar, ok=not report["errors"], checked_at=_now())
    return report


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def _row(contribution_id: str) -> dict:
    row = store.db.one("SELECT * FROM question_contributions WHERE contribution_id = ?", (contribution_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi đóng góp.")
    return row


def view(row: dict, for_reviewer: bool = False) -> dict:
    events = store.db.query("SELECT actor_id, action, note, created_at FROM contribution_events WHERE contribution_id = ? ORDER BY created_at", (row["contribution_id"],))
    out = {key: row[key] for key in ("contribution_id", "bank", "author_name", "skill_code", "level", "status", "revision", "review_note",
                                     "published_item_id", "created_at", "updated_at", "submitted_at", "decided_at")}
    out.update(payload=json.loads(row["payload"]), validation=json.loads(row["validation"]) if row["validation"] else None,
               events=[{**event, "actor_id": None if not for_reviewer else event["actor_id"]} for event in events], is_mine=False)
    if for_reviewer:
        out["author_id"] = row["author_id"]
        out["review_items"] = review_items(row["bank"], out["payload"])
        out["review_checklist"] = json.loads(row["review_checklist"]) if row.get("review_checklist") else None
    return out


def owned(contribution_id: str, user) -> dict:
    row = _row(contribution_id)
    if row["author_id"] != _key(user.user_id):
        # Someone else's question looks like it does not exist.
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi đóng góp.")
    return row


def _event(contribution_id: str, actor: Any, action: str, note: str = "") -> None:
    store.db.execute("INSERT INTO contribution_events(event_id, contribution_id, actor_id, action, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), contribution_id, _key(actor), action, note or None, _now()))


def _clean_payload(bank: str, payload: dict) -> dict:
    keys = (("topic", "prompt", "answer_type", "workspace", "minutes", "max_chars", "placeholder", "cases", "gates", "report_sections", "reference_answers")
            if bank == "EXAM" else ("type", "topic", "stem", "code", "options", "answer", "tolerance", "unit", "explanation"))
    clean = {key: copy.deepcopy(payload[key]) for key in keys if key in payload}
    english = payload.get("en")
    if english not in (None, {}):
        if (not isinstance(english, dict) or len(english) > MAX_ENGLISH_FIELDS
                or any(not isinstance(key, str) or len(key) > 60 or not isinstance(value, str) or len(value) > 4000 for key, value in english.items())):
            raise HTTPException(status_code=422, detail="Bản tiếng Anh phải là các cặp mục - nội dung (tối đa 80 mục, mỗi mục tối đa 4000 ký tự).")
        trimmed = {key: value.strip() for key, value in english.items() if value.strip()}
        if trimmed:
            clean["en"] = trimmed
    if len(dumps(clean)) > 60_000:
        raise HTTPException(status_code=413, detail="Câu hỏi quá dài.")
    return clean


def create(user, bank: str, skill_code: str, level: int, payload: dict) -> dict:
    require_contributor(user)
    if bank not in BANKS:
        raise HTTPException(status_code=422, detail="Ngân hàng phải là EXAM hoặc TEST.")
    if not store.get_skill(skill_code):
        raise HTTPException(status_code=422, detail="Mã kỹ năng không tồn tại.")
    open_count = store.db.one("SELECT COUNT(*) AS n FROM question_contributions WHERE author_id = ? AND status IN ('DRAFT', 'SUBMITTED', 'CHANGES_REQUESTED')", (_key(user.user_id),))["n"]
    if open_count >= MAX_OPEN_PER_AUTHOR:
        raise HTTPException(status_code=429, detail=f"Bạn đang có {open_count} câu chưa xử lý xong. Hãy hoàn tất hoặc xóa bớt bản nháp trước.")
    clean = _clean_payload(bank, payload)
    contribution_id = str(uuid.uuid4())
    now = _now()
    with store.db.transaction():
        store.db.execute(
            """INSERT INTO question_contributions(contribution_id, bank, author_id, author_name, skill_code, level, status, payload, fingerprint, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?)""",
            (contribution_id, bank, _key(user.user_id), user.full_name, skill_code, level, dumps(clean), fingerprint(bank, clean), now, now),
        )
        _event(contribution_id, user.user_id, "CREATED")
    return view(_row(contribution_id))


def update(user, contribution_id: str, skill_code: str, level: int, payload: dict) -> dict:
    require_contributor(user)
    row = owned(contribution_id, user)
    if row["status"] not in EDITABLE:
        raise HTTPException(status_code=409, detail="Chỉ sửa được bản nháp hoặc câu được yêu cầu chỉnh sửa. Hãy rút lại câu đang chờ duyệt trước.")
    if not store.get_skill(skill_code):
        raise HTTPException(status_code=422, detail="Mã kỹ năng không tồn tại.")
    clean = _clean_payload(row["bank"], payload)
    # An edit invalidates the last check, so the question has to be checked again before it can be sent.
    store.db.execute("UPDATE question_contributions SET skill_code = ?, level = ?, payload = ?, fingerprint = ?, validation = NULL, updated_at = ? WHERE contribution_id = ?",
                     (skill_code, level, dumps(clean), fingerprint(row["bank"], clean), _now(), contribution_id))
    return view(_row(contribution_id))


def _validate_as(user, row) -> dict:
    """The contributor's own check runs the reference answers in the sandbox, so it takes that person's one
    code-run slot like any other run of their code (audit 2026-11-18)."""
    from backend.exam_service import code_run_slot

    if row["bank"] != "EXAM":
        return validate(row["bank"], row["skill_code"], row["level"], json.loads(row["payload"]), row["contribution_id"])
    with code_run_slot(user.user_id, gap=False):
        return validate(row["bank"], row["skill_code"], row["level"], json.loads(row["payload"]), row["contribution_id"])


def run_check(user, contribution_id: str) -> dict:
    require_contributor(user)
    row = owned(contribution_id, user)
    report = _validate_as(user, row)
    store.db.execute("UPDATE question_contributions SET validation = ?, updated_at = ? WHERE contribution_id = ?", (dumps(report), _now(), contribution_id))
    return view(_row(contribution_id))


def submit(user, contribution_id: str) -> dict:
    require_contributor(user)
    row = owned(contribution_id, user)
    if row["status"] not in EDITABLE:
        raise HTTPException(status_code=409, detail="Câu này không ở trạng thái gửi duyệt được.")
    report = _validate_as(user, row)
    now = _now()
    with store.db.transaction():
        if not report["ok"]:
            store.db.execute("UPDATE question_contributions SET validation = ?, updated_at = ? WHERE contribution_id = ?", (dumps(report), now, contribution_id))
        else:
            store.db.execute("UPDATE question_contributions SET status = 'SUBMITTED', validation = ?, revision = revision + 1, submitted_at = ?, updated_at = ? WHERE contribution_id = ?",
                             (dumps(report), now, now, contribution_id))
            _event(contribution_id, user.user_id, "SUBMITTED")
    if not report["ok"]:
        raise HTTPException(status_code=422, detail="Câu hỏi chưa qua bước kiểm tra tự động: " + " ".join(report["errors"][:3]))
    return view(_row(contribution_id))


def withdraw(user, contribution_id: str) -> dict:
    row = owned(contribution_id, user)
    if row["status"] != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Chỉ rút lại được câu đang chờ duyệt.")
    with store.db.transaction():
        store.db.execute("UPDATE question_contributions SET status = 'DRAFT', updated_at = ? WHERE contribution_id = ?", (_now(), contribution_id))
        _event(contribution_id, user.user_id, "WITHDRAWN")
    return view(_row(contribution_id))


def delete(user, contribution_id: str) -> None:
    row = owned(contribution_id, user)
    if row["status"] not in ("DRAFT", "CHANGES_REQUESTED", "REJECTED"):
        raise HTTPException(status_code=409, detail="Không xóa được câu đang chờ duyệt hoặc đã xuất bản.")
    store.db.execute("DELETE FROM question_contributions WHERE contribution_id = ?", (contribution_id,))


def mine(user) -> list[dict]:
    rows = store.db.query("SELECT * FROM question_contributions WHERE author_id = ? ORDER BY updated_at DESC", (_key(user.user_id),))
    return [{**view(row), "is_mine": True} for row in rows]


# ---------------------------------------------------------------------------
# Review and publishing
# ---------------------------------------------------------------------------

def queue(status_filter: Optional[str]) -> list[dict]:
    if status_filter:
        rows = store.db.query("SELECT * FROM question_contributions WHERE status = ? ORDER BY COALESCE(submitted_at, updated_at)", (status_filter,))
    else:
        rows = store.db.query("SELECT * FROM question_contributions WHERE status != 'DRAFT' ORDER BY COALESCE(submitted_at, updated_at) DESC")
    return [view(row, for_reviewer=True) for row in rows]


def decide(admin, contribution_id: str, decision: str, note: str, checklist: Optional[dict] = None) -> dict:
    row = _row(contribution_id)
    if row["status"] != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Câu này không chờ duyệt.")
    if row["author_id"] == _key(admin.user_id):
        # Four eyes: nobody approves or rejects their own question.
        raise HTTPException(status_code=403, detail="Người viết không tự duyệt câu của mình. Hãy nhờ một quản trị viên khác.")
    if decision in ("REQUEST_CHANGES", "REJECT") and len(note.strip()) < 10:
        raise HTTPException(status_code=422, detail="Hãy ghi lý do (ít nhất 10 ký tự) để người viết biết cần sửa gì.")
    now = _now()
    if decision != "APPROVE":
        new_status = "CHANGES_REQUESTED" if decision == "REQUEST_CHANGES" else "REJECTED"
        with store.db.transaction():
            store.db.execute("UPDATE question_contributions SET status = ?, review_note = ?, reviewer_id = ?, decided_at = ?, updated_at = ? WHERE contribution_id = ?",
                             (new_status, note.strip(), _key(admin.user_id), now, now, contribution_id))
            _event(contribution_id, admin.user_id, new_status, note.strip())
        return view(_row(contribution_id), for_reviewer=True)
    payload = json.loads(row["payload"])
    items = review_items(row["bank"], payload)
    unconfirmed = [item["label"] for item in items if (checklist or {}).get(item["key"]) is not True]
    if unconfirmed:
        # The automatic check proves the reference answer passes the cases; whether the question is right is a person's call.
        raise HTTPException(status_code=422, detail="Hãy xác nhận đủ các mục kiểm tra của người duyệt trước khi xuất bản: " + " ".join(unconfirmed))
    confirmed = dumps({"items": [item["key"] for item in items], "confirmed_at": now, "reviewer_id": _key(admin.user_id)})
    # Checked again at approval: the bank may have changed since it was submitted.
    report = validate(row["bank"], row["skill_code"], row["level"], payload, contribution_id)
    if not report["ok"]:
        store.db.execute("UPDATE question_contributions SET validation = ? WHERE contribution_id = ?", (dumps(report), contribution_id))
        raise HTTPException(status_code=422, detail="Câu hỏi không còn qua kiểm tra tự động: " + " ".join(report["errors"][:3]))
    item_id = f"C-{row['skill_code']}-{row['level']}-{uuid.uuid4().hex[:6].upper()}"
    with store.db.transaction():
        if row["bank"] == "EXAM":
            published = {key: payload[key] for key in ("topic", "prompt", "answer_type", "workspace", "minutes", "max_chars", "cases") if key in payload}
            published.update(placeholder=payload.get("placeholder", ""), gates=payload.get("gates") or [], report_sections=payload.get("report_sections") or [])
            store.db.execute("""INSERT INTO exam_bank_items(item_id, contribution_id, skill_code, tier, status, author_id, payload, approved_by, approved_at)
                                VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)""",
                             (item_id, contribution_id, row["skill_code"], row["level"], row["author_id"], dumps(published), admin.email, now))
        else:
            item = _test_item(item_id, row["skill_code"], row["level"], payload)
            store.save_question_item({**item, "author_id": row["author_id"], "contribution_id": contribution_id})
        store.db.execute("""UPDATE question_contributions SET status = 'APPROVED', validation = ?, review_note = ?, reviewer_id = ?, published_item_id = ?,
                            review_checklist = ?, decided_at = ?, updated_at = ? WHERE contribution_id = ?""",
                         (dumps(report), note.strip() or None, _key(admin.user_id), item_id, confirmed, now, now, contribution_id))
        _event(contribution_id, admin.user_id, "APPROVED", note.strip())
    store._bump("content")
    return view(_row(contribution_id), for_reviewer=True)


def retire(admin, contribution_id: str, note: str) -> dict:
    """Take a published question out of new exams and tests. Attempts that already used it keep it."""
    row = _row(contribution_id)
    if row["status"] != "APPROVED" or not row["published_item_id"]:
        raise HTTPException(status_code=409, detail="Chỉ ngừng dùng được câu đã xuất bản.")
    now = _now()
    with store.db.transaction():
        if row["bank"] == "EXAM":
            store.db.execute("UPDATE exam_bank_items SET status = 'RETIRED', retired_at = ? WHERE item_id = ?", (now, row["published_item_id"]))
        else:
            item = store.get_question_item(row["published_item_id"])
            if item:
                store.save_question_item({**item, "status": "RETIRED"})
        store.db.execute("UPDATE question_contributions SET status = 'RETIRED', updated_at = ? WHERE contribution_id = ?", (now, contribution_id))
        _event(contribution_id, admin.user_id, "RETIRED", note.strip())
    store._bump("content")
    return view(_row(contribution_id), for_reviewer=True)
