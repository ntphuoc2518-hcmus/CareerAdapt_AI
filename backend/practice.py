"""Practice exercises of a lesson: the learner runs code on the sample data and checks the answer.

The exercises live in their own file, never in the exam bank, so practising cannot reveal a test
question. A practice check runs the same test-case engine as the exam and is stored as practice
history only: it is never skill evidence and never changes a level or a lesson's state.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status

from backend.clock import utcnow
from backend.database import dumps
from backend.engine.exam_grader import BANK, evaluate_question
from backend.store import store

DATA = json.loads((Path(__file__).resolve().parents[1] / "data" / "practice_items_v1.json").read_text(encoding="utf-8"))
EXERCISES = {item["exercise_id"]: item for item in DATA["items"]}
PUBLIC_FIELDS = ("exercise_id", "activity_id", "skill_code", "title", "prompt", "answer_type", "workspace", "max_chars", "placeholder", "minutes", "report_sections")


def validate() -> list[str]:
    problems = []
    for item in DATA["items"]:
        if sum(case["points"] for case in item["cases"]) != 100:
            problems.append(f"{item['exercise_id']}: tổng điểm khác 100.")
        if item["dataset"] not in BANK["datasets"]:
            problems.append(f"{item['exercise_id']}: bộ dữ liệu không tồn tại.")
    return problems


def question_of(item: dict) -> dict:
    """The exercise in the shape the test-case engine reads.

    Practice is formative and never evidence, and its answers are short labelled fields ("Mục tiêu: …"),
    so a concept may stand anywhere; the exam's explaining-sentence rule does not apply here.
    """
    cases = [{**case, "anywhere": True} if case["type"] == "text_regex" else case for case in item["cases"]]
    return {**item, "cases": cases, "question_id": item["exercise_id"], "dataset": BANK["datasets"][item["dataset"]], "gates": [], "label": item["title"], "topic": item["title"], "tier": 1}


def _latest(user_id: uuid.UUID, exercise_id: str) -> Optional[dict]:
    row = store.db.one("SELECT * FROM practice_attempts WHERE user_id = ? AND exercise_id = ? AND archived_by_run IS NULL ORDER BY created_at DESC, rowid DESC LIMIT 1", (str(user_id), exercise_id))
    if not row:
        return None
    payload = json.loads(row["payload"])
    return {"attempt_id": row["attempt_id"], "score": row["score"], "created_at": row["created_at"], "answer": row["answer_text"], "cases": payload.get("cases", [])}


def exercises_for(user_id: uuid.UUID, activity_id: str) -> list[dict]:
    from backend.exam_service import _dataset_view

    found = []
    for item in DATA["items"]:
        if item["activity_id"] != activity_id:
            continue
        attempts = store.db.one("SELECT COUNT(*) AS n FROM practice_attempts WHERE user_id = ? AND exercise_id = ? AND archived_by_run IS NULL", (str(user_id), item["exercise_id"]))["n"]
        found.append({**{key: item.get(key) for key in PUBLIC_FIELDS}, "checks": [case["description"] for case in item["cases"]],
                      "dataset": _dataset_view(BANK["datasets"][item["dataset"]]), "attempts": attempts, "latest": _latest(user_id, item["exercise_id"])})
    return found


def _exercise_for_learner(user_id: uuid.UUID, exercise_id: str) -> dict:
    from backend.learning_journey import roadmap_activity

    item = EXERCISES.get(exercise_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài thực hành.")
    roadmap_activity(user_id, item["activity_id"])
    return item


def run(user_id: uuid.UUID, exercise_id: str, code: str) -> dict:
    from backend.exam_service import run_question_code

    item = _exercise_for_learner(user_id, exercise_id)
    return run_question_code(user_id, question_of(item), code)


def check(user_id: uuid.UUID, exercise_id: str, answer: str) -> dict:
    """Grade a practice answer and keep it as practice history."""
    item = _exercise_for_learner(user_id, exercise_id)
    if not answer.strip():
        raise HTTPException(status_code=422, detail="Bài làm đang trống.")
    if len(answer) > item["max_chars"]:
        raise HTTPException(status_code=413, detail=f"Bài làm vượt giới hạn {item['max_chars']} ký tự.")
    question = question_of(item)
    try:
        if question["answer_type"] in {"sql", "python"}:
            from backend.exam_service import code_run_slot

            # A check runs the learner's code like the "Chạy thử" button, so it takes the same one-run-at-a-time slot.
            with code_run_slot(user_id, gap=False):
                outcomes, _ = evaluate_question(question, answer)
        else:
            outcomes, _ = evaluate_question(question, answer)
    except RuntimeError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Môi trường chạy code đang bận. Hãy thử lại sau ít phút.")
    cases = [{"id": case["id"], "description": case["description"], "points": case["points"], "passed": bool(outcomes.get(case["id"], {}).get("passed"))} for case in item["cases"]]
    score = sum(case["points"] for case in cases if case["passed"])
    now = utcnow().isoformat()
    attempt_id = str(uuid.uuid4())
    store.db.execute(
        "INSERT INTO practice_attempts(attempt_id, user_id, activity_id, exercise_id, answer_text, score, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (attempt_id, str(user_id), item["activity_id"], exercise_id, answer, score, dumps({"cases": cases}), now),
    )
    return {"attempt_id": attempt_id, "exercise_id": exercise_id, "score": score, "cases": cases, "created_at": now,
            "note": "Bài thực hành chỉ để tự kiểm tra, không phải bằng chứng năng lực và không đổi trạng thái bài học."}
