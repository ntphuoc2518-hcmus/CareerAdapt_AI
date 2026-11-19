"""Compare the learner's verified levels with every approved library JD.

The same gap engine as the Khoảng cách page runs once per JD, so the numbers for the current target
match that page exactly. Only verified levels count; a skill never measured is reported as such and
never treated as level 0. The result says how well measured skills meet a JD, not a chance of being hired.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from backend.clock import utcnow
from backend.store import store
from backend.targeting import default_requirements, evaluate_learner, resolve_target

SCOPE_NOTE = ("Mức đáp ứng chỉ tính trên các kỹ năng đã có bằng chứng và yêu cầu đã ánh xạ của từng JD. "
              "Đây không phải xác suất trúng tuyển.")


def _library_targets() -> list[dict]:
    """The latest approved, reachable, in-date version of each library JD that has mapped requirements."""
    today = utcnow().date().isoformat()
    rows = store.db.query(
        """SELECT j.jd_id, j.title, j.employer, j.role_level, v.jd_version, v.payload FROM job_descriptions j
           JOIN jd_versions v ON v.jd_id = j.jd_id
           WHERE j.origin = 'LIBRARY' AND v.review_status = 'APPROVED' AND COALESCE(v.link_status, 'OK') != 'BROKEN'
             AND (v.next_review_at IS NULL OR v.next_review_at >= ?)""", (today,))
    latest: dict[str, dict] = {}
    for row in rows:
        if row["jd_id"] not in latest or row["jd_version"] > latest[row["jd_id"]]["jd_version"]:
            latest[row["jd_id"]] = row
    targets = []
    for row in latest.values():
        payload = json.loads(row["payload"])
        requirements = payload.get("requirements_by_skill") or {}
        if not requirements:
            continue
        targets.append({
            "source_type": "JD_LIBRARY", "name": " — ".join(part for part in (payload.get("title") or row["title"], payload.get("employer") or row["employer"]) if part),
            "jd_id": row["jd_id"], "jd_version": row["jd_version"], "employer": payload.get("employer") or row["employer"], "role_level": payload.get("role_level") or row["role_level"],
            "requirements_by_skill": requirements, "additional_requirements": payload.get("additional_requirements", []),
        })
    return targets


def _summary(evaluation: dict, target: dict, current: Optional[dict]) -> dict:
    measured = [item for item in evaluation["skill_evaluations"] if item["status"] == "ASSESSED"]
    gaps = sorted((item for item in measured if (item["gap"] or 0) > 0), key=lambda item: (-item["gap"] * item["weight"], item["skill_code"]))
    return {
        "jd_id": target["jd_id"], "jd_version": target.get("jd_version"), "name": target["name"], "employer": target.get("employer"), "role_level": target.get("role_level"),
        "is_current": bool(current) and current.get("jd_id") == target["jd_id"] and current.get("jd_version") == target.get("jd_version"),
        "readiness": evaluation["readiness"], "coverage": evaluation["coverage"], "locked": evaluation["is_readiness_locked"], "lock_reasons": evaluation["lock_reasons"],
        "skills_met": sum(1 for item in measured if item["gap"] == 0), "skills_total": len(evaluation["skill_evaluations"]),
        "top_gaps": [{"skill_code": item["skill_code"], "current_level": item["current_level"], "target_level": item["target_level"], "gap": item["gap"]} for item in gaps[:2]],
        "unmeasured": [item["skill_code"] for item in evaluation["skill_evaluations"] if item["status"] != "ASSESSED"],
    }


def matches(user_id: uuid.UUID) -> dict:
    profile = store.get_or_create_profile(user_id)
    current = resolve_target(profile) if profile.get("target_jd") else None
    if not profile.get("assessed_skills"):
        return {"items": [], "has_evidence": False, "scope_note": SCOPE_NOTE}
    targets = _library_targets()
    targets.append({"source_type": "DEFAULT", "name": f"Bộ mục tiêu {store.career_metadata['career_title']} mặc định", "jd_id": "DEFAULT_DATA_ANALYST",
                    "jd_version": store.career_metadata["version_tag"], "requirements_by_skill": default_requirements(), "additional_requirements": []})
    items = [_summary(evaluate_learner(user_id, profile, target), target, current) for target in targets]
    # Unlocked results first, best match first; then the most evidence.
    items.sort(key=lambda item: (item["locked"], -(item["readiness"] or 0), -item["coverage"], item["name"]))
    return {"items": items, "has_evidence": True, "scope_note": SCOPE_NOTE}
