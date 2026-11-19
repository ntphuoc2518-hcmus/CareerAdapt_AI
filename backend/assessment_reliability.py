"""How much each verified skill level can be trusted, read from the evidence already stored.

The bank holds one exam question per skill × difficulty, so a level is often concluded from a single
answer. This module does not change any level: it says, per skill, how many independent graded sources
support the current level and what kind of check each one was, and turns that into a rating with the
reasons written out. Nothing here is stored and no AI is involved; the same data always gives the same
answer.

Kinds of evidence, strongest first:
- CODE: SQL or Python that was run and compared with results computed by trusted SQL.
- WRITTEN_DATA: a written answer with at least one figure the learner had to compute, checked exactly.
- WRITTEN_KEYWORDS: a written answer whose passed checks are only key phrases (reasoning not verified).
- QUIZ: closed questions of a lesson check or review mini-test (choice, number, ordering).
- HUMAN: a level set by a reviewer.
- NOTHING: the answer was blank or passed no check, so it shows nothing about the skill.

Rating of the current level:
- HIGH: two or more independent sources support it and at least one is CODE or WRITTEN_DATA.
- MEDIUM: one CODE / WRITTEN_DATA / HUMAN source supports it, or two or more QUIZ sources do.
- LOW: it rests on one quiz or on key phrases only, a newer source shows a lower level, or the level is 0.
- NONE: the skill has no verified level yet.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from backend.store import store
from backend.targeting import resolve_target

CODE_ANSWERS = {"sql", "python"}
DATA_CASES = {"text_number", "text_numbers_all", "text_number_near", "text_pairs", "text_percent", "text_ids"}
PRACTICAL = {"CODE", "WRITTEN_DATA"}
KIND_LABELS = {
    "CODE": "Chạy code, so với kết quả tính sẵn",
    "WRITTEN_DATA": "Bài viết có số liệu tự tính đúng",
    "WRITTEN_KEYWORDS": "Bài viết chỉ khớp cụm từ khóa",
    "QUIZ": "Câu hỏi đóng (trắc nghiệm, số, sắp xếp)",
    "HUMAN": "Người duyệt chấm",
    "NOTHING": "Bỏ trống hoặc không phần nào đạt",
}
SOURCE_LABELS = {"ASSESSMENT": "Bài kiểm tra đầu vào", "FINAL_ASSESSMENT": "Bài đánh giá tổng hợp", "MINI_TEST": "Kiểm tra kiến thức", "HUMAN_REVIEW": "Người duyệt"}
RATING_LABELS = {"HIGH": "Cao", "MEDIUM": "Trung bình", "LOW": "Thấp", "NONE": "Chưa có"}


def _question_kind(question: dict, passed: dict[str, bool]) -> str:
    """The kind of check a question's answer passed, from the case types that passed."""
    ok = {case["type"] for case in question.get("cases", []) if passed.get(f"{question['question_id']}.{case['id']}")}
    if not ok:
        return "NOTHING"
    if question.get("answer_type") in CODE_ANSWERS:
        return "CODE"
    return "WRITTEN_DATA" if ok & DATA_CASES else "WRITTEN_KEYWORDS"


def _exam_kinds(source_id: str) -> dict[str, str]:
    """Skill → kind for an entry-exam submission (``skill_evidence.source_id`` is its submission id)."""
    attempt = store.db.one("SELECT payload FROM exam_attempts WHERE submission_id = ?", (source_id,))
    if not attempt:
        return {}
    rows = store.db.query("SELECT test_case_id, passed FROM test_case_results WHERE submission_id = ?", (source_id,))
    passed = {row["test_case_id"]: bool(row["passed"]) for row in rows}
    return {question["skill_code"]: _question_kind(question, passed) for question in json.loads(attempt["payload"]).get("questions", [])}


def _final_kinds(source_id: str) -> dict[str, str]:
    row = store.db.one("SELECT payload FROM final_attempts WHERE attempt_id = ?", (source_id,))
    if not row:
        return {}
    payload = json.loads(row["payload"])
    passed = {key: bool(value.get("passed")) for key, value in ((payload.get("result") or {}).get("test_cases") or {}).items()}
    return {question["skill_code"]: _question_kind(question, passed) for question in payload.get("questions", [])}


def _kind(row: dict, cache: dict[str, dict[str, str]]) -> str:
    source = row["source_type"]
    if source == "MINI_TEST":
        return "QUIZ"
    if source == "HUMAN_REVIEW":
        return "HUMAN"
    reader = _final_kinds if source == "FINAL_ASSESSMENT" else _exam_kinds
    if row["source_id"] not in cache:
        cache[row["source_id"]] = reader(row["source_id"])
    # Evidence of an older task type (V4 practice tasks) has no exam payload: those were graded by test cases.
    return cache[row["source_id"]].get(row["skill_code"], "CODE")


