"""Item bank and per-question verifiers for the Career Adapt exam.

Reuses the V4 parts: the SQL sandbox, the static Python analysis and the number reading. Expected
values are computed from the question's dataset by trusted SQL, so a variant on another dataset has
its own answers and the bank holds no answer key. The output has the shape the rule engine expects,
so points, thresholds and critical gates are still decided by ``rubric_engine``.
"""
from __future__ import annotations

import json
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from backend import assessment_policy as policy
from backend.engine.deterministic_grader import _mentions_amount, _numbers_in, _python_calls, _python_tree, _test_case, _value_near_label
from backend.engine.python_sandbox import run_python
from backend.engine.skill_report import normalize
from backend.engine.sql_sandbox import execute_readonly_sql

BANK: dict[str, Any] = json.loads((Path(__file__).resolve().parents[2] / "data" / "exam_items_v5.json").read_text(encoding="utf-8"))
BANK_VERSION: str = BANK["bank_version"]
PASS_THRESHOLD = float(BANK["pass_threshold"])
TIER_LABELS = {1: "Cơ bản", 2: "Trung bình", 3: "Khó"}
WORKSPACES = {"sql", "python", "report", "data_quality", "visualization"}
PASS_RATIO = policy.QUESTION_PASS_RATIO
PARTIAL_RATIO = policy.QUESTION_PARTIAL_RATIO
# A concept counts only inside a sentence that explains something, not as a bare keyword (audit A-02):
# once every concept of the check is taken out, the sentence must still say something.
MIN_CONTEXT_WORDS = 3
SENTENCE_BREAK = re.compile(r"[.!?\n]+")
# Keyword stuffing (audit 2026-11-17). Words that only pad a sentence are not the learner's own explanation:
# a run of PADDING_NGRAM words copied from the question, or repeated in two sentences of the answer, is
# padding (PROMPT_NGRAM words for the question, which a short answer naturally echoes). A sentence naming
# LIST_MIN_CONCEPTS concepts or more with fewer own words than concepts is a keyword list. Neither counts.
PADDING_NGRAM = 4
PROMPT_NGRAM = 5
LIST_MIN_CONCEPTS = 3
# Cases that check data the learner had to compute. A written answer with none of them right shows no
# analysis, so it cannot prove more than level 1 however many concepts it names (audit A-02).
SUBSTANCE_CASES = {"text_number", "text_numbers_all", "text_number_near", "text_pairs", "text_percent", "text_ids", "sql_result", "sql_contains", "py_runs"}
# Audit 2026-11-15. "It runs" is not evidence of the skill: these cases count only beside a passed case that
# checks what the question asked for. Before, `SELECT 1` or `print("hi")` earned 15-20 points.
FOUNDATION_CASES = {"sql_runs", "py_parses", "py_runs"}
# A figure printed by code counts only on a result line. A row of a printed table holds many numbers, so
# dumping the data (print(df)) no longer "contains" the expected answer by accident.
MAX_NUMBERS_ON_RESULT_LINE = 4
# A written answer that only says the learner does not know proves nothing, whatever words it happens to hold.
NON_ANSWER = re.compile(r"chua ro|khong ro|khong biet|khong hieu|chua biet|chua hieu|tra loi dai|khong tra loi duoc|bo qua cau|i do ?n.?t know|no idea|not sure")
NON_ANSWER_MAX_WORDS = 30
FALLING = re.compile(r"\bgiam\b|sut giam|decreas|declin|\bdrop|\bfell\b|\bfall(en|s)?\b")
RISING = re.compile(r"\btang\b|increas|\bgrew\b|growth|\brose\b|\brisen?\b")


def tier_for_level(level: Optional[int]) -> int:
    """Declared level to difficulty. Kept for older callers; the exam uses ``tier_for_target``."""
    return {2: 2, 3: 3}.get(level if level is not None else 0, 1)


def tier_for_target(target_level: Optional[int]) -> int:
    """The JD's required level sets the difficulty, so every learner can prove the level the JD asks for.

    The self-declared level is never used here: it is not evidence, and letting it choose an easier
    question capped learners who under-declared below the JD level however well they answered.
    """
    return min(max(int(target_level or 1), 1), 3)


