"""F05: Gap, Coverage, and Readiness Calculation Endpoints (TV3 / F05)."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends
from auth import AuthenticatedUser, get_current_user
from schemas.models import EvaluationResponse, SkillGapItem
from services.store import store
from domain.evaluation import (
    SkillEvaluationItem, evaluate_readiness, calculate_gap,
    calculate_attainment, calculate_priority
)

router = APIRouter(prefix="/evaluation", tags=["F05 - Gap & Readiness"])


@router.get("/summary", response_model=EvaluationResponse)
def get_user_evaluation_summary(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Calculate gap, coverage, priority, and readiness score for the authenticated user.
    
    Principles:
    - Coverage = sum(weight of evaluated skills with valid evidence)
    - Eligibility Gate: Readiness is ONLY released when coverage >= 0.80 and all core skills are evaluated.
    - Otherwise, readiness_score is null and missing core skills are prominently highlighted.
    """
    uid = current_user.user_id

    # Find all assessments completed by this user
    user_assessments = [
        store.assessments[s["submission_id"]]
        for s in store.submissions.values()
        if s["user_id"] == uid and s["submission_id"] in store.assessments
    ]

    # Map skill -> evaluated level and validity
    skill_eval_map: dict[str, tuple[int, bool]] = {}
    for ass in user_assessments:
        if ass.get("status") == "ACCEPTED":
            # Map task to skills
            # DA01 -> SQL, DATA_QUALITY
            # DA02 -> PYTHON, DATA_VIZ
            # DA03 -> WRITTEN_EXPLANATION
            sub_id = ass["submission_id"]
            sub = store.submissions.get(sub_id, {})
            task_id = sub.get("task_version_id", "")
            lvl = ass.get("overall_level", 1)

            if "DA01" in task_id:
                skill_eval_map["SQL"] = (lvl, True)
                skill_eval_map["DATA_QUALITY"] = (lvl, True)
            elif "DA02" in task_id:
                skill_eval_map["PYTHON"] = (lvl, True)
                skill_eval_map["DATA_VIZ"] = (lvl, True)
            elif "DA03" in task_id:
                skill_eval_map["WRITTEN_EXPLANATION"] = (lvl, True)

    # Build SkillEvaluationItems
    eval_items: list[SkillEvaluationItem] = []
    for skill_id, skill in store.skills.items():
        eval_data = skill_eval_map.get(skill_id)
        eval_level = eval_data[0] if eval_data else None
        has_evidence = eval_data[1] if eval_data else False

        eval_items.append(SkillEvaluationItem(
            skill_id=skill.skill_id,
            skill_name=skill.skill_name,
            target_level=skill.target_level,
            weight=skill.weight,
            is_core=skill.is_core,
            evaluated_level=eval_level,
            has_valid_evidence=has_evidence,
            estimated_hours=8.0
        ))

    # Run domain evaluation
    result = evaluate_readiness(eval_items)

    # Build skills analysis details
    skills_analysis: list[SkillGapItem] = []
    for item in eval_items:
        gap = result.gaps[item.skill_id]
        attainment = result.attainments[item.skill_id]
        priority = result.priorities[item.skill_id]
        status_label = "EVALUATED" if item.evaluated_level is not None else "UNEVALUATED"

        skills_analysis.append(SkillGapItem(
            skill_id=item.skill_id,
            skill_name=item.skill_name,
            target_level=item.target_level,
            evaluated_level=item.evaluated_level,
            is_core=item.is_core,
            gap=gap,
            attainment=attainment,
            priority=priority,
            status=status_label
        ))

    return EvaluationResponse(
        user_id=uid,
        coverage=result.coverage,
        is_readiness_eligible=result.is_readiness_eligible,
        readiness_score=result.readiness_score,
        readiness_level=result.readiness_level,
        missing_core_skills=result.missing_core_skills,
        skills_analysis=skills_analysis
    )
