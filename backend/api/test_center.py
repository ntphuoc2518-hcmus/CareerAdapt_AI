"""Test Center: timed objective tests, server-side scoring and evaluation reports.

Learner endpoints (/api/v1/tests/...):
- GET  /tests/blueprints                         catalog with attempt policy status
- POST /tests/attempts                           start (or resume) an attempt with a frozen random form
- GET  /tests/attempts                           my attempt history with scores
- GET  /tests/attempts/{id}                      resume state; auto-submits once time is up
- PUT  /tests/attempts/{id}/responses/{item_id}  autosave one answer (practice returns feedback)
- POST /tests/attempts/{id}/events               integrity events (focus lost, paste)
- POST /tests/attempts/{id}/submit               score and evaluate
- GET  /tests/attempts/{id}/report               evaluation report with item review

Admin endpoints (/api/v1/admin/tests/...): item bank CRUD, item analysis, results, CSV export.

The answer key never leaves the server before an attempt is submitted, and the
server clock decides when an attempt expires.
"""
from __future__ import annotations

import copy
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.auth import AuthenticatedUser, get_current_user, require_admin_user
from backend.engine.test_engine import (
    assemble_form, build_evaluation, integrity_review, item_analysis, public_item,
    score_attempt, score_item, time_analytics,
)
from backend.store import store

router = APIRouter(tags=["Test Center - Kiểm tra năng lực"])

GRACE_SECONDS = 30  # network latency allowance after the visible timer reaches zero
MAX_EVENTS_PER_ATTEMPT = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _blueprint_or_404(blueprint_id: str) -> dict:
    blueprint = store.get_blueprint(blueprint_id)
    if not blueprint or blueprint.get("status", "PUBLISHED") != "PUBLISHED":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài kiểm tra.")
    return blueprint