def verified_level(tier: int, ratio: float, blank: bool, critical: bool) -> int:
    """The level a question can prove: an easy question never proves more than level 1.

    Passing proves the tier. A partial answer proves one level below it. On the hard tier any
    correct part still proves level 1, because failing a hard question does not show the basics
    are missing. A blank answer proves nothing, and a critical error keeps the skill at 1 or below.
    """
    if blank:
        return 0
    if ratio >= PASS_RATIO:
        level = tier
    elif ratio >= PARTIAL_RATIO:
        level = tier - 1
    else:
        level = max(tier - 2, 0) if ratio > 0 else 0
    return min(level, 1) if critical else level


def validate_bank() -> list[str]:
    problems = []
    for item in BANK["items"]:
        if sum(case["points"] for case in item["cases"]) != 100:
            problems.append(f"{item['item_id']}: tổng điểm khác 100.")
    if PASS_THRESHOLD != policy.EXAM_PASS_SCORE:
        problems.append(f"Ngưỡng đạt của ngân hàng ({PASS_THRESHOLD:g}) khác chính sách đánh giá ({policy.EXAM_PASS_SCORE:g}).")
    cells = {(item["skill_code"], item["tier"]) for item in BANK["items"]}
    for item in BANK["items"]:
        if item.get("workspace") not in WORKSPACES:
            problems.append(f"{item['item_id']}: thiếu loại không gian làm bài.")
    for skill in {item["skill_code"] for item in BANK["items"]}:
        for tier in TIER_LABELS:
            if (skill, tier) not in cells:
                problems.append(f"{skill}: thiếu câu độ khó {tier}.")
    return problems


def exam_items() -> list[dict]:
    """The seed bank plus every contributed question an administrator approved and has not retired (5.35)."""
    from backend.contributions import contributed_exam_items

    return [*BANK["items"], *contributed_exam_items()]


def plan_questions(requirements: dict[str, dict], declared: dict[str, int], seen: set[str], seed: int, author_id: Optional[str] = None) -> list[dict]:
    """One question per skill the JD weighs, so the count follows the JD and never repeats a topic.

    Difficulty follows the level the JD requires (``tier_for_target``), never the declared level.
    Heavier skills come first. When a skill × level has several approved questions, one is drawn at random,
    preferring a question the learner has not met, then a dataset variant they have not met. A contributor
    never gets a question they wrote.
    """
    rng = random.Random(seed)
    items = [entry for entry in exam_items() if not author_id or entry.get("author_id") != author_id]
    measured = sorted(
        ((code, item) for code, item in requirements.items() if float(item.get("weight", 0)) > 0 and any(entry["skill_code"] == code for entry in items)),
        key=lambda pair: (-float(pair[1]["weight"]), pair[0]),
    )
    total = sum(float(item["weight"]) for _, item in measured)
    questions = []
    for index, (code, requirement) in enumerate(measured, start=1):
        tier = tier_for_target(requirement.get("target_level"))
        candidates = [entry for entry in items if entry["skill_code"] == code and entry["tier"] == tier]
        seen_items = {key.rsplit("-", 1)[0] for key in seen}
        combos = [(entry, variant, dataset) for entry in candidates for variant, dataset in BANK["datasets"].items()]
        rng.shuffle(combos)
        combos.sort(key=lambda combo: (combo[0]["item_id"] in seen_items, f"{combo[0]['item_id']}-{combo[1]}" in seen))
        item, variant, dataset = combos[0]
        questions.append({
            **{key: item[key] for key in ("skill_code", "tier", "topic", "prompt", "answer_type", "workspace", "minutes", "max_chars", "cases")},
            "report_sections": item.get("report_sections", []),
            "question_id": f"Q{index}", "label": f"Bài {index}", "item_id": f"{item['item_id']}-{variant}", "dataset": dataset, "gates": item.get("gates", []),
            "placeholder": item.get("placeholder", ""), "declared_level": declared.get(code), "weight": float(requirement["weight"]) / total, "target_level": int(requirement.get("target_level", 1)),
        })
    return questions