def rate(level: Optional[int], sources: list[dict]) -> tuple[str, list[str]]:
    """The rating of one skill's current level and the reasons, from its sources (oldest first)."""
    if level is None:
        return "NONE", ["Chưa có bài làm được chấm cho kỹ năng này."]
    if level == 0:
        # Level 0 is the absence of evidence, so there is nothing whose reliability could be high.
        return "LOW", ["Mức 0 nghĩa là chưa có bằng chứng đạt mức 1.", f"{len(sources)} bài đã chấm cho kỹ năng này chưa chứng minh được mức 1."]
    supporting = [item for item in sources if item["level"] >= level]
    practical = [item for item in supporting if item["kind"] in PRACTICAL]
    quiz = [item for item in supporting if item["kind"] == "QUIZ"]
    human = [item for item in supporting if item["kind"] == "HUMAN"]
    reasons = [f"{len(supporting)} nguồn độc lập cho thấy mức {level} trở lên."]
    newest = sources[-1] if sources else None
    contradicted = bool(newest and newest["level"] < level)
    if contradicted:
        reasons.append(f"Bài gần nhất ({newest['source_label'].lower()}) chỉ cho thấy mức {newest['level']}; mức không bị hạ nhưng cần kiểm tra lại.")
    if len(supporting) == 1:
        reasons.append("Mức này được kết luận từ một bài duy nhất; ngân hàng hiện có một câu cho mỗi kỹ năng × độ khó.")
    if supporting and not practical and not human:
        reasons.append("Chưa có bài thực hành nào (chạy code hoặc tự tính số liệu) xác nhận mức này.")
    if any(item["kind"] == "WRITTEN_KEYWORDS" for item in supporting):
        reasons.append("Phần lập luận của bài viết được kiểm bằng cụm từ khóa, chưa có người đọc lại.")
    if contradicted:
        rating = "LOW"
    elif len(supporting) >= 2 and practical:
        rating = "HIGH"
    elif practical or human or len(quiz) >= 2:
        rating = "MEDIUM"
    else:
        rating = "LOW"
    return rating, reasons


def _next_step(rating: str, level: Optional[int], target: int) -> str:
    if rating == "NONE":
        return "Làm bài kiểm tra kiến thức của bài học kỹ năng này hoặc bài đánh giá tổng hợp để có mức đầu tiên."
    if rating == "HIGH":
        return "Mức này đã có nhiều nguồn xác nhận."
    if (level or 0) < target:
        return "Học các bài của kỹ năng này trên lộ trình rồi làm bài đánh giá tổng hợp: thêm một bài thực hành độc lập sẽ nâng độ tin cậy."
    return "Bài đánh giá tổng hợp sẽ thêm một bài thực hành độc lập cho kỹ năng này."


def reliability(user_id: uuid.UUID) -> dict[str, Any]:
    """Per target skill: current verified level, every source behind it and how far it can be trusted."""
    profile = store.get_or_create_profile(user_id)
    assessed = profile.get("assessed_skills") or {}
    target = resolve_target(profile).get("requirements_by_skill") or {}
    codes = [code for code, item in target.items() if float(item.get("weight", 0) or 0) > 0] or sorted(assessed)
    cache: dict[str, dict[str, str]] = {}
    skills = []
    for code in codes:
        rows = sorted(store.skill_evidence(user_id, code), key=lambda row: row["created_at"])
        sources = []
        for row in rows:
            kind = _kind(row, cache)
            sources.append({
                "source_type": row["source_type"], "source_label": SOURCE_LABELS.get(row["source_type"], row["source_type"]), "kind": kind, "kind_label": KIND_LABELS[kind],
                "level": int(row["level"]), "score": round(float(row["score"]) * 100) if row.get("score") is not None else None, "created_at": row["created_at"],
            })
        level = (assessed.get(code) or {}).get("level")
        level = int(level) if level is not None else None
        rating, reasons = rate(level, sources)
        wanted = int((target.get(code) or {}).get("target_level") or 0)
        skills.append({
            "skill_code": code, "current_level": level, "target_level": wanted, "rating": rating, "rating_label": RATING_LABELS[rating], "reasons": reasons,
            "sources": sources, "supporting": sum(1 for item in sources if level is not None and item["level"] >= level), "next_step": _next_step(rating, level, wanted),
        })
    counts = {key: sum(1 for item in skills if item["rating"] == key) for key in RATING_LABELS}
    return {
        "skills": skills, "counts": counts, "rules": [
            "Cao: từ 2 nguồn độc lập trở lên xác nhận mức hiện tại, trong đó có bài thực hành (chạy code hoặc tự tính số liệu).",
            "Trung bình: một bài thực hành hoặc một người duyệt xác nhận, hoặc từ 2 bài kiểm tra kiến thức.",
            "Thấp: chỉ một bài kiểm tra kiến thức, chỉ khớp cụm từ khóa, hoặc bài gần nhất cho mức thấp hơn.",
        ],
        "note": "Bảng này không đổi mức kỹ năng; nó cho biết mức hiện tại dựa trên bao nhiêu bài làm và loại kiểm tra nào.",
    }
