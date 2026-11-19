"""Periodic work: due reminders, limited grading retries, link checks and answer retention."""
from __future__ import annotations

import asyncio
import copy
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from backend.clock import utcnow
from backend.learning_cycle_service import run_scan
from backend.store import store

logger = logging.getLogger("careeradapt.background")

TICK_SECONDS = 60
RETRY_BACKOFF_MINUTES = 5
ANSWER_RETENTION_DAYS = 90
LINK_CHECKS_PER_TICK = 2


def retry_pending_submissions() -> int:
    """Retry graded-but-held submissions a limited number of times, with a pause between tries."""
    from backend.ai_service.assessment_provider import is_enabled
    from backend.ai_service.llm_grader import MAX_GRADE_ATTEMPTS, grade_submission_orchestrator
    from backend.api.submissions import _after_grading, _load_answers

    if not is_enabled():
        return 0
    cutoff = (utcnow() - timedelta(minutes=RETRY_BACKOFF_MINUTES)).isoformat()
    rows = store.db.query("SELECT submission_id FROM assessment_attempts WHERE status = 'PENDING_RETRY' AND grade_attempts < ? AND updated_at < ?", (MAX_GRADE_ATTEMPTS, cutoff))
    done = 0
    for row in rows:
        claimed = store.db.execute("UPDATE assessment_attempts SET status = 'PROCESSING' WHERE submission_id = ? AND status = 'PENDING_RETRY'", (row["submission_id"],)).rowcount
        if not claimed:
            continue
        record = next(item for key, item in store.submissions.items() if str(key) == row["submission_id"])
        answers, text = _load_answers(record["submission_id"])
        assessment = grade_submission_orchestrator(
            submission_id=record["submission_id"], user_id=record["user_id"], task_id=record["task_id"], submission_text=text, mode=record["mode"],
            task_snapshot=copy.deepcopy(record.get("task_snapshot")), declared_tool=record.get("declared_tool", "Chưa khai báo"),
            used_assistance=record.get("used_assistance", False), assistance_details=record.get("assistance_details", ""), answers=answers,
        )
        with store.user_scope(record["user_id"]):
            _after_grading(record["user_id"], assessment)
        done += 1
    return done


def purge_expired_answers() -> int:
    """Remove answer text past the retention period; scores and the audit trail stay.

    Career Adapt exams are kept: the learner reviews that work in their account until they reset or erase it."""
    cutoff = (utcnow() - timedelta(days=ANSWER_RETENTION_DAYS)).isoformat()
    return store.db.execute("UPDATE submission_answers SET answer_text = NULL WHERE submitted_at < ? AND answer_text IS NOT NULL "
        "AND submission_id NOT IN (SELECT submission_id FROM exam_attempts WHERE submission_id IS NOT NULL)", (cutoff,)).rowcount


def finish_expired_exams() -> int:
    """Submit entry exams and final assessments whose time ran out while the learner was away."""
    from backend import final_assessment
    from backend.exam_service import finish_expired

    return finish_expired() + final_assessment.finish_expired()


def check_due_links() -> int:
    """Re-check a few resources whose review date passed, so a dead link gets hidden on its own."""
    from backend.api.resources import run_link_check
    from backend.catalog import list_resources

    now = utcnow().isoformat()
    due = [item for item in list_resources(store.db, approved_only=False) if item["status"] == "APPROVED" and (item.get("next_review_at") or "") < now]
    for resource in due[:LINK_CHECKS_PER_TICK]:
        run_link_check(resource)
    return len(due[:LINK_CHECKS_PER_TICK])


def embed_knowledge() -> int:
    """Add vectors for newly approved knowledge. On failure, retrieval stays keyword-only until the next tick."""
    from backend.ai_service.gateway import GatewayError
    from backend.ai_service.knowledge import embed_pending

    try:
        return embed_pending(store.db)
    except GatewayError as error:
        logger.warning("Knowledge embedding skipped: %s", error.code)
        return 0


def grade_pending() -> int:
    """Queue submitted exams and pick up gradings cut off by a restart (audit B-04)."""
    from backend.grading_queue import recover

    return recover()


TICK_LEASE = "background-tick"


def run_tick() -> None:
    from backend.grading_queue import drop_lease, take_lease

    # Every server process has this loop; the lease lets one of them do the work each minute.
    owner = take_lease(TICK_LEASE, TICK_SECONDS * 0.9)
    if owner is None:
        return
    store.sync_all()
    _run_tick_work()


def _run_tick_work() -> None:
    run_scan()
    finish_expired_exams()
    grade_pending()
    retry_pending_submissions()
    purge_expired_answers()
    embed_knowledge()
    if os.getenv("CAREERADAPT_AUTO_LINK_CHECK", "true").lower() == "true":
        check_due_links()


async def _loop() -> None:
    while True:
        try:
            await run_in_threadpool(run_tick)
        except Exception:  # A failed tick must not stop later ones; the error is logged without content.
            logger.exception("Background tick failed")
        await asyncio.sleep(TICK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None if "pytest" in sys.modules else asyncio.create_task(_loop())
    yield
    if task:
        task.cancel()