def build_blueprint(questions: list[dict]) -> dict:
    """A one-off blueprint for ``score_submission``: one criterion per question, summing to 100."""
    criteria, test_cases, gates = [], [], {}
    remaining = 100.0
    for position, question in enumerate(questions):
        share = remaining if position == len(questions) - 1 else round(question["weight"] * 100, 2)
        remaining = round(remaining - share, 2)
        criteria.append({"criterion_id": question["question_id"], "label": f"{question['label']}: {question['topic']}", "max_points": share, "skill_code": question["skill_code"], "question_ids": [question["question_id"]]})
        left = share
        for index, case in enumerate(question["cases"]):
            points = left if index == len(question["cases"]) - 1 else round(share * case["points"] / 100, 2)
            left = round(left - points, 2)
            test_cases.append({"test_case_id": f"{question['question_id']}.{case['id']}", "criterion_id": question["question_id"], "question_id": question["question_id"], "description": case["description"], "points": points})
        for gate in question["gates"]:
            gates.setdefault(gate["gate_id"], {"gate_id": gate["gate_id"], "label": gate["label"]})
    return {
        "rubric_version": BANK_VERSION, "pass_threshold": PASS_THRESHOLD, "support_policy": {}, "required_outputs": [],
        "scope_note": "Kết quả chỉ phản ánh các câu đã làm ở độ khó được giao trong bài kiểm tra này, không phải chứng chỉ nghề.",
        "questions": [{key: question[key] for key in ("question_id", "label", "prompt", "answer_type", "max_chars")} for question in questions],
        "criteria": criteria, "test_cases": test_cases, "critical_gates": list(gates.values()),
    }


@lru_cache(maxsize=256)
def _trusted_rows(sql: str, dataset: str) -> str:
    execution = execute_readonly_sql(sql, dataset)
    if not execution.get("executed") or execution.get("error"):
        raise ValueError(f"Câu truy vấn tham chiếu lỗi: {execution.get('error')}")
    return json.dumps(execution["result_sets"][-1]["rows"], ensure_ascii=False)


def expected_rows(sql: str, dataset: str) -> list[list[Any]]:
    return json.loads(_trusted_rows(sql, dataset))


def _last_rows(execution: dict) -> list[list[Any]]:
    filled = [result.get("rows", []) for result in execution.get("result_sets", []) if result.get("rows")]
    return filled[-1] if filled else []


