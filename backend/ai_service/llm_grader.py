"""Grading pipeline: machine checks first, AI explains after, the server decides last.

1. Deterministic verifiers and test cases run on every gradable submission.
2. The rule engine computes points, the pass decision and critical gates.
3. The optional AI writes feedback; its schema, criteria and evidence are validated by the server.
4. Only an accepted result writes evidence and updates the skill profile, in one transaction.

AI can only move a result to NEEDS_REVIEW (disagreement, fake evidence) or PENDING_RETRY (timeout,
invalid output). It can never add points. Each stage records a trace for later audit.
"""
from __future__ import annotations

import copy
import json
import math
import time
import uuid
from typing import Any, Optional

from backend.ai_service import assessment_provider
from backend.ai_service.assessment_provider import PROMPT_VERSION, RESPONSE_SCHEMA_VERSION, AssessmentProviderError, evaluate_submission
from backend.ai_service.security import anonymize_submission, verify_evidence_quote
from backend.clock import utcnow
from backend.database import dumps
from backend.engine.deterministic_grader import ASSESSMENT_RUBRICS, verify_submission
from backend.engine.rubric_engine import (
    BLUEPRINT_VERSION, RULE_VERSION, apply_critical_cap, get_blueprint, score_submission, validate_answers,
)
from backend.store import store
from backend.targeting import target_snapshot_for_record

MAX_GRADE_ATTEMPTS = 3
ACCEPTED_STATUSES = {"GRADED", "REVIEWED_APPROVED"}
RETRYABLE_STATUSES = {"RECEIVED", "PENDING_RETRY"}
FINAL_INVALID_STATUSES = {"INCOMPLETE", "INVALID"}


def format_user_prompt(task_id: str, submission_text: str) -> str:
    """Safe JSON envelope for diagnostics/documentation; submission stays untrusted data."""
    anonymized_text = anonymize_submission(submission_text)
    return json.dumps({"task_id": task_id, "student_submission_untrusted_data": anonymized_text}, ensure_ascii=False)


def _rubric_for_task(task_id: str) -> dict | None:
    task_rubric = ASSESSMENT_RUBRICS["tasks"].get(task_id.upper())
    if task_rubric and "same_as" in task_rubric:
        task_rubric = ASSESSMENT_RUBRICS["tasks"].get(task_rubric["same_as"])
    return task_rubric


def _criteria_snapshot(task: dict, task_id: str) -> list[dict]:
    configured = _rubric_for_task(task_id)
    criteria = []
    for item in task.get("skills_evaluated", []):
        code = item.get("skill_code")
        skill = store.get_skill(code) or {}
        skill_rubric = (configured or {}).get("skills", {}).get(code, {})
        criteria.append({
            "skill_code": code,
            "skill_name": skill.get("skill_name", code),
            "target_level": item.get("target_level"),
            "weight": item.get("weight"),
            "rubric_summary": copy.deepcopy(skill.get("rubric_summary", {})),
            "assessment_criteria": copy.deepcopy(skill_rubric.get("criteria", [])),
            "level_2_requires": copy.deepcopy(skill_rubric.get("level_2_requires", [])),
            "level_3_requires": copy.deepcopy(skill_rubric.get("level_3_requires", [])),
        })
    return criteria


def _overall_level(results: dict[str, dict], task: dict, key: str = "level") -> int | None:
    weighted = []
    for task_skill in task.get("skills_evaluated", []):
        code = task_skill.get("skill_code")
        score = results.get(code, {}).get(key)
        if score is None:
            continue
        weight = float(task_skill.get("weight", 1) or 0)
        weighted.append((int(score), weight if weight > 0 else 1.0))
    if not weighted:
        return None
    total_weight = sum(weight for _, weight in weighted)
    return math.floor(sum(level * weight for level, weight in weighted) / total_weight + 0.5)


