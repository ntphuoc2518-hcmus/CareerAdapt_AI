"""Resolve the skill target a learner is measured against, and the skills evaluated for it.

Every gap, roadmap and assessment record points back to the JD version and mapping version
returned here, so an old result keeps referring to the target it was computed against.
"""
from __future__ import annotations

import uuid
from typing import Optional

from backend.clock import utcnow
from backend.database import dumps
from backend.engine.gap_coverage import evaluate_competency_framework
from backend.engine.jd_parser import MAPPING_VERSION
from backend.store import store

DEFAULT_TARGET_ID = "DEFAULT_DATA_ANALYST"


def default_requirements() -> dict[str, dict]:
    return {
        skill["skill_code"]: {
            "target_level": skill["target_level"], "weight": skill["weight"], "is_core": bool(skill.get("is_core")),
            "requirement_type": "REQUIRED", "rationale": skill.get("description", ""),
        }
        for skill in store.skills
    }


def resolve_target(profile: dict) -> dict:
    """Confirmed JD target first, then a legacy profile choice, then the approved default set."""
    confirmed = profile.get("target_jd")
    if isinstance(confirmed, dict) and confirmed.get("requirements_by_skill"):
        return {**confirmed, "is_confirmed": True}
    if profile.get("job_profile_id") == "CUSTOM_JOB_DESCRIPTION" and isinstance(profile.get("custom_job_profile"), dict):
        legacy = profile["custom_job_profile"]
        return {
            "source_type": "LEGACY_CUSTOM", "name": legacy.get("name", "JD tùy chỉnh"), "jd_id": None, "jd_version": None,
            "mapping_version": None, "target_version": None, "is_confirmed": True,
            "requirements_by_skill": legacy.get("requirements_by_skill", {}), "additional_requirements": legacy.get("additional_requirements", []),
        }
    job_profile = store.get_job_profile(profile.get("job_profile_id", ""))
    if job_profile and profile.get("job_profile_id") != "VN_ENTRY_ANALYST":
        return {
            "source_type": "LEGACY_PROFILE", "name": job_profile["name"], "jd_id": job_profile["profile_id"], "jd_version": None,
            "mapping_version": None, "target_version": None, "is_confirmed": True,
            "requirements_by_skill": job_profile["requirements_by_skill"], "additional_requirements": job_profile.get("additional_requirements", []),
        }
    return {
        "source_type": "DEFAULT", "name": f"Bộ mục tiêu {store.career_metadata['career_title']} mặc định", "jd_id": DEFAULT_TARGET_ID, "jd_version": store.career_metadata["version_tag"],
        "mapping_version": MAPPING_VERSION, "target_version": None, "is_confirmed": False,
        "requirements_by_skill": default_requirements(), "additional_requirements": [],
    }


def learning_hours_by_skill() -> dict[str, float]:
    hours: dict[str, float] = {}
    for activity in store.activities:
        code = activity.get("target_skill")
        hours[code] = hours.get(code, 0.0) + float(activity.get("estimated_hours", 0.0))
    return hours


def skills_for_target(target: dict) -> list[dict]:
    """Catalog skills the target weighs, with the target's level, weight and core flag applied."""
    requirements = target.get("requirements_by_skill", {})
    hours = learning_hours_by_skill()
    result = []
    for skill in store.skills:
        requirement = requirements.get(skill["skill_code"], {})
        weight = float(requirement.get("weight", skill.get("weight", 0)) if requirements else skill.get("weight", 0))
        if weight <= 0:
            continue
        result.append({
            **skill,
            "target_level": int(requirement.get("target_level", skill.get("target_level", 1))),
            "weight": weight,
            "is_core": bool(requirement.get("is_core", skill.get("is_core"))),
            "requirement_type": requirement.get("requirement_type", "REQUIRED"),
            "estimated_learning_hours": max(hours.get(skill["skill_code"], 1.0), 0.25),
        })
    return result