def _cell_equal(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return abs(float(actual) - float(expected)) <= max(0.02, abs(float(expected)) * 0.0005)
        except (TypeError, ValueError):
            return False
    return normalize(str(expected or "")).strip() == normalize(str(actual or "")).strip()


def _row_contains(actual: list[Any], expected: list[Any]) -> bool:
    """Every expected cell appears in the row, in any column order; extra columns are fine."""
    free = list(actual)
    for cell in expected:
        match = next((index for index, value in enumerate(free) if _cell_equal(cell, value)), None)
        if match is None:
            return False
        free.pop(match)
    return True


def _rows_match(actual: list[list[Any]], expected: list[list[Any]], exact_count: bool = True) -> bool:
    if exact_count and len(actual) != len(expected):
        return False
    free = list(actual)
    for row in expected:
        match = next((index for index, candidate in enumerate(free) if _row_contains(candidate, row)), None)
        if match is None:
            return False
        free.pop(match)
    return True


RUN_FAILURES = {"SYNTAX_ERROR": "Code sai cú pháp nên chưa chạy.", "BLOCKED": "Code dùng thao tác không được phép nên chưa chạy.", "RUNTIME_ERROR": "Code chạy bị lỗi.", "TIMEOUT": "Code chạy quá thời gian.", "RESOURCE_LIMIT": "Code vượt giới hạn tài nguyên."}


def _execute(question: dict, answer: str) -> dict:
    """The real run of a Python answer. A sandbox that cannot start must not cost the learner marks."""
    if question["answer_type"] != "python" or not answer.strip():
        return {"status": "NOT_RUN", "output_text": ""}
    result = run_python(answer, question["dataset"])
    if result["status"] == "UNAVAILABLE":
        raise RuntimeError("Python sandbox unavailable")
    return result


def _mentions(text: str, value: float, exact: bool) -> bool:
    return any(abs(number - value) < 0.5 for number in _numbers_in(text)) if exact else _mentions_amount(text, value)


def _number_near_label(text: str, labels: list[str], value: float) -> bool:
    normalized = normalize(text)
    for label in labels:
        for match in re.finditer(re.escape(label), normalized):
            window = normalized[max(0, match.start() - 28): match.end() + 42]
            if any(number == value for number in _numbers_in(window)):
                return True
    return False


def _trend(text: str) -> tuple[bool, bool]:
    normalized = normalize(text)
    return bool(RISING.search(normalized)), bool(FALLING.search(normalized))


def _percent_ok(text: str, value: float) -> bool:
    rising, falling = _trend(text)
    numbers = _numbers_in(text)
    if any(abs(number - value) <= 0.06 for number in numbers):
        return True
    if any(abs(number - abs(value)) <= 0.06 for number in numbers):
        return (value < 0 and falling and not rising) or (value > 0 and rising and not falling)
    return False


def evaluate_question(question: dict, answer: str) -> tuple[dict[str, dict], list[str]]:
    """Run a question's cases. Returns {case id: outcome} and the critical gates it violated."""
    dataset = question["dataset"]
    code = question["answer_type"] in {"sql", "python"}
    execution = execute_readonly_sql(answer, dataset) if question["answer_type"] == "sql" and answer.strip() else {"executed": False, "result_sets": [], "error": None}
    rows = _last_rows(execution)
    tree = _python_tree(answer) if question["answer_type"] == "python" else None
    calls = _python_calls(tree)
    python_run = _execute(question, answer)
    outcomes = {}
    printed = _result_lines(python_run["output_text"])
    padding = _padding_ngrams(answer, question.get("prompt", "")) if any(case["type"] == "text_regex" for case in question["cases"]) else set()
    for case in question["cases"]:
        # Figures count only when the code really printed them; comments are never evidence.
        scope = printed if case.get("section") in {"output", "comments"} else answer
        normalized = normalize(scope)
        kind = case["type"]
        reference = expected_rows(case["expected_sql"], dataset) if case.get("expected_sql") else []
        if kind == "sql_runs":
            passed = bool(rows)
            outcomes[case["id"]] = _test_case(passed, "Truy vấn chạy được và có dòng kết quả.", "Chạy được." if passed else (execution.get("error") or "Không có dòng kết quả."), "SQL_FAILED")
        elif kind == "sql_row_count":
            passed = len(rows) == len(reference)
            outcomes[case["id"]] = _test_case(passed, f"{len(reference)} dòng.", f"{len(rows)} dòng.")
        elif kind in {"sql_result", "sql_contains"}:
            passed = _rows_match(rows, reference, exact_count=kind == "sql_result") if kind == "sql_result" else all(any(_cell_equal(row[0], cell) for result in rows for cell in result) for row in reference if row[0] is not None)
            outcomes[case["id"]] = _test_case(passed, _rows_text(reference), _rows_text(rows))
        elif kind == "code_regex":
            passed = bool(re.search(case["pattern"], answer, re.IGNORECASE | re.DOTALL))
            outcomes[case["id"]] = _test_case(passed, case["description"], "Có trong bài." if passed else "Không thấy trong bài.", "MISSING_ELEMENT")
        elif kind == "py_parses":
            outcomes[case["id"]] = _test_case(tree is not None, "Code phân tích được.", "Đúng cú pháp." if tree is not None else "Lỗi cú pháp hoặc bỏ trống.", "CODE_NOT_PARSED")
        elif kind == "py_runs":
            passed = python_run["status"] == "OK"
            outcomes[case["id"]] = _test_case(passed, "Code chạy xong không lỗi.", "Chạy được." if passed else _run_failure(python_run), "CODE_FAILED")
        elif kind == "py_calls":
            alternatives = case.get("alternatives", {})
            missing = [name for name in case.get("all", []) if not ({name, *alternatives.get(name, [])} & calls)]
            any_ok = not case.get("any") or bool(set(case["any"]) & calls)
            passed = tree is not None and not missing and any_ok
            outcomes[case["id"]] = _test_case(passed, case["description"], "Có đủ lệnh cần thiết." if passed else f"Thiếu: {', '.join(missing or case.get('any', []))}.", "MISSING_ELEMENT")
        elif kind == "text_number":
            value = float(reference[0][0])
            passed = _mentions(scope, value, case.get("exact", False))
            outcomes[case["id"]] = _test_case(passed, _format(value), "Có giá trị đúng." if passed else "Không tìm thấy giá trị đúng.")
        elif kind == "text_numbers_all":
            values = [float(row[0]) for row in reference]
            missing = [value for value in values if not _mentions(scope, value, False)]
            outcomes[case["id"]] = _test_case(not missing, ", ".join(_format(value) for value in values), "Đủ các giá trị." if not missing else f"Thiếu {', '.join(_format(value) for value in missing)}.")
        elif kind == "text_number_near":
            value = float(reference[0][0])
            passed = _number_near_label(scope, case["labels"], value)
            outcomes[case["id"]] = _test_case(passed, _format(value), "Có giá trị đúng cạnh nội dung liên quan." if passed else "Không thấy giá trị đúng ở bước này.")
        elif kind == "text_pairs":
            missing = [str(row[0]) for row in reference if not _value_near_label(scope, str(row[0]), float(row[1]))]
            outcomes[case["id"]] = _test_case(not missing, "; ".join(f"{row[0]}: {_format(float(row[1]))}" for row in reference), "Đủ và đúng." if not missing else f"Sai hoặc thiếu: {', '.join(missing)}.")
        elif kind == "text_ids":
            wanted = {normalize(str(row[0])) for row in reference}
            allowed = {normalize(str(row[0])) for row in expected_rows(case["allowed_sql"], dataset)}
            mentioned = set(re.findall(r"\bor[a-z]\d+\b", normalized))
            passed = wanted <= mentioned and mentioned <= allowed
            outcomes[case["id"]] = _test_case(passed, ", ".join(sorted(item.upper() for item in wanted)), ", ".join(sorted(item.upper() for item in mentioned)) or "Không nêu mã đơn.")
        elif kind == "text_regex":
            # Headings may stand alone; every other concept must sit in an explaining sentence.
            scopes = [normalized] if case.get("anywhere") else _explaining(_sentences(scope), case["patterns"], padding)
            hits = sum(any(re.search(pattern, part) for part in scopes) for pattern in case["patterns"])
            forbidden = any(re.search(pattern, normalized) for pattern in case.get("forbid", []))
            passed = hits >= case["min_matches"] and not forbidden
            outcomes[case["id"]] = _test_case(passed, case["description"], "Có trong bài." if passed else "Không thấy trong bài.", "MISSING_ELEMENT")
        elif kind == "text_trend":
            rising, falling = _trend(scope)
            value = float(reference[0][0])
            passed = (rising and not falling) if value > 0 else (falling and not rising)
            outcomes[case["id"]] = _test_case(passed, "Doanh thu tăng." if value > 0 else "Doanh thu giảm.", "Đúng xu hướng." if passed else "Không nêu đúng xu hướng.")
        elif kind == "text_percent":
            value = float(reference[0][0])
            passed = _percent_ok(scope, value)
            outcomes[case["id"]] = _test_case(passed, f"{value:.2f}%".replace(".", ","), "Có giá trị đúng." if passed else "Không tìm thấy giá trị đúng.")
        elif kind == "text_sentences":
            count = len([part for part in re.split(r"[.!?\n]+", scope) if len(part.strip()) > 8])
            outcomes[case["id"]] = _test_case(count >= case["min"], f"Ít nhất {case['min']} câu.", f"{count} câu.", "FORMAT")
        else:
            raise ValueError(f"Loại kiểm tra không hỗ trợ: {kind}")
    if question["answer_type"] == "text" and _is_non_answer(answer):
        for case in question["cases"]:
            if outcomes[case["id"]]["passed"]:
                outcomes[case["id"]] = _test_case(False, case["description"], "Bài làm chỉ nêu là chưa biết nên không được tính.", "NON_ANSWER")
    if not any(outcomes[case["id"]]["passed"] for case in question["cases"] if case["type"] not in FOUNDATION_CASES):
        for case in question["cases"]:
            if case["type"] in FOUNDATION_CASES and outcomes[case["id"]]["passed"]:
                outcomes[case["id"]] = _test_case(False, case["description"], "Chạy được nhưng chưa đáp ứng yêu cầu nào của đề nên không được tính.", "NO_REQUIREMENT_MET")
    return outcomes, _violated_gates(question, answer, rows, code)


def _result_lines(output: str) -> str:
    """The printed lines that can be a result: lines of a table dump (many numbers each) are left out."""
    return "\n".join(line for line in (output or "").splitlines() if len(_numbers_in(line)) <= MAX_NUMBERS_ON_RESULT_LINE)


def _is_non_answer(answer: str) -> bool:
    text = normalize(answer)
    return len(re.findall(r"\w+", text)) <= NON_ANSWER_MAX_WORDS and bool(NON_ANSWER.search(text))


def _sentences(text: str) -> list[str]:
    """Normalized sentences. A dot or comma between digits (157.500) is not a break."""
    return [normalize(part) for part in SENTENCE_BREAK.split(re.sub(r"(?<=\d)[.,](?=\d)", "", text)) if part.strip()]


def _ngrams(words: list[str], size: int) -> list[tuple[str, ...]]:
    return [tuple(words[index:index + size]) for index in range(len(words) - size + 1)]


def _padding_ngrams(answer: str, prompt: str) -> set[tuple[str, ...]]:
    """Word runs that pad rather than explain: copied from the question, or repeated in two sentences."""
    padding = set(_ngrams(re.findall(r"\w+", normalize(prompt)), PROMPT_NGRAM))
    seen: dict[tuple[str, ...], int] = {}
    for index, sentence in enumerate(_sentences(answer)):
        for gram in set(_ngrams(re.findall(r"\w+", sentence), PADDING_NGRAM)):
            if gram in seen and seen[gram] != index:
                padding.add(gram)
            seen.setdefault(gram, index)
    return padding


def _own_words(sentence: str, concepts: re.Pattern, padding: set[tuple[str, ...]]) -> tuple[int, int]:
    """(concepts named, words of the learner's own): words outside every concept and every padding run."""
    words = list(re.finditer(r"\w+", sentence))
    taken = [False] * len(words)
    named: set[str] = set()
    for match in concepts.finditer(sentence):
        if match.end() > match.start():
            named.add(match.group().strip())
        for index, word in enumerate(words):
            if word.start() < match.end() and word.end() > match.start():
                taken[index] = True
    texts = [word.group() for word in words]
    for size in (PADDING_NGRAM, PROMPT_NGRAM):
        for index in range(len(words) - size + 1):
            if tuple(texts[index:index + size]) in padding:
                for offset in range(size):
                    taken[index + offset] = True
    return len(named), taken.count(False)


def _explaining(sentences: list[str], patterns: list[str], padding: Optional[set[tuple[str, ...]]] = None) -> list[str]:
    """Sentences that still hold words of their own once every concept and every padding run is removed.

    A sentence that names many concepts with few words of its own is a keyword list and explains nothing.
    """
    concepts = re.compile("|".join(f"(?:{pattern})" for pattern in patterns))
    kept = []
    for sentence in sentences:
        named, own = _own_words(sentence, concepts, padding or set())
        if own < MIN_CONTEXT_WORDS or (named >= LIST_MIN_CONCEPTS and own < named):
            continue
        kept.append(sentence)
    return kept


def lacks_substance(question: dict, outcomes: dict[str, dict]) -> bool:
    """True when the question checks computed data and the answer got none of it right."""
    core = [case["id"] for case in question["cases"] if case["type"] in SUBSTANCE_CASES]
    return bool(core) and not any(outcomes.get(case_id, {}).get("passed") for case_id in core)


def _run_failure(result: dict) -> str:
    reason = RUN_FAILURES.get(result["status"], "Code chưa chạy được.")
    detail = (result.get("error") or {}).get("message")
    return f"{reason} {detail}" if detail else reason


def _violated_gates(question: dict, answer: str, rows: list[list[Any]], code: bool) -> list[str]:
    dataset = question["dataset"]
    violated = []
    for gate in question["gates"]:
        if gate["type"] == "sql_equals":
            hit = _rows_match(rows, expected_rows(gate["wrong_sql"], dataset)) and not _same_result(gate, dataset, rows, question)
        elif gate["type"] == "sql_contains_all":
            hit = bool(rows) and _rows_match(rows, expected_rows(gate["wrong_sql"], dataset), exact_count=False) and not _rows_match(rows, expected_rows(gate["right_sql"], dataset), exact_count=False)
        elif gate["type"] == "trend_opposite":
            case = next(item for item in question["cases"] if item["id"] == gate["case_id"])
            value = float(expected_rows(case["expected_sql"], dataset)[0][0])
            rising, falling = _trend(answer)
            hit = (falling and not rising) if value > 0 else (rising and not falling)
        else:
            raise ValueError(f"Loại cổng không hỗ trợ: {gate['type']}")
        if hit:
            violated.append(gate["gate_id"])
    return violated


def _same_result(gate: dict, dataset: str, rows: list[list[Any]], question: dict) -> bool:
    """A dataset can make the wrong filter give the right numbers; correct output is never a violation."""
    case = next(item for item in question["cases"] if item["id"] == "result")
    return _rows_match(rows, expected_rows(case["expected_sql"], dataset))


def _format(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", "§").replace(".", ",").replace("§", ".")


def _rows_text(rows: list[list[Any]]) -> str:
    if not rows:
        return "Không có dòng kết quả."
    shown = "; ".join(" | ".join(_format(cell) if isinstance(cell, float) else str(cell if cell is not None else "NULL") for cell in row) for row in rows[:6])
    return shown + (f" … (+{len(rows) - 6} dòng)" if len(rows) > 6 else "")


# A level from one answer: code compared with trusted results is the firmest single check, a computed figure
# next, key phrases alone the weakest. Shown as a number only to keep the stored field; the learner-facing
# rating is ``backend.assessment_reliability``.
CONFIDENCE_BY_KIND = {"code": 0.7, "data": 0.6, "keywords": 0.3, "blank": 0.0}


def _confidence(question: dict, outcomes: dict[str, dict], blank: bool) -> float:
    if blank:
        return CONFIDENCE_BY_KIND["blank"]
    if question["answer_type"] in {"sql", "python"}:
        return CONFIDENCE_BY_KIND["code"]
    data = {"text_number", "text_numbers_all", "text_number_near", "text_pairs", "text_percent", "text_ids"}
    computed = any(outcomes.get(case["id"], {}).get("passed") for case in question["cases"] if case["type"] in data)
    return CONFIDENCE_BY_KIND["data" if computed else "keywords"]


def verify_exam(questions: list[dict], answers: dict[str, str]) -> dict:
    """Verifier output for the whole exam, with each skill's level set by its one question."""
    test_cases: dict[str, dict] = {}
    critical: dict[str, bool] = {}
    skills: dict[str, dict] = {}
    for question in questions:
        answer = answers.get(question["question_id"], "")
        blank = not answer.strip()
        outcomes, violated = ({}, []) if blank else evaluate_question(question, answer)
        earned = sum(case["points"] for case in question["cases"] if outcomes.get(case["id"], {}).get("passed"))
        for case in question["cases"]:
            test_cases[f"{question['question_id']}.{case['id']}"] = outcomes.get(case["id"]) or _test_case(False, case["description"], "Câu này chưa được trả lời.", "BLANK_ANSWER")
        for gate in question["gates"]:
            critical[gate["gate_id"]] = critical.get(gate["gate_id"], False) or gate["gate_id"] in violated
        ratio = earned / 100
        thin = not blank and lacks_substance(question, outcomes)
        level = verified_level(question["tier"], ratio, blank, bool(violated))
        if thin:
            level = min(level, 1)
        failed = [case["description"] for case in question["cases"] if not outcomes.get(case["id"], {}).get("passed")]
        skills[question["skill_code"]] = {
            "skill_code": question["skill_code"], "level": level, "deterministic_level": level, "score": ratio, "confidence": _confidence(question, outcomes, blank), "question_id": question["question_id"],
            "tier": question["tier"], "capped_by_critical_error": bool(violated), "capped_by_missing_data": thin and not violated, "blank": blank, "feedback": f"Đạt {earned}/100 ở độ khó {TIER_LABELS[question['tier']]}." + (" Còn thiếu: " + "; ".join(failed[:3]) + "." if failed else ""),
            "next_steps": failed, "checks": [],
        }
    return {"supported": True, "test_cases": test_cases, "critical": critical, "skill_results": skills, "proposed_level": max((item["level"] for item in skills.values()), default=0)}