def validate_ai_feedback(payload: Any, blueprint: dict, scoring: dict, answer_texts: list[str]) -> dict:
    """Check structure, criteria and evidence. Raises on invalid structure; flags review issues."""
    if not isinstance(payload, dict) or not isinstance(payload.get("criteria"), list):
        raise AssessmentProviderError("AI không trả về nhận xét theo từng tiêu chí.", "AI_INVALID_SCHEMA")
    expected = {item["criterion_id"] for item in blueprint["criteria"]}
    test_case_ids = {item["test_case_id"] for item in scoring["test_case_results"]}
    machine_levels = {item["criterion_id"]: item["level_proposed"] for item in scoring["criteria"]}
    normalized: dict[str, dict] = {}
    issues: list[dict] = []
    for item in payload["criteria"]:
        if not isinstance(item, dict):
            raise AssessmentProviderError("AI trả về tiêu chí sai định dạng.", "AI_INVALID_SCHEMA")
        criterion_id = item.get("criterion_id")
        if criterion_id not in expected or criterion_id in normalized:
            raise AssessmentProviderError("AI trả về mã tiêu chí không có trong rubric.", "AI_INVALID_SCHEMA")
        level = item.get("proposed_level")
        if not isinstance(level, int) or isinstance(level, bool) or level not in range(4):
            raise AssessmentProviderError("AI trả về mức ngoài thang 0–3.", "AI_INVALID_SCHEMA")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not isinstance(item.get("reason"), str):
            raise AssessmentProviderError("AI thiếu lý do hoặc bằng chứng.", "AI_INVALID_SCHEMA")
        checked = []
        for reference in evidence:
            if not isinstance(reference, dict) or reference.get("kind") not in {"quote", "test_case"} or not isinstance(reference.get("value"), str):
                raise AssessmentProviderError("AI trả về bằng chứng sai định dạng.", "AI_INVALID_SCHEMA")
            value = reference["value"]
            verified = value in test_case_ids if reference["kind"] == "test_case" else any(verify_evidence_quote(value, text) for text in answer_texts)
            checked.append({"kind": reference["kind"], "value": value[:400], "verified": verified})
            if not verified:
                issues.append({"code": "FAKE_EVIDENCE", "criterion_id": criterion_id, "message": f"Bằng chứng của tiêu chí {criterion_id} không tồn tại trong bài nộp hoặc kết quả kiểm tra."})
        if level > 0 and not checked:
            issues.append({"code": "MISSING_EVIDENCE", "criterion_id": criterion_id, "message": f"AI không nêu bằng chứng cho tiêu chí {criterion_id}."})
        if level > machine_levels[criterion_id]:
            issues.append({"code": "AI_ABOVE_MACHINE", "criterion_id": criterion_id, "message": f"AI đề xuất mức {level} cho {criterion_id}, cao hơn bộ kiểm tra (mức {machine_levels[criterion_id]})."})
        elif machine_levels[criterion_id] - level >= 2:
            issues.append({"code": "AI_BELOW_MACHINE", "criterion_id": criterion_id, "message": f"AI đề xuất mức {level} cho {criterion_id}, thấp hơn nhiều so với bộ kiểm tra (mức {machine_levels[criterion_id]})."})
        if item.get("needs_review") is True:
            issues.append({"code": "AI_REQUESTED_REVIEW", "criterion_id": criterion_id, "message": f"AI chưa đủ căn cứ để kết luận tiêu chí {criterion_id}."})
        normalized[criterion_id] = {
            "criterion_id": criterion_id, "proposed_level": level, "evidence": checked, "reason": item["reason"][:800],
            "uncertainties": str(item.get("uncertainties") or "")[:500], "needs_review": bool(item.get("needs_review")),
        }
    if set(normalized) != expected:
        raise AssessmentProviderError("AI bỏ sót tiêu chí trong rubric.", "AI_INVALID_SCHEMA")
    return {"criteria": normalized, "issues": issues, "overall_feedback": str(payload.get("overall_feedback") or "")[:2000]}