def evaluate_learner(user_id: uuid.UUID, profile: Optional[dict] = None, target: Optional[dict] = None) -> dict:
    """Gap, coverage and readiness for the learner's current target, with reasons and evidence."""
    profile = profile or store.get_or_create_profile(user_id)
    target = target or resolve_target(profile)
    assessed = profile.get("assessed_skills", {})
    levels = {code: item["level"] for code, item in assessed.items()}
    evaluation = evaluate_competency_framework(skills_for_target(target), levels)
    self_reported = {item["skill_code"]: item for item in profile.get("self_reported_skills", []) if isinstance(item, dict) and item.get("skill_code")}
    for item in evaluation["skill_evaluations"]:
        code = item["skill_code"]
        declared = self_reported.get(code)
        evidence = assessed.get(code)
        item["self_reported_level"] = declared.get("level") if declared else None
        item["evidence"] = None
        if evidence:
            item["evidence"] = {
                "submission_id": evidence.get("submission_id"), "source_type": evidence.get("source_type", "ASSESSMENT"),
                "assessed_at": evidence.get("assessed_at"), "task_id": evidence.get("task_id"), "score": evidence.get("score"),
                "scope_note": evidence.get("scope_note"),
            }
        item["explanation"] = _explain(item)
    measured = [item for item in evaluation["skill_evaluations"] if item["status"] == "ASSESSED"]
    evaluation["skills_measured"] = len(measured)
    evaluation["skills_total"] = len(evaluation["skill_evaluations"])
    evaluation["target"] = target_summary(target)
    evaluation["scope_notice"] = (
        "Điểm đáp ứng chỉ phản ánh bộ yêu cầu của mục tiêu đang chọn trong phạm vi các bài đã đo. "
        "Đây không phải tỷ lệ thành thạo toàn bộ nghề hay khả năng được tuyển dụng."
    )
    return evaluation


def _explain(item: dict) -> str:
    target = item["target_level"]
    declared = item["self_reported_level"]
    if item["status"] != "ASSESSED":
        suffix = f" Bạn tự khai mức {declared}, nhưng tự khai không được tính là bằng chứng." if declared is not None else ""
        return f"Chưa có bằng chứng từ bài đánh giá hợp lệ nên chưa kết luận (không phải mức 0).{suffix}"
    level = item["current_level"]
    if item["gap"] == 0:
        return f"Bài đánh giá hợp lệ cho thấy mức {level}, đạt mục tiêu mức {target}."
    return f"Bài đánh giá hợp lệ cho thấy mức {level}, còn thiếu {item['gap']} mức so với mục tiêu mức {target}."


def target_summary(target: dict) -> dict:
    return {key: target.get(key) for key in (
        "source_type", "name", "jd_id", "jd_version", "mapping_version", "target_version", "config_id", "is_confirmed", "employer", "role_level"
    )} | {"additional_requirements": target.get("additional_requirements", [])}


def target_snapshot_for_record(profile: dict) -> dict:
    """Stored on every assessment so it keeps pointing at the target used when it was graded."""
    target = resolve_target(profile)
    return {key: target.get(key) for key in ("source_type", "name", "jd_id", "jd_version", "mapping_version", "target_version")}


def save_target_version(user_id: uuid.UUID, target: dict) -> dict:
    """Confirmed targets are immutable: changing one appends a new version."""
    latest = store.db.one("SELECT MAX(version) AS version FROM target_versions WHERE user_id = ?", (str(user_id),))
    version = int((latest or {}).get("version") or 0) + 1
    record = {**target, "target_version": version, "confirmed_at": utcnow().isoformat()}
    store.db.execute(
        "INSERT INTO target_versions(target_id, user_id, version, jd_id, jd_version, mapping_version, config_id, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), str(user_id), version, target.get("jd_id"), target.get("jd_version"), target.get("mapping_version"),
         target.get("config_id"), dumps(record), record["confirmed_at"]),
    )
    return record
