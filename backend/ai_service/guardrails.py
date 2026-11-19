"""AI Security and Validation Layer: when the assistant may run, and what of its output is kept."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException, status

from backend import career_process, config, exam_service
from backend.clock import utcnow
from backend.store import store

# Lets the output check see that the system prompt has leaked.
CANARY = "CA-GUARD-7F3A"
SOCIAL_MARKER = "[[CHAT]]"
MINI_TEST_WINDOW_MINUTES = 30
CITATION = re.compile(r"\[S(\d{1,2})\]")
CLAIM = re.compile(r"(?i)(\d+(?:[.,]\d+)?)\s*(?:%|phần trăm|điểm|/\s*100|giờ)|mức\s+(\d)")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
EXAM_BLOCK = "Trợ lý tạm dừng trong lúc bạn làm bài kiểm tra, vì bài kiểm tra không có trợ giúp. Hãy quay lại sau khi nộp bài."


def open_test(user_id: uuid.UUID) -> Optional[tuple[str, str]]:
    """The test the account is taking, as (reason shown to the learner, page link to return to it), or None.
    Decided on the server from the account's state, so another tab or a direct call changes nothing."""
    from backend.api.test_center import _refresh

    if career_process.active_run(user_id):
        attempt = exam_service.current_attempt(user_id)
        if attempt and attempt["status"] == "IN_PROGRESS":
            return EXAM_BLOCK, "#/flow"
    running = next((item for item in store.user_test_attempts(user_id) if item["mode"] != "PRACTICE" and _refresh(item)["status"] == "IN_PROGRESS"), None)
    if running:
        return EXAM_BLOCK, f"#/tests/run/{running['attempt_id']}"
    final = store.db.one("SELECT attempt_id FROM final_attempts WHERE user_id = ? AND status = 'IN_PROGRESS' LIMIT 1", (str(user_id),))
    if final:
        return EXAM_BLOCK, "#/final-exam"
    cutoff = (utcnow() - timedelta(minutes=MINI_TEST_WINDOW_MINUTES)).isoformat()
    # A mini-test can wait for days; only one the learner has opened counts as being taken.
    row = store.db.one("SELECT micro_id FROM micro_assessments WHERE user_id = ? AND status = 'PENDING' AND json_extract(payload, '$.opened_at') >= ? LIMIT 1", (str(user_id), cutoff))
    if row:
        return "Trợ lý tạm dừng khi bạn đang mở mini-test. Hãy nộp bài rồi quay lại.", f"#/mini/{row['micro_id']}"
    return None


def assistant_block(user_id: uuid.UUID) -> Optional[str]:
    found = open_test(user_id)
    return found[0] if found else None


def require_open(user_id: uuid.UUID) -> None:
    reason = assistant_block(user_id)
    if reason:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=reason)


def enforce_rate(user_id: uuid.UUID) -> None:
    since = (utcnow() - timedelta(minutes=1)).isoformat()
    used = store.db.one("SELECT COUNT(*) AS n FROM ai_usage_traces WHERE user_id = ? AND task = 'assistant_turn' AND created_at >= ?", (str(user_id), since))["n"]
    if used >= config.AI_CHAT_PER_MINUTE:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Bạn đang gửi quá nhanh. Hãy chờ một phút rồi thử lại.")


def _day_start() -> str:
    now: datetime = utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def budget_problem(user_id: uuid.UUID) -> Optional[str]:
    """The reason AI is out of budget today, or None. The assistant then answers without AI."""
    start = _day_start()
    total = "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) AS n FROM ai_usage_traces WHERE created_at >= ?"
    if store.db.one(total + " AND user_id = ?", (start, str(user_id)))["n"] >= config.AI_DAILY_TOKENS_PER_USER:
        return "Bạn đã dùng hết hạn mức AI của hôm nay."
    if store.db.one(total, (start,))["n"] >= config.AI_DAILY_TOKENS_TOTAL:
        return "Hệ thống đã dùng hết hạn mức AI của hôm nay."
    return None


def usage_report(days: int = 7) -> dict:
    since = (utcnow() - timedelta(days=days)).isoformat()
    rows = store.db.query(
        "SELECT task, status, error, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens, AVG(latency_ms) AS avg_latency_ms "
        "FROM ai_usage_traces WHERE created_at >= ? GROUP BY task, status, error ORDER BY calls DESC", (since,))
    return {"days": days, "rows": rows, "total_tokens": sum((row["input_tokens"] or 0) + (row["output_tokens"] or 0) for row in rows)}


def leaked_prompt(text: str) -> bool:
    return CANARY in text


def resolve_citations(text: str, sources: list[dict]) -> tuple[str, list[dict]]:
    """Keep markers of sources that were really retrieved; a made-up marker is removed."""
    known = {source["source_id"]: source for source in sources}
    used: dict[str, dict] = {}

    def replace(match: re.Match) -> str:
        key = f"S{match.group(1)}"
        if key in known:
            used[key] = known[key]
            return match.group(0)
        return ""

    return re.sub(r"[ \t]{2,}", " ", CITATION.sub(replace, text)).strip(), list(used.values())


def _values(text: str) -> set[float]:
    return {float(item.replace(",", ".")) for item in NUMBER.findall(text)}


def unverified_numbers(answer: str, evidence: list[Any]) -> list[str]:
    """Scores, percents, hours and levels in a reply must appear in what the backend supplied."""
    known = _values(" ".join(item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=str) for item in evidence))
    unknown = []
    for match in CLAIM.finditer(CITATION.sub("", answer)):
        value = match.group(1) or match.group(2)
        if float(value.replace(",", ".")) not in known:
            unknown.append(match.group(0).strip())
    return unknown
