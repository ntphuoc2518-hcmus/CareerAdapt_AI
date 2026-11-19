"""Deterministic Rule Engine - Coverage, Gap, Attainment & Readiness Calculations.

Strictly mathematical implementation with NO AI/LLM heuristics.
Formulas defined in Proposal Section 8:
- Coverage = sum(weight_i for i in K)
- Gap_i = max(0, target_i - level_i)
- Attainment_i = min(level_i / target_i, 1.0)
- Readiness released ONLY when coverage >= 0.80 AND all core skills are present in K.
- Readiness = 100 * sum(weight_i * attainment_i for i in K) / coverage
"""
from __future__ import annotations
from typing import Optional


def calculate_gap(target_level: int, current_level: Optional[int]) -> Optional[int]:
    """Calculate competency gap between target level and evidence-backed level.

    An UNASSESSED skill has no gap yet (None): it is unknown, not level 0.
    If current_level >= target_level, gap is 0 (never negative).
    """
    if current_level is None:
        return None
    return max(0, target_level - current_level)


def calculate_attainment(target_level: int, current_level: Optional[int]) -> float:
    """Calculate attainment ratio (capped at 1.0).
    
    If current_level exceeds target_level, attainment is capped at 1.0 (100%).
    """
    if current_level is None or target_level <= 0:
        return 0.0
    return min(current_level / target_level, 1.0)


def calculate_priority(weight: float, gap: int, target_level: int = 1, estimated_hours: float = 1.0) -> float:
    """Calculate deterministic learning priority per hour, normalized to the target.

    Defaults preserve the original two-argument helper contract.
    """
    if target_level <= 0 or estimated_hours <= 0:
        return 0.0
    return round(weight * (gap / target_level) / estimated_hours, 4)


def evaluate_competency_framework(
    skills_catalog: list[dict],
    assessed_levels: dict[str, int]
) -> dict:
    """Evaluate full competency framework for a student.
    
    Args:
        skills_catalog: List of skill dictionaries with keys:
            - skill_code: str
            - weight: float
            - target_level: int
            - is_core: bool
        assessed_levels: Dictionary mapping skill_code -> verified level (from ASSESSMENT mode).
    
    Returns:
        Structured dictionary containing:
            - coverage: float (0.0 to 1.0)
            - readiness: Optional[float] (0.0 to 100.0 or None if locked)
            - is_readiness_locked: bool
            - lock_reasons: list[str]
            - core_skills_met: bool
            - skill_evaluations: list[dict]
    """
    assessed_keys = set(assessed_levels.keys())

    # 1. Calculate Coverage
    coverage = sum(s["weight"] for s in skills_catalog if s["skill_code"] in assessed_keys)
    coverage = round(coverage, 4)

    # 2. Check Core Skills
    core_skills = [s["skill_code"] for s in skills_catalog if s.get("is_core", False)]
    missing_core = [code for code in core_skills if code not in assessed_keys]
    core_skills_met = len(missing_core) == 0

    # 3. Individual Skill Evaluations
    skill_evaluations = []
    weighted_attainment_sum = 0.0

    for s in skills_catalog:
        code = s["skill_code"]
        target = s["target_level"]
        weight = s["weight"]
        is_core = s.get("is_core", False)

        has_evidence = code in assessed_keys
        current_lvl = assessed_levels.get(code) if has_evidence else None

        gap = calculate_gap(target, current_lvl)
        attainment = calculate_attainment(target, current_lvl)
        estimated_hours = max(float(s.get("estimated_learning_hours", 1.0)), 0.25)
        priority = calculate_priority(weight, gap, target, estimated_hours) if has_evidence else 0.0
        attainment_value = round(attainment, 4) if has_evidence else None

        if has_evidence:
            weighted_attainment_sum += weight * attainment

        skill_evaluations.append({
            "skill_code": code,
            "skill_name": s.get("skill_name", code),
            "is_core": is_core,
            "weight": weight,
            "target_level": target,
            "current_level": current_lvl,
            "status": "ASSESSED" if has_evidence else "UNASSESSED",
            "gap": gap,
            "attainment": attainment_value,
            "estimated_learning_hours": estimated_hours,
            "priority_score": priority,
            "next_action": "ASSESS" if not has_evidence else ("LEARN" if gap > 0 else "MAINTAIN")
        })

    # Priority first; ties go to core skills, then larger weight, then skill code, so runs are reproducible.
    skill_evaluations.sort(key=lambda x: (-x["priority_score"], not x["is_core"], -x["weight"], x["skill_code"]))

    # 4. Readiness Evaluation & Release Gate
    # Threshold condition: coverage >= 0.80 AND core_skills_met
    lock_reasons = []
    if coverage < 0.80:
        lock_reasons.append(f"Độ phủ bằng chứng đạt {round(coverage * 100, 1):g}% (Yêu cầu tối thiểu 80%).")
    if not core_skills_met:
        lock_reasons.append(f"Thiếu bằng chứng đánh giá cho các kỹ năng cốt lõi: {', '.join(missing_core)}.")

    if coverage >= 0.80 and core_skills_met and coverage > 0:
        readiness = (weighted_attainment_sum / coverage) * 100.0
        readiness = round(readiness, 2)
        is_locked = False
    else:
        readiness = None
        is_locked = True

    return {
        "coverage": coverage,
        "readiness": readiness,
        "is_readiness_locked": is_locked,
        "lock_reasons": lock_reasons,
        "core_skills_met": core_skills_met,
        "missing_core_skills": missing_core,
        "skill_evaluations": skill_evaluations
    }
