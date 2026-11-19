"""The checks a learner actually failed, attached to the lessons that teach that skill (5.46.0).

Read only. For each skill it takes the newest graded practical answer (entry exam or final assessment)
and lists the test cases that answer did not pass, with the case text and what the answer produced.
A lesson of that skill shows them, the closest to its objectives first, so the learner studies the parts
they got wrong instead of the whole topic. Nothing here changes a level, a score or the schedule.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from backend.lesson_checks import _words
from backend.store import store

MAX_PER_LESSON = 5


def _exam_failures(user_id: uuid.UUID) -> list[dict]:
    row = store.db.one(
        """SELECT exam_attempts.payload, exam_attempts.submission_id, exam_attempts.submitted_at FROM exam_attempts
           JOIN career_runs ON career_runs.run_id = exam_attempts.run_id
           WHERE exam_attempts.user_id = ? AND exam_attempts.status = 'GRADED' AND career_runs.status != 'ARCHIVED'
           ORDER BY exam_attempts.submitted_at DESC LIMIT 1""",
        (str(user_id),),
    )
    if not row:
        return []
    results = {item["test_case_id"]: item for item in store.db.query(
        "SELECT test_case_id, passed, actual_summary, failure_code FROM test_case_results WHERE submission_id = ?", (row["submission_id"],))}
    return _failures(json.loads(row["payload"]).get("questions", []), results, "Bài kiểm tra đầu vào", row["submitted_at"])


def _final_failures(user_id: uuid.UUID) -> list[dict]:
    row = store.db.one(
        "SELECT payload, submitted_at FROM final_attempts WHERE user_id = ? AND status = 'GRADED' AND archived_by_run IS NULL ORDER BY submitted_at DESC LIMIT 1",
        (str(user_id),),
    )
    if not row:
        return []
    payload = json.loads(row["payload"])
    results = {key: {"passed": value.get("passed"), "actual_summary": value.get("actual_summary"), "failure_code": value.get("failure_code")}
               for key, value in ((payload.get("result") or {}).get("test_cases") or {}).items()}
    return _failures(payload.get("questions", []), results, "Bài đánh giá tổng hợp", row["submitted_at"])


def _failures(questions: list[dict], results: dict[str, dict], source: str, when: Optional[str]) -> list[dict]:
    found = []
    for question in questions:
        for case in question.get("cases", []):
            result = results.get(f"{question['question_id']}.{case['id']}")
            if result is None or result.get("passed"):
                continue
            found.append({
                "skill_code": question["skill_code"], "source": source, "submitted_at": when, "topic": question.get("topic"),
                "check": case["description"], "blank": result.get("failure_code") == "BLANK_ANSWER",
                "answer_gave": None if result.get("failure_code") == "BLANK_ANSWER" else result.get("actual_summary"),
            })
    return found


def skill_failures(user_id: uuid.UUID) -> dict[str, list[dict]]:
    """Skill → failed checks of the newest graded practical answer of that skill."""
    newest: dict[str, list[dict]] = {}
    for item in sorted(_exam_failures(user_id) + _final_failures(user_id), key=lambda entry: entry["submitted_at"] or "", reverse=True):
        bucket = newest.setdefault(item["skill_code"], [])
        if not bucket or bucket[0]["submitted_at"] == item["submitted_at"]:
            bucket.append(item)
    return newest


def lesson_mistakes(user_id: uuid.UUID, activity: dict, failures: Optional[dict[str, list[dict]]] = None) -> list[dict]:
    """The failed checks of the lesson's skill, closest to the lesson's objectives first."""
    failures = skill_failures(user_id) if failures is None else failures
    goal = _words(" ".join([activity.get("title", ""), activity.get("learning_outcome", "") or "", *activity.get("learning_objectives", [])]))
    ranked = []
    for item in failures.get(activity.get("target_skill"), []):
        overlap = len(goal & _words(f"{item['check']} {item.get('topic') or ''}"))
        ranked.append({**item, "related": overlap > 0, "overlap": overlap})
    ranked.sort(key=lambda item: (-item["overlap"], item["check"]))
    return ranked[:MAX_PER_LESSON]
