"""5.57.1: in English, a lesson's failed checks show their exam topic and check text in English.

Both are exam content, translated by the reviewed server catalog (data/i18n/sensitive_en.json) that the browser
never receives. What the learner's answer produced is never translated, and Vietnamese stays the default.
"""
import json
from pathlib import Path

import pytest

from backend.clock import set_clock
from backend.store import store
from v5_helpers import WRONG, P, STUDENT, client, good_answer, questions_of, set_default_jd, set_skills

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = json.loads((ROOT / "data" / "i18n" / "sensitive_en.json").read_text(encoding="utf-8"))
EN = {**STUDENT, "X-Language": "en"}


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    set_clock(None)
    yield
    set_clock(None)
    store.reset()


def _process_with_wrong_sql():
    """SQL answered wrongly (not blank, so the grader records what the answer produced); the rest answered well."""
    assert client.post(f"{P}/runs", json={"career_code": "DATA_ANALYST"}, headers=STUDENT).status_code == 201
    set_skills()
    set_default_jd()
    exam = client.post(f"{P}/exam/start", headers=STUDENT).json()
    for question in questions_of(exam["attempt_id"]):
        text = WRONG[question["answer_type"]] if question["skill_code"] == "SQL" else good_answer(question["item_id"])
        client.put(f"{P}/exam/responses/{question['question_id']}", json={"text": text}, headers=STUDENT)
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    client.post(f"{P}/result/confirm", headers=STUDENT)
    assert client.post(f"{P}/roadmap", json={"weekly_hours": 6, "timeline_weeks": 8}, headers=STUDENT).status_code == 200


def _sql_lesson(headers):
    journey = client.get("/me/journey", headers=STUDENT).json()
    ids = [lesson["activity_id"] for week in journey["weeks"] for topic in week["topics"] for lesson in topic["lessons"]]
    lessons = [client.get(f"/me/journey/lessons/{activity_id}", headers=headers).json() for activity_id in ids]
    return next(item for item in lessons if item["activity"]["target_skill"] == "SQL" and item["mistakes"])


def test_failed_checks_on_a_lesson_are_shown_in_english():
    _process_with_wrong_sql()
    vietnamese = _sql_lesson(STUDENT)
    english = _sql_lesson(EN)
    assert len(english["mistakes"]) == len(vietnamese["mistakes"])
    # The wrong SQL ran, so at least one check records what the answer produced.
    assert any(item["answer_gave"] for item in vietnamese["mistakes"])
    for source, shown in zip(vietnamese["mistakes"], english["mistakes"]):
        # The catalog holds every check text of the exam, so each one arrives in English.
        assert source["check"] in PRIVATE and shown["check"] == PRIVATE[source["check"]]
        if source.get("topic") in PRIVATE:
            assert shown["topic"] == PRIVATE[source["topic"]]
        # What the answer produced is the learner's own result and is never translated.
        assert shown["answer_gave"] == source["answer_gave"]
        assert {key: value for key, value in shown.items() if key not in ("check", "topic")} == {key: value for key, value in source.items() if key not in ("check", "topic")}


def test_vietnamese_lessons_keep_the_source_text():
    _process_with_wrong_sql()
    lesson = _sql_lesson(STUDENT)
    assert all(item["check"] not in PRIVATE.values() for item in lesson["mistakes"])
