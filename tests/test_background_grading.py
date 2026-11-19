"""Audit B-04: submitting returns at once and grading runs on a bounded background queue."""
from __future__ import annotations

import threading
import time

import pytest

from backend import exam_service, grading_queue
from backend.store import store
from v5_helpers import P, STUDENT, answer_all, client, step, to_exam


@pytest.fixture(autouse=True)
def background():
    store.reset()
    grading_queue.use_background(True)
    yield
    grading_queue.wait_idle()
    grading_queue.use_background(False)


def _attempt():
    return store.db.one("SELECT attempt_id, status FROM exam_attempts ORDER BY started_at DESC LIMIT 1")


def test_submit_returns_before_grading_and_the_result_arrives_later():
    exam = to_exam()
    answer_all(exam)
    started = time.monotonic()
    response = client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    elapsed = time.monotonic() - started
    assert response.status_code == 200 and response.json()["status"] in ("SUBMITTED", "GRADING")
    assert elapsed < 2.0
    # Locked at once: answers can no longer change while grading runs.
    assert client.put(f"{P}/exam/responses/Q1", json={"text": "x"}, headers=STUDENT).status_code == 409
    assert grading_queue.wait_idle()
    assert _attempt()["status"] == "GRADED" and step() == "RESULT"
    review = client.get(f"{P}/exam/review", headers=STUDENT).json()
    assert review["score"] == 100


def test_a_second_submit_while_grading_does_not_grade_twice():
    exam = to_exam()
    answer_all(exam)
    first = client.post(f"{P}/exam/submit", json={}, headers=STUDENT).json()
    second = client.post(f"{P}/exam/submit", json={}, headers=STUDENT).json()
    assert first["is_duplicate"] is False and second["is_duplicate"] is True
    grading_queue.wait_idle()
    attempt = _attempt()
    assert store.db.one("SELECT COUNT(*) AS n FROM final_assessments WHERE task_id LIKE ?", (f"EXAM-{attempt['attempt_id'][:8].upper()}%",))["n"] == 1


def test_a_grading_cut_off_by_a_restart_is_picked_up_again():
    exam = to_exam()
    answer_all(exam)
    grading_queue.use_background(False)
    attempt_id = exam["attempt_id"]
    # As if the server stopped mid-grading: the row says GRADING but no worker owns it.
    store.db.execute("UPDATE exam_attempts SET status = 'GRADING', submitted_at = started_at WHERE attempt_id = ?", (attempt_id,))
    assert grading_queue.recover() == 1
    assert _attempt()["status"] == "GRADED" and step() == "RESULT"
    assert grading_queue.recover() == 0


def test_the_state_page_reports_grading_until_it_is_done():
    exam = to_exam()
    answer_all(exam)
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    state = client.get(f"{P}/state", headers=STUDENT).json()
    assert state["run"]["step"] in ("EXAM", "RESULT") and state["exam_status"] in ("SUBMITTED", "GRADING", "GRADED")
    grading_queue.wait_idle()
    assert client.get(f"{P}/state", headers=STUDENT).json()["exam_status"] == "GRADED"


def test_no_more_jobs_run_at_once_than_there_are_workers():
    running, peak, lock = [0], [0], threading.Lock()

    def job():
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.2)
        with lock:
            running[0] -= 1

    for index in range(grading_queue.WORKERS * 3):
        assert grading_queue.enqueue(f"test:{index}", job)
    assert grading_queue.enqueue("test:0", job) is False  # already queued
    assert grading_queue.wait_idle()
    assert peak[0] <= grading_queue.WORKERS


def test_a_failing_job_is_logged_and_frees_its_slot():
    def boom():
        raise RuntimeError("sandbox unavailable")

    assert grading_queue.enqueue("test:fail", boom)
    grading_queue.wait_idle()
    assert not grading_queue.is_active("test:fail")
    assert grading_queue.enqueue("test:fail", lambda: None)


def test_inline_mode_still_grades_inside_the_request():
    grading_queue.use_background(False)
    exam = to_exam()
    answer_all(exam)
    assert client.post(f"{P}/exam/submit", json={}, headers=STUDENT).json()["status"] == "GRADED"
    assert exam_service is not None