def _record_trace(submission_id: uuid.UUID, grade_attempt: int, provider: str, model: Optional[str], rubric_version: str,
                  validation_result: str, evidence_refs: Any = None, latency_ms: Optional[int] = None, error: Optional[str] = None) -> None:
    store.db.execute(
        """INSERT INTO ai_feedback_traces(trace_id, submission_id, grade_attempt, provider, model, prompt_version, rubric_version,
               response_schema_version, evidence_refs, validation_result, latency_ms, error, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), str(submission_id), grade_attempt, provider, model, PROMPT_VERSION, rubric_version, RESPONSE_SCHEMA_VERSION,
         dumps(evidence_refs) if evidence_refs is not None else None, validation_result, latency_ms, error, utcnow().isoformat()),
    )


def _run_ai(submission_id: uuid.UUID, grade_attempt: int, task: dict, blueprint: dict, scoring: dict, answers: dict[str, str], fault: Optional[str]) -> dict:
    """Return {"state": NOT_CONFIGURED|ACCEPTED|REVIEW|RETRY, ...}. Never touches the score."""
    rubric_version = blueprint["rubric_version"]
    provider = assessment_provider.config.LLM_PROVIDER.strip().lower()
    if fault == "timeout":
        _record_trace(submission_id, grade_attempt, "fault-injection", None, rubric_version, "FAILED", error="AI_TIMEOUT")
        return {"state": "RETRY", "error_code": "AI_TIMEOUT", "message": "Mô phỏng timeout của dịch vụ chấm."}
    if fault == "invalid_json":
        _record_trace(submission_id, grade_attempt, "fault-injection", None, rubric_version, "FAILED", error="AI_INVALID_JSON")
        return {"state": "RETRY", "error_code": "AI_INVALID_JSON", "message": "Mô phỏng AI trả về JSON sai cấu trúc."}
    if fault == "conflict":
        _record_trace(submission_id, grade_attempt, "fault-injection", None, rubric_version, "REJECTED", error="AI_ABOVE_MACHINE")
        return {"state": "REVIEW", "issues": [{"code": "AI_ABOVE_MACHINE", "message": "Mô phỏng xung đột giữa rubric xác định và đánh giá AI."}], "feedback": None}
    if fault == "hallucination":
        _record_trace(submission_id, grade_attempt, "fault-injection", None, rubric_version, "REJECTED", evidence_refs=[{"kind": "quote", "value": "ĐOẠN_BẰNG_CHỨNG_GIẢ", "verified": False}], error="FAKE_EVIDENCE")
        return {"state": "REVIEW", "issues": [{"code": "FAKE_EVIDENCE", "message": "Mô phỏng trích dẫn bằng chứng không tồn tại trong bài nộp."}], "feedback": None, "evidence_quote_verified": False}
    if not assessment_provider.is_enabled():
        _record_trace(submission_id, grade_attempt, provider or "mock", None, rubric_version, "NOT_CONFIGURED")
        return {"state": "NOT_CONFIGURED"}
    anonymized = {question: anonymize_submission(text) for question, text in answers.items()}
    started = time.monotonic()
    model = assessment_provider.active_model()
    try:
        output = evaluate_submission(task, blueprint, scoring, anonymized)
        validated = validate_ai_feedback(output, blueprint, scoring, list(anonymized.values()) + list(answers.values()))
    except AssessmentProviderError as error:
        _record_trace(submission_id, grade_attempt, provider, model, rubric_version, "FAILED", latency_ms=int((time.monotonic() - started) * 1000), error=error.code)
        return {"state": "RETRY", "error_code": error.code, "message": str(error)}
    evidence = [reference for item in validated["criteria"].values() for reference in item["evidence"]]
    state = "REVIEW" if validated["issues"] else "ACCEPTED"
    _record_trace(submission_id, grade_attempt, provider, model, rubric_version, "REJECTED" if validated["issues"] else "PASSED",
                  evidence_refs=evidence, latency_ms=int((time.monotonic() - started) * 1000), error=validated["issues"][0]["code"] if validated["issues"] else None)
    return {"state": state, "issues": validated["issues"], "feedback": validated, "provider": provider, "model": model}


def _deterministic_feedback(verifier: dict, task: dict, scoring: dict) -> dict:
    """Readable feedback built from test results when no AI is configured. Clearly labelled."""
    details = verifier.get("skill_results", {})
    strengths, gaps, skill_feedback = [], [], []
    for skill in task.get("skills_evaluated", []):
        code = skill.get("skill_code")
        item = details.get(code, {})
        passed = [check["description"] for check in item.get("checks", []) if check.get("passed") and check.get("weight", 0) > 0]
        if passed:
            strengths.append(f"{code} (mức {item.get('level', 0)}): {'; '.join(passed[:4])}.")
        gaps.extend(item.get("next_steps") or [])
        if item.get("feedback"):
            skill_feedback.append(f"{code} — mức {item.get('level', 0)}: {item['feedback']}")
    return {
        "provider": "deterministic", "model": None, "status": "DETERMINISTIC_ONLY", "proposed_level": verifier.get("proposed_level", 0),
        "feedback": " ".join(["Kết quả được tính bằng bộ kiểm tra xác định; dịch vụ AI chưa được cấu hình nên không có nhận xét AI."] + skill_feedback),
        "evidence_quote": "", "strengths": strengths, "areas_for_improvement": list(dict.fromkeys(gaps))[:12], "criteria_feedback": {},
        "skill_results": copy.deepcopy(details),
    }


def _write_trail(submission_id: uuid.UUID, scoring: dict, final_skills: dict[str, dict]) -> None:
    identifier = str(submission_id)
    store.db.execute("DELETE FROM test_case_results WHERE submission_id = ?", (identifier,))
    store.db.execute("DELETE FROM rubric_scores WHERE submission_id = ?", (identifier,))
    for item in scoring["test_case_results"]:
        store.db.execute(
            """INSERT INTO test_case_results(submission_id, test_case_id, version, criterion_id, expected_summary, actual_summary, passed,
                   points_awarded, points_max, failure_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, item["test_case_id"], item["version"], item["criterion_id"], item["expected_summary"], item["actual_summary"],
             int(item["passed"]), item["points_awarded"], item["points_max"], item["failure_code"]),
        )
    critical = {violation["gate_id"] for violation in scoring["critical_violations"]}
    for item in scoring["criteria"]:
        accepted = (final_skills.get(item.get("skill_code")) or {}).get("level")
        store.db.execute(
            """INSERT INTO rubric_scores(submission_id, criterion_id, version, skill_code, points_awarded, max_points, level_proposed, level_accepted,
                   critical_flag, rule_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, item["criterion_id"], item["version"], item.get("skill_code"), item["points_awarded"], item["max_points"], item["level_proposed"],
             accepted, int(bool(critical)), RULE_VERSION),
        )


def apply_skill_update(user_id: uuid.UUID, record: dict, skills: dict[str, dict], source_type: str = "ASSESSMENT") -> dict[str, dict]:
    """Record evidence and refresh current levels. Call inside the assessment's transaction."""
    profile = store.get_or_create_profile(user_id)
    target = record.get("target_snapshot") or {}
    now = record.get("created_at") or utcnow().isoformat()
    changes = {}
    for code, result in skills.items():
        level = int(result.get("level", 0))
        previous = profile.setdefault("assessed_skills", {}).get(code)
        store.add_skill_evidence(
            user_id, code, level, source_type, str(record["submission_id"]), score=float(result.get("score", 0) or 0), task_id=record.get("task_id"),
            task_version=record.get("task_version"), rubric_version=record.get("rubric_version"), jd_id=target.get("jd_id"), jd_version=target.get("jd_version"),
            mapping_version=target.get("mapping_version"), scope_note=record.get("scope_note"), created_at=now,
        )
        profile["assessed_skills"][code] = {
            "level": level, "score": float(result.get("score", 0) or 0), "confidence": result.get("confidence"),
            "submission_id": str(record["submission_id"]), "assessed_at": now, "assessment_status": "VERIFIED",
            "source_type": source_type, "task_id": record.get("task_id"), "scope_note": record.get("scope_note"),
        }
        changes[code] = {"previous_level": (previous or {}).get("level"), "current_level": level}
    profile["updated_at"] = now
    return changes


def _reassessment_comparison(user_id: uuid.UUID, task: dict, final_level: Optional[int], criteria_snapshot: list[dict]) -> Optional[dict]:
    comparable_to = task.get("comparable_to")
    if task.get("comparability_status") != "APPROVED" or not comparable_to or final_level is None:
        return None
    prior = max((
        item for item in store.assessments.values()
        if item.get("user_id") == user_id and item.get("task_id") == comparable_to and item.get("mode") == "ASSESSMENT"
        and item.get("status") in ACCEPTED_STATUSES and item.get("final_level") is not None
        and item.get("criteria_snapshot") == criteria_snapshot
    ), key=lambda item: item.get("created_at", ""), default=None)
    if not prior:
        return None
    return {
        "compared_submission_id": str(prior.get("submission_id")), "previous_task_id": comparable_to, "previous_level": prior.get("final_level"),
        "current_level": final_level, "level_change": final_level - prior.get("final_level"),
    }


def _base_record(submission_id: uuid.UUID, user_id: uuid.UUID, task_id: str, mode: str, task: dict, criteria_snapshot: list[dict], context: dict, status: str, blueprint: Optional[dict] = None) -> dict:
    blueprint = blueprint or get_blueprint(task_id) or {}
    profile = store.get_or_create_profile(user_id)
    return {
        "assessment_id": submission_id, "submission_id": submission_id, "user_id": user_id, "task_id": task_id, "mode": mode, "status": status,
        "task_title": task.get("title"), "task_version": task.get("content_version", 1), "blueprint_version": BLUEPRINT_VERSION,
        "rubric_version": blueprint.get("rubric_version"), "rule_version": RULE_VERSION, "criteria_snapshot": criteria_snapshot,
        "scope_note": blueprint.get("scope_note"), "target_snapshot": target_snapshot_for_record(profile), **context,
        "final_level": None, "final_score": None, "max_score": 100.0, "pass_threshold": blueprint.get("pass_threshold"), "passed": None,
        "per_skill_results": {}, "deterministic_result": None, "ai_result": None, "scoring": None, "created_at": utcnow().isoformat(),
    }


def _finish(record: dict) -> dict:
    """Persist a record and mirror its status on the submission, atomically."""
    submission = store.submissions.get(record["submission_id"])
    with store.db.transaction():
        store.save_assessment(record)
        if submission is not None:
            submission["status"] = record["status"]
            submission["final_level"] = record.get("final_level")
            store.save_submission(submission)
    return record


def grade_submission_orchestrator(
    submission_id: uuid.UUID,
    user_id: uuid.UUID,
    task_id: str,
    submission_text: str = "",
    mode: str = "ASSESSMENT",
    fault_injection: Optional[str] = None,
    task_snapshot: Optional[dict] = None,
    declared_tool: str = "Chưa khai báo",
    used_assistance: bool = False,
    assistance_details: str = "",
    answers: Optional[dict[str, str]] = None,
    exam: Optional[dict] = None,
) -> dict:
    """Run the full pipeline for one stored submission and return its assessment record.

    ``exam`` carries the one-off blueprint and verifier of a Career Adapt exam. An exam has one
    sitting, so nothing may hold it open: blanks score zero instead of voiding it, and an AI failure
    only drops the AI comment. The score is the machine's either way, and the result is flagged.
    """
    normalized_task_id = task_id.upper().strip()
    task = task_snapshot or store.get_task(normalized_task_id) or {"task_id": normalized_task_id, "title": normalized_task_id, "skills_evaluated": []}
    task.setdefault("task_id", normalized_task_id)
    blueprint = exam["blueprint"] if exam else get_blueprint(normalized_task_id)
    criteria_snapshot = _criteria_snapshot(task, normalized_task_id)
    context = {"declared_tool": declared_tool, "used_assistance": used_assistance, "assistance_details": assistance_details}
    submission = store.submissions.get(submission_id) or {}
    grade_attempt = int(submission.get("grade_attempts", 0)) + 1
    if submission:
        submission["grade_attempts"] = grade_attempt

    if blueprint is None:
        record = _base_record(submission_id, user_id, normalized_task_id, mode, task, criteria_snapshot, context, "NEEDS_REVIEW")
        record["review_reason"] = "Bài này chưa có rubric đã hiệu chuẩn. Cần quản trị viên duyệt thủ công."
        record["deterministic_result"] = verify_submission(normalized_task_id, submission_text, task)
        return _queue_review(_finish(record))

    # Structured answers are authoritative; a plain text submission is treated as one whole answer.
    structured = answers is not None
    if structured:
        validation = validate_answers(blueprint, answers)
        combined = _combined_text(blueprint, answers)
    else:
        validation = {"state": "VALID" if submission_text.strip() else "EMPTY", "blank_questions": [], "missing_outputs": [], "problems": [] if submission_text.strip() else ["Bài nộp không có câu trả lời nào."]}
        combined = submission_text
    if exam and validation["state"] == "EMPTY":
        validation = {**validation, "state": "VALID"}
    if validation["state"] != "VALID":
        status = "INCOMPLETE" if validation["state"] == "EMPTY" else "INVALID"
        record = _base_record(submission_id, user_id, normalized_task_id, mode, task, criteria_snapshot, context, status)
        record["validation"] = validation
        record["notes"] = " ".join(validation["problems"])
        return _finish(record)

    verifier = exam["verifier"] if exam else verify_submission(normalized_task_id, combined, task, answers if structured else None)
    if not verifier.get("supported"):
        record = _base_record(submission_id, user_id, normalized_task_id, mode, task, criteria_snapshot, context, "NEEDS_REVIEW")
        record["review_reason"] = "Bài này chưa có bộ kiểm tra xác định. Cần quản trị viên duyệt thủ công."
        record["deterministic_result"] = verifier
        return _queue_review(_finish(record))

    scoring = score_submission(blueprint, verifier, validation["blank_questions"])
    if exam:
        # A question proves at most its difficulty, and a critical error caps only that question's skill.
        for item in scoring["criteria"]:
            item["level_proposed"] = verifier["skill_results"][item["skill_code"]]["level"]
    else:
        apply_critical_cap(verifier.get("skill_results", {}), blueprint, scoring)
    final_skills = {code: copy.deepcopy(result) for code, result in verifier.get("skill_results", {}).items()}
    for result in final_skills.values():
        result.setdefault("ai_level", result.get("level"))
    final_level = _overall_level(final_skills, task)

    outcome = _run_ai(submission_id, grade_attempt, task, blueprint, scoring, answers if structured else {"FULL_TEXT": combined}, fault_injection)
    record = _base_record(submission_id, user_id, normalized_task_id, mode, task, criteria_snapshot, context, "GRADED", blueprint)
    if exam and outcome["state"] in {"RETRY", "REVIEW"}:
        issue = (outcome.get("issues") or [{}])[0]
        record["ai_flag"] = {"code": outcome.get("error_code") or issue.get("code", "AI_REJECTED"), "message": outcome.get("message") or issue.get("message", "Nhận xét AI không đạt kiểm tra nên đã bị loại.")}
        outcome = {"state": "NOT_CONFIGURED"}
    record.update({
        "validation": validation, "deterministic_result": verifier, "scoring": scoring, "final_score": scoring["final_score"], "passed": scoring["passed"],
        "per_skill_results": final_skills, "evidence_quote_verified": outcome.get("evidence_quote_verified", True), "grade_attempts": grade_attempt,
    })

    if outcome["state"] == "RETRY":
        exhausted = grade_attempt >= MAX_GRADE_ATTEMPTS
        record["status"] = "NEEDS_REVIEW" if exhausted else "PENDING_RETRY"
        record["passed"] = None
        record["ai_error_code"] = outcome["error_code"]
        record["notes"] = outcome["message"]
        record["provisional_score"] = scoring["final_score"]
        record["final_score"] = None
        with store.db.transaction():
            _write_trail(submission_id, scoring, {})
            _finish(record)
        if exhausted:
            record["review_reason"] = f"AI không phản hồi hợp lệ sau {grade_attempt} lần thử ({outcome['error_code']}). Cần người duyệt xác nhận kết quả."
            return _queue_review(_finish(record))
        return record

    if outcome["state"] == "REVIEW":
        issues = outcome["issues"]
        record["status"] = "NEEDS_REVIEW"
        record["review_issues"] = issues
        record["review_reason"] = "; ".join(issue["message"] for issue in issues[:3])
        record["ai_result"] = _ai_result(outcome, verifier, task)
        record["final_level_proposed"] = final_level
        with store.db.transaction():
            _write_trail(submission_id, scoring, {})
            _finish(record)
        return _queue_review(record)

    record["ai_result"] = _ai_result(outcome, verifier, task) if outcome["state"] == "ACCEPTED" else _deterministic_feedback(verifier, task, scoring)
    record["final_level"] = final_level
    record["reassessment_comparison"] = _reassessment_comparison(user_id, task, final_level, criteria_snapshot) if mode == "ASSESSMENT" else None
    # Accepted result: trail, evidence and profile commit together or not at all. The learner's lock
    # (already held inside a request) keeps another server process from changing the same profile meanwhile.
    with store.user_scope(user_id):
        profile_before = copy.deepcopy(store.get_or_create_profile(user_id))
        try:
            with store.db.transaction():
                _write_trail(submission_id, scoring, final_skills)
                if mode == "ASSESSMENT":
                    record["skill_changes"] = apply_skill_update(user_id, record, final_skills)
                    store.persist_user_runtime(user_id)
                _finish(record)
        except Exception:
            store.profiles[user_id] = profile_before
            raise
    return record


def _combined_text(blueprint: dict, answers: dict[str, str]) -> str:
    return "\n".join(f"-- {item['label']}\n{answers.get(item['question_id'], '')}" for item in blueprint["questions"])


def _ai_result(outcome: dict, verifier: dict, task: dict) -> dict:
    feedback = outcome.get("feedback") or {}
    criteria = feedback.get("criteria") or {}
    return {
        "provider": outcome.get("provider", "fault-injection"), "model": outcome.get("model"), "status": "COMPLETED" if feedback else "REJECTED",
        "proposed_level": verifier.get("proposed_level", 0), "feedback": feedback.get("overall_feedback", ""), "criteria_feedback": criteria,
        "strengths": [], "areas_for_improvement": [issue["message"] for issue in (feedback.get("issues") or [])],
        "evidence_quote": next((ref["value"] for item in criteria.values() for ref in item["evidence"] if ref["kind"] == "quote" and ref["verified"]), ""),
        "skill_results": copy.deepcopy(verifier.get("skill_results", {})),
    }


def _queue_review(record: dict) -> dict:
    item = {
        "submission_id": record["submission_id"], "user_id": record["user_id"], "task_id": record["task_id"],
        "deterministic_level": (record.get("deterministic_result") or {}).get("proposed_level"),
        "ai_level": (record.get("ai_result") or {}).get("proposed_level"),
        "per_skill_results": copy.deepcopy(record.get("per_skill_results", {})),
        "reason": record.get("review_reason") or "Cần người chấm xác nhận.", "created_at": record.get("created_at"),
    }
    if not any(existing["submission_id"] == record["submission_id"] for existing in store.review_queue):
        store.review_queue.append(item)
    record["review_item"] = {**item, "submission_id": str(item["submission_id"]), "user_id": str(item["user_id"])}
    store.save_assessment(record)
    return record
