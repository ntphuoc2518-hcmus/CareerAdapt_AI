"""Rule engine: turn verifier results and a published blueprint into points and a pass decision.

The final score always comes from here. The AI layer can only ask for a human review; it can
never add a point, change a threshold or clear a critical gate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

BLUEPRINTS: dict[str, Any] = json.loads((Path(__file__).resolve().parents[2] / "data" / "assessment_blueprints_v4.json").read_text(encoding="utf-8"))
BLUEPRINT_VERSION: str = BLUEPRINTS["blueprint_version"]
RULE_VERSION: str = BLUEPRINTS["rule_version"]


def get_blueprint(task_id: str) -> Optional[dict]:
    entry = BLUEPRINTS["tasks"].get(task_id.upper().strip())
    if entry and "same_as" in entry:
        entry = BLUEPRINTS["tasks"].get(entry["same_as"])
    return entry


def validate_blueprints() -> list[str]:
    """Consistency problems in the published blueprints: points must add up and refer to real criteria."""
    problems = []
    for task_id, blueprint in BLUEPRINTS["tasks"].items():
        if "same_as" in blueprint:
            continue
        questions = {item["question_id"] for item in blueprint["questions"]}
        criteria = {item["criterion_id"]: item for item in blueprint["criteria"]}
        if sum(item["max_points"] for item in blueprint["criteria"]) != 100:
            problems.append(f"{task_id}: tổng điểm tiêu chí khác 100.")
        for criterion_id, criterion in criteria.items():
            points = sum(case["points"] for case in blueprint["test_cases"] if case["criterion_id"] == criterion_id)
            if points != criterion["max_points"]:
                problems.append(f"{task_id}/{criterion_id}: tổng điểm test case {points} khác {criterion['max_points']}.")
        for case in blueprint["test_cases"]:
            if case["criterion_id"] not in criteria or case["question_id"] not in questions:
                problems.append(f"{task_id}/{case['test_case_id']}: tham chiếu không hợp lệ.")
    return problems


def public_blueprint(blueprint: dict) -> dict:
    """What a learner may see before starting: questions and criteria, no expected values."""
    return {
        "rubric_version": blueprint["rubric_version"],
        "pass_threshold": blueprint["pass_threshold"],
        "scope_note": blueprint["scope_note"],
        "support_policy": blueprint["support_policy"],
        "required_outputs": blueprint["required_outputs"],
        "questions": blueprint["questions"],
        "criteria": [{key: item[key] for key in ("criterion_id", "label", "max_points", "skill_code")} for item in blueprint["criteria"]],
        "critical_gates": blueprint["critical_gates"],
    }


def validate_answers(blueprint: dict, answers: dict[str, str]) -> dict:
    """Classify a submission before any content is graded.

    EMPTY: nothing to grade. INVALID: a required output is missing, so the rest is not graded.
    VALID: gradable; a blank non-required question simply scores zero.
    """
    known = {item["question_id"]: item for item in blueprint["questions"]}
    blank = [question_id for question_id in known if not (answers.get(question_id) or "").strip()]
    if len(blank) == len(known):
        return {"state": "EMPTY", "blank_questions": blank, "missing_outputs": list(blueprint["required_outputs"]), "problems": ["Bài nộp không có câu trả lời nào."]}
    problems = []
    for question_id, value in answers.items():
        limit = known.get(question_id, {}).get("max_chars")
        if limit and len(value or "") > limit:
            problems.append(f"{known[question_id]['label']} vượt giới hạn {limit} ký tự.")
    missing = [question_id for question_id in blueprint["required_outputs"] if question_id in blank]
    if missing:
        labels = ", ".join(known[question_id]["label"] for question_id in missing)
        problems.append(f"Thiếu đầu ra bắt buộc: {labels}.")
    return {"state": "INVALID" if problems else "VALID", "blank_questions": blank, "missing_outputs": missing, "problems": problems}


def _criterion_level(earned: float, maximum: float) -> int:
    ratio = earned / maximum if maximum else 0.0
    if ratio <= 0:
        return 0
    if ratio < 0.5:
        return 1
    return 3 if ratio >= 1 else 2


def score_submission(blueprint: dict, verifier: dict, blank_questions: list[str]) -> dict:
    """Award points per test case. A blank question scores zero and is never counted as correct."""
    cases = verifier.get("test_cases", {})
    results = []
    for case in blueprint["test_cases"]:
        outcome = cases.get(case["test_case_id"]) or {"passed": False, "expected_summary": case["description"], "actual_summary": "Không có kết quả kiểm tra.", "failure_code": "NOT_EVALUATED"}
        blank = case["question_id"] in blank_questions
        passed = bool(outcome["passed"]) and not blank
        results.append({
            "test_case_id": case["test_case_id"], "version": BLUEPRINT_VERSION, "criterion_id": case["criterion_id"], "question_id": case["question_id"],
            "description": case["description"], "expected_summary": outcome["expected_summary"],
            "actual_summary": "Câu này chưa được trả lời." if blank else outcome["actual_summary"],
            "passed": passed, "points_awarded": float(case["points"]) if passed else 0.0, "points_max": float(case["points"]),
            "failure_code": None if passed else ("BLANK_ANSWER" if blank else outcome.get("failure_code") or "VALUE_MISMATCH"),
        })
    criteria = []
    for criterion in blueprint["criteria"]:
        own = [item for item in results if item["criterion_id"] == criterion["criterion_id"]]
        earned = sum(item["points_awarded"] for item in own)
        blank = any(question in blank_questions for question in criterion["question_ids"]) and all(question in blank_questions for question in criterion["question_ids"])
        criteria.append({
            "criterion_id": criterion["criterion_id"], "label": criterion["label"], "skill_code": criterion.get("skill_code"), "version": blueprint["rubric_version"],
            "points_awarded": earned, "max_points": float(criterion["max_points"]), "level_proposed": _criterion_level(earned, criterion["max_points"]),
            "blank": blank, "failed_test_cases": [item["test_case_id"] for item in own if not item["passed"]],
        })
    gates = {gate["gate_id"]: gate for gate in blueprint["critical_gates"]}
    violations = [
        {"gate_id": gate_id, "label": gates[gate_id]["label"]}
        for gate_id, violated in (verifier.get("critical") or {}).items()
        if violated and gate_id in gates
    ]
    total = round(sum(item["points_awarded"] for item in results), 2)
    threshold = float(blueprint["pass_threshold"])
    return {
        "final_score": total, "max_score": 100.0, "pass_threshold": threshold,
        "passed": total >= threshold and not violations,
        "critical_violations": violations, "test_case_results": results, "criteria": criteria,
        "blank_questions": blank_questions, "rule_version": RULE_VERSION,
    }


def apply_critical_cap(skill_results: dict[str, dict], blueprint: dict, scoring: dict) -> None:
    """A critical error keeps every skill the task measures below the independent level."""
    if not scoring["critical_violations"]:
        return
    for result in skill_results.values():
        if int(result.get("level", 0)) > 1:
            result["level"] = result["deterministic_level"] = 1
            result["capped_by_critical_error"] = True