def _attempt_or_404(attempt_id: str, user: AuthenticatedUser) -> dict:
    attempt = store.test_attempts.get(attempt_id)
    if not attempt or (attempt["user_id"] != str(user.user_id) and user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lượt làm bài.")
    return attempt


def _attempts_last_24h(user_id: uuid.UUID, blueprint_id: str) -> list[dict]:
    since = _now() - timedelta(hours=24)
    return [a for a in store.user_test_attempts(user_id) if a["blueprint_id"] == blueprint_id and _parse(a["started_at"]) >= since]


def _remaining_seconds(attempt: dict) -> Optional[int]:
    if not attempt.get("expires_at"):
        return None
    return max(0, int((_parse(attempt["expires_at"]) - _now()).total_seconds()))


def _is_expired(attempt: dict) -> bool:
    if not attempt.get("expires_at") or attempt["status"] != "IN_PROGRESS":
        return False
    return _now() > _parse(attempt["expires_at"]) + timedelta(seconds=GRACE_SECONDS)


def _finalize(attempt: dict, auto_submitted: bool = False) -> dict:
    """Score, evaluate and lock an attempt. Idempotent for already submitted attempts."""
    if attempt["status"] != "IN_PROGRESS":
        return attempt
    blueprint = attempt["blueprint_snapshot"]
    score = score_attempt(attempt["form_items"], attempt["responses"], store.skills, store.difficulty_points)
    user_id = uuid.UUID(attempt["user_id"])
    previous = next((a for a in reversed(store.user_test_attempts(user_id))
                     if a["blueprint_id"] == attempt["blueprint_id"] and a["status"] == "SUBMITTED" and a["attempt_id"] != attempt["attempt_id"]), None)
    store.sync_all()
    cohort = [a["score"]["composite_score"] for a in store.test_attempts.values()
              if a["blueprint_id"] == attempt["blueprint_id"] and a["status"] == "SUBMITTED" and a["mode"] == "ASSESSMENT"]
    previous_summary = None
    if previous:
        previous_summary = {"attempt_id": previous["attempt_id"], "submitted_at": previous["submitted_at"],
                            "composite_score": previous["score"]["composite_score"], "skills": previous["score"]["skills"]}
    submitted_at = _now()
    elapsed = (submitted_at - _parse(attempt["started_at"])).total_seconds()
    if attempt.get("expires_at"):
        elapsed = min(elapsed, blueprint["time_limit_minutes"] * 60)
    attempt.update({
        "status": "SUBMITTED",
        "submitted_at": submitted_at.isoformat(),
        "auto_submitted": auto_submitted,
        "score": score,
        "evaluation": build_evaluation(score, blueprint, store.activities, previous_summary, cohort),
        "integrity": integrity_review(score["items"], attempt.get("events", []), auto_submitted),
        "timing": time_analytics(score["items"], blueprint["time_limit_minutes"] * 60, elapsed),
    })
    store.add_history_event(user_id, "TEST_SUBMITTED",
                            f"{blueprint['title']}: {score['composite_score']:.1f}/100 ({attempt['evaluation']['band']['label']})")
    store.persist_user_runtime(user_id)
    return attempt


def _refresh(attempt: dict) -> dict:
    if _is_expired(attempt):
        _finalize(attempt, auto_submitted=True)
    return attempt


def _attempt_state(attempt: dict) -> dict:
    """Learner-facing view of an attempt in progress (no answer key)."""
    practice = attempt["mode"] == "PRACTICE"
    items = []
    for index, entry in enumerate(attempt["form"]):
        item = next(i for i in attempt["form_items"] if i["item_id"] == entry["item_id"])
        view = public_item(item, entry["option_order"])
        view["number"] = index + 1
        saved = attempt["responses"].get(item["item_id"])
        view["response"] = saved.get("value") if saved else None
        view["flagged"] = bool(saved and saved.get("flagged"))
        if practice and saved and saved.get("checked"):
            view["feedback"] = _feedback(item, saved.get("value"))
        items.append(view)
    return {
        "attempt_id": attempt["attempt_id"],
        "blueprint_id": attempt["blueprint_id"],
        "title": attempt["blueprint_snapshot"]["title"],
        "mode": attempt["mode"],
        "status": attempt["status"],
        "started_at": attempt["started_at"],
        "expires_at": attempt.get("expires_at"),
        "remaining_seconds": _remaining_seconds(attempt),
        "server_time": _now().isoformat(),
        "items": items,
        "answered": sum(1 for r in attempt["responses"].values() if r.get("value") not in (None, "", [])),
        "total_items": len(items),
    }


def _feedback(item: dict, value: Any) -> dict:
    credit = score_item(item, value)
    return {"credit": credit, "correct": credit >= 1.0, "answer": item["answer"], "explanation": item.get("explanation", "")}


def _summary(attempt: dict) -> dict:
    data = {
        "attempt_id": attempt["attempt_id"],
        "blueprint_id": attempt["blueprint_id"],
        "title": attempt["blueprint_snapshot"]["title"],
        "mode": attempt["mode"],
        "status": attempt["status"],
        "started_at": attempt["started_at"],
        "submitted_at": attempt.get("submitted_at"),
    }
    if attempt["status"] == "SUBMITTED":
        data.update({
            "composite_score": attempt["score"]["composite_score"],
            "passed": attempt["evaluation"]["passed"],
            "band": attempt["evaluation"]["band"],
            "skills": {code: {"percent": s["percent"], "estimated_level": s["estimated_level"]} for code, s in attempt["score"]["skills"].items()},
            "integrity_status": attempt["integrity"]["status"],
        })
    else:
        data["remaining_seconds"] = _remaining_seconds(attempt)
    return data


def _report(attempt: dict) -> dict:
    blueprint = attempt["blueprint_snapshot"]
    show_answers = blueprint.get("show_answers_after_submit", True)
    review = []
    results = {r["item_id"]: r for r in attempt["score"]["items"]}
    for index, entry in enumerate(attempt["form"]):
        item = next(i for i in attempt["form_items"] if i["item_id"] == entry["item_id"])
        view = public_item(item, entry["option_order"])
        view["number"] = index + 1
        view["response"] = (attempt["responses"].get(item["item_id"]) or {}).get("value")
        view.update({k: results[item["item_id"]][k] for k in ("credit", "points_earned", "points_possible", "time_spent_seconds")})
        if show_answers:
            view["answer"] = item["answer"]
            view["explanation"] = item.get("explanation", "")
        review.append(view)
    return {
        **_summary(attempt),
        "blueprint": {k: blueprint.get(k) for k in ("blueprint_id", "title", "description", "time_limit_minutes", "pass_mark_percent", "core_skill_min_percent")},
        "bank_version": attempt["bank_version"],
        "auto_submitted": attempt.get("auto_submitted", False),
        "score": {k: v for k, v in attempt["score"].items() if k != "items"},
        "evaluation": attempt["evaluation"],
        "integrity": attempt["integrity"],
        "timing": attempt["timing"],
        "review": review,
        "certificate": _certificate(attempt) if attempt["evaluation"]["passed"] and attempt["mode"] == "ASSESSMENT" else None,
    }


def _certificate(attempt: dict) -> dict:
    return {
        "certificate_id": f"CA-{attempt['attempt_id'][:8].upper()}",
        "issued_at": attempt["submitted_at"],
        "title": attempt["blueprint_snapshot"]["title"],
        "score": attempt["score"]["composite_score"],
        "band": attempt["evaluation"]["band"]["label"],
        "verification_note": "Chứng nhận kết quả bài kiểm tra kiến thức; năng lực thực hành được xác minh riêng qua bài thực hành có bằng chứng.",
    }


# ---------------------------------------------------------------------------
# Learner endpoints
# ---------------------------------------------------------------------------

class StartAttemptRequest(BaseModel):
    blueprint_id: str = Field(min_length=1, max_length=64)


class SaveResponseRequest(BaseModel):
    value: Any = None
    time_spent_seconds: float = Field(default=0, ge=0, le=36000)
    flagged: bool = False
    check: bool = Field(default=False, description="Chỉ dùng trong chế độ luyện tập: xem đáp án ngay")


class IntegrityEvent(BaseModel):
    type: Literal["focus_lost", "focus_returned", "paste", "fullscreen_exit"]
    detail: str = Field(default="", max_length=200)


@router.get("/tests/blueprints")
def list_blueprints(current_user: AuthenticatedUser = Depends(get_current_user)):
    catalog = []
    for blueprint in store.test_blueprints:
        if blueprint.get("status", "PUBLISHED") != "PUBLISHED":
            continue
        recent = _attempts_last_24h(current_user.user_id, blueprint["blueprint_id"])
        limit = blueprint.get("max_attempts_per_24h", 0)
        submitted = [a for a in store.user_test_attempts(current_user.user_id) if a["blueprint_id"] == blueprint["blueprint_id"] and a["status"] == "SUBMITTED"]
        in_progress = next((a for a in store.user_test_attempts(current_user.user_id)
                            if a["blueprint_id"] == blueprint["blueprint_id"] and _refresh(a)["status"] == "IN_PROGRESS"), None)
        catalog.append({
            **{k: blueprint.get(k) for k in ("blueprint_id", "title", "description", "mode", "time_limit_minutes", "pass_mark_percent", "core_skill_min_percent", "max_attempts_per_24h")},
            "skills": list(blueprint["matrix"].keys()),
            "item_count": sum(sum(levels.values()) for levels in blueprint["matrix"].values()),
            "attempts_last_24h": len(recent),
            "attempts_remaining": None if not limit else max(0, limit - len(recent)),
            "best_score": max((a["score"]["composite_score"] for a in submitted), default=None),
            "last_score": submitted[-1]["score"]["composite_score"] if submitted else None,
            "in_progress_attempt_id": in_progress["attempt_id"] if in_progress else None,
        })
    return {"bank_version": store.question_bank_version, "blueprints": catalog}


@router.post("/tests/attempts", status_code=status.HTTP_201_CREATED)
def start_attempt(body: StartAttemptRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    blueprint = _blueprint_or_404(body.blueprint_id)
    # Resume rather than open a second concurrent attempt of the same test.
    for attempt in store.user_test_attempts(current_user.user_id):
        if attempt["blueprint_id"] == blueprint["blueprint_id"] and _refresh(attempt)["status"] == "IN_PROGRESS":
            return {**_attempt_state(attempt), "resumed": True}
    limit = blueprint.get("max_attempts_per_24h", 0)
    if limit and len(_attempts_last_24h(current_user.user_id, blueprint["blueprint_id"])) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Bạn đã dùng hết {limit} lượt làm bài này trong 24 giờ. Hãy ôn tập rồi quay lại sau.")
    # A contributor never gets their own question, unless the bank has no other for that cell yet.
    own = str(current_user.user_id)
    try:
        form = assemble_form(blueprint, [item for item in store.question_items if item.get("author_id") != own])
    except ValueError:
        try:
            form = assemble_form(blueprint, store.question_items)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    started = _now()
    minutes = blueprint.get("time_limit_minutes", 0)
    attempt = {
        "attempt_id": str(uuid.uuid4()),
        "user_id": str(current_user.user_id),
        "blueprint_id": blueprint["blueprint_id"],
        "blueprint_snapshot": copy.deepcopy(blueprint),
        "bank_version": store.question_bank_version,
        "mode": blueprint.get("mode", "ASSESSMENT"),
        "status": "IN_PROGRESS",
        "started_at": started.isoformat(),
        "expires_at": (started + timedelta(minutes=minutes)).isoformat() if minutes else None,
        "form": form,
        # Freeze item content so later bank edits cannot change how this attempt is scored.
        "form_items": [copy.deepcopy(store.get_question_item(entry["item_id"])) for entry in form],
        "responses": {},
        "events": [],
    }
    store.test_attempts[attempt["attempt_id"]] = attempt
    store.add_history_event(current_user.user_id, "TEST_STARTED", blueprint["title"])
    store.persist_user_runtime(current_user.user_id)
    return {**_attempt_state(attempt), "resumed": False}


@router.get("/tests/attempts")
def list_my_attempts(current_user: AuthenticatedUser = Depends(get_current_user)):
    attempts = [_refresh(a) for a in store.user_test_attempts(current_user.user_id)]
    return {"attempts": [_summary(a) for a in reversed(attempts)]}


@router.get("/tests/attempts/{attempt_id}")
def get_attempt(attempt_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    attempt = _refresh(_attempt_or_404(attempt_id, current_user))
    if attempt["status"] == "SUBMITTED":
        return {"attempt_id": attempt_id, "status": "SUBMITTED", "auto_submitted": attempt.get("auto_submitted", False)}
    return _attempt_state(attempt)


@router.put("/tests/attempts/{attempt_id}/responses/{item_id}")
def save_response(attempt_id: str, item_id: str, body: SaveResponseRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    attempt = _refresh(_attempt_or_404(attempt_id, current_user))
    if attempt["status"] != "IN_PROGRESS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lượt làm bài đã kết thúc; câu trả lời không được lưu.")
    item = next((i for i in attempt["form_items"] if i["item_id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Câu hỏi không thuộc đề này.")
    value = body.value
    if item["type"] in ("multiple", "ordering"):
        if value is not None and (not isinstance(value, list) or not all(isinstance(v, str) for v in value) or len(value) > 20):
            raise HTTPException(status_code=422, detail="Câu trả lời phải là danh sách lựa chọn.")
        valid = {o["id"] for o in item["options"]}
        if value and not set(value) <= valid:
            raise HTTPException(status_code=422, detail="Lựa chọn không hợp lệ.")
    elif item["type"] == "single":
        # Checked as a string first: a list or object here is malformed input, not a crash.
        if value is not None and (not isinstance(value, str) or value not in {o["id"] for o in item["options"]}):
            raise HTTPException(status_code=422, detail="Lựa chọn không hợp lệ.")
    elif item["type"] == "numeric" and value is not None:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise HTTPException(status_code=422, detail="Câu trả lời phải là một số.")
        if len(str(value)) > 40:
            raise HTTPException(status_code=422, detail="Giá trị số quá dài.")
    saved = attempt["responses"].get(item_id, {})
    practice = attempt["mode"] == "PRACTICE"
    if practice and saved.get("checked"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Câu này đã xem đáp án, không thể sửa.")
    attempt["responses"][item_id] = {
        "value": value,
        # Accumulate time across visits; the client reports time spent in this visit.
        "time_spent_seconds": round(saved.get("time_spent_seconds", 0) + body.time_spent_seconds, 1),
        "flagged": body.flagged,
        "checked": practice and body.check,
        "saved_at": _now().isoformat(),
    }
    store.persist_user_runtime(uuid.UUID(attempt["user_id"]))
    result = {"saved": True, "remaining_seconds": _remaining_seconds(attempt)}
    if practice and body.check:
        result["feedback"] = _feedback(item, value)
    return result


@router.post("/tests/attempts/{attempt_id}/events")
def record_event(attempt_id: str, body: IntegrityEvent, current_user: AuthenticatedUser = Depends(get_current_user)):
    attempt = _refresh(_attempt_or_404(attempt_id, current_user))
    if attempt["status"] == "IN_PROGRESS" and len(attempt["events"]) < MAX_EVENTS_PER_ATTEMPT:
        attempt["events"].append({"type": body.type, "detail": body.detail, "at": _now().isoformat()})
        store.persist_user_runtime(uuid.UUID(attempt["user_id"]))
    return {"recorded": True}


@router.post("/tests/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    attempt = _attempt_or_404(attempt_id, current_user)
    _finalize(attempt, auto_submitted=_is_expired(attempt))
    return _report(attempt)


@router.get("/tests/attempts/{attempt_id}/report")
def get_report(attempt_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    attempt = _refresh(_attempt_or_404(attempt_id, current_user))
    if attempt["status"] != "SUBMITTED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bài chưa nộp nên chưa có báo cáo.")
    return _report(attempt)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

class QuestionItemRequest(BaseModel):
    item_id: str = Field(min_length=3, max_length=32, pattern=r"^[A-Z0-9_-]+$")
    skill_code: str
    level: int = Field(ge=1, le=3)
    type: Literal["single", "multiple", "numeric", "ordering"]
    topic: str = Field(min_length=1, max_length=80)
    stem: str = Field(min_length=5, max_length=2000)
    code: Optional[str] = Field(default=None, max_length=2000)
    options: list[dict] = Field(default_factory=list)
    answer: Any
    tolerance: float = Field(default=0, ge=0)
    unit: Optional[str] = Field(default=None, max_length=20)
    explanation: str = Field(default="", max_length=2000)
    status: Literal["ACTIVE", "RETIRED", "DRAFT"] = "ACTIVE"


def _validate_item(body: QuestionItemRequest) -> dict:
    if not store.get_skill(body.skill_code):
        raise HTTPException(status_code=422, detail="Mã kỹ năng không tồn tại.")
    item = body.model_dump(exclude_none=True)
    option_ids = [o.get("id") for o in body.options]
    if body.type in ("single", "multiple", "ordering"):
        if len(body.options) < 2 or any(not o.get("id") or not o.get("text") for o in body.options) or len(set(option_ids)) != len(option_ids):
            raise HTTPException(status_code=422, detail="Cần ít nhất 2 lựa chọn, mỗi lựa chọn có id duy nhất và nội dung.")
        item["options"] = [{"id": str(o["id"]), "text": str(o["text"])} for o in body.options]
    if body.type == "single" and body.answer not in option_ids:
        raise HTTPException(status_code=422, detail="Đáp án phải là id của một lựa chọn.")
    if body.type == "multiple" and (not isinstance(body.answer, list) or not body.answer or not set(body.answer) <= set(option_ids)):
        raise HTTPException(status_code=422, detail="Đáp án phải là danh sách id lựa chọn.")
    if body.type == "ordering" and (not isinstance(body.answer, list) or sorted(body.answer) != sorted(option_ids)):
        raise HTTPException(status_code=422, detail="Đáp án sắp xếp phải chứa đủ mọi id lựa chọn.")
    if body.type == "numeric":
        try:
            item["answer"] = float(body.answer)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Đáp án dạng số không hợp lệ.")
        item.pop("options", None)
    return item


def _submitted_assessments() -> list[dict]:
    store.sync_all()
    return [a for a in store.test_attempts.values() if a["status"] == "SUBMITTED" and a["mode"] == "ASSESSMENT"]


@router.get("/admin/tests/items")
def admin_list_items(admin: AuthenticatedUser = Depends(require_admin_user)):
    return {"bank_version": store.question_bank_version, "items": store.question_items}


@router.post("/admin/tests/items", status_code=status.HTTP_201_CREATED)
def admin_create_item(body: QuestionItemRequest, admin: AuthenticatedUser = Depends(require_admin_user)):
    if store.get_question_item(body.item_id):
        raise HTTPException(status_code=409, detail="Mã câu hỏi đã tồn tại.")
    item = store.save_question_item(_validate_item(body))
    return {**item, "bank_version": store.question_bank_version}


@router.put("/admin/tests/items/{item_id}")
def admin_update_item(item_id: str, body: QuestionItemRequest, admin: AuthenticatedUser = Depends(require_admin_user)):
    existing = store.get_question_item(item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi.")
    if body.item_id != item_id:
        raise HTTPException(status_code=422, detail="Không được đổi mã câu hỏi.")
    item = store.save_question_item(_validate_item(body))
    return {**item, "bank_version": store.question_bank_version}


@router.get("/admin/tests/item-analysis")
def admin_item_analysis(admin: AuthenticatedUser = Depends(require_admin_user)):
    attempts = _submitted_assessments()
    return {"attempts_analyzed": len(attempts), "items": item_analysis(store.question_items, attempts)}


@router.get("/admin/tests/results")
def admin_results(blueprint_id: Optional[str] = None, admin: AuthenticatedUser = Depends(require_admin_user)):
    attempts = [a for a in _submitted_assessments() if not blueprint_id or a["blueprint_id"] == blueprint_id]
    scores = sorted(a["score"]["composite_score"] for a in attempts)
    stats = None
    if scores:
        n = len(scores)
        mean = sum(scores) / n
        stats = {
            "count": n,
            "mean": round(mean, 2),
            "median": round(scores[n // 2] if n % 2 else (scores[n // 2 - 1] + scores[n // 2]) / 2, 2),
            "std_dev": round((sum((s - mean) ** 2 for s in scores) / n) ** 0.5, 2),
            "pass_rate": round(100 * sum(1 for a in attempts if a["evaluation"]["passed"]) / n, 1),
            "flagged": sum(1 for a in attempts if a["integrity"]["status"] != "OK"),
            "distribution": [sum(1 for s in scores if lo <= s < lo + 20 or (lo == 80 and s == 100)) for lo in (0, 20, 40, 60, 80)],
        }
    rows = [{**_summary(a), "user_id": a["user_id"], "integrity_flags": a["integrity"]["flags"]} for a in sorted(attempts, key=lambda a: a["submitted_at"], reverse=True)]
    return {"statistics": stats, "results": rows}


@router.get("/admin/tests/results.csv")
def admin_results_csv(admin: AuthenticatedUser = Depends(require_admin_user)):
    skill_codes = [s["skill_code"] for s in store.skills]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["attempt_id", "user_id", "blueprint_id", "submitted_at", "composite_score", "passed", "band", "integrity"] + [f"{c}_percent" for c in skill_codes] + [f"{c}_level" for c in skill_codes])
    for a in sorted(_submitted_assessments(), key=lambda a: a["submitted_at"]):
        skills = a["score"]["skills"]
        writer.writerow([a["attempt_id"], a["user_id"], a["blueprint_id"], a["submitted_at"], a["score"]["composite_score"],
                         a["evaluation"]["passed"], a["evaluation"]["band"]["label"], a["integrity"]["status"]]
                        + [skills.get(c, {}).get("percent", "") for c in skill_codes]
                        + [skills.get(c, {}).get("estimated_level", "") for c in skill_codes])
    # BOM so Excel opens Vietnamese text correctly.
    return StreamingResponse(iter(["﻿" + buffer.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=test_results.csv"})
