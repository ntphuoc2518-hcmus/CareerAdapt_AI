"""Pure functions for Gap, Coverage, Readiness, and Priority evaluation (TV3 / F05).

Core Principles:
1. Pure, deterministic mathematical functions. Same inputs always produce same outputs.
2. No division by zero.
3. "Chưa đánh giá" is distinct from level 0.
4. Readiness is ONLY released when coverage >= 0.80 and ALL core skills are evaluated with valid evidence.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SkillEvaluationItem:
    skill_id: str
    skill_name: str
    target_level: int           # e.g. 1 to 3
    weight: float               # e.g. 0.20 (sum across all skills = 1.0)
    is_core: bool               # e.g. SQL, Data Quality are core
    evaluated_level: Optional[int]  # None if 'Chưa đánh giá', 0-3 if evaluated
    has_valid_evidence: bool = False
    estimated_hours: float = 10.0


@dataclass(frozen=True)
class EvaluationSummaryResult:
    coverage: float
    is_readiness_eligible: bool
    readiness_score: Optional[float]   # None when not eligible
    readiness_level: Optional[str]     # e.g. "Sẵn sàng thực tập" / "Cần bổ sung kỹ năng cốt lõi"
    missing_core_skills: list[str]
    unevaluated_skills: list[str]
    gaps: dict[str, int]
    priorities: dict[str, float]
    attainments: dict[str, float]


def calculate_gap(target_level: int, current_level: Optional[int]) -> int:
    """gap = max(0, target - level). If not evaluated, gap equals target_level."""
    if current_level is None:
        return max(0, target_level)
    return max(0, target_level - current_level)


def calculate_attainment(current_level: Optional[int], target_level: int) -> float:
    """attainment = min(level / target, 1.0). If current_level is None, attainment is 0.0."""
    if current_level is None or target_level <= 0:
        return 0.0
    return min(float(current_level) / float(target_level), 1.0)


def calculate_priority(
    weight: float,
    gap: int,
    target_level: int,
    estimated_hours: float
) -> float:
    """priority = weight * (gap / target) / estimated_hours.
    
    Guards against division by zero (target <= 0 or estimated_hours <= 0).
    """
    if target_level <= 0 or estimated_hours <= 0 or gap <= 0 or weight <= 0:
        return 0.0
    return (weight * (float(gap) / float(target_level))) / float(estimated_hours)


def calculate_coverage(skills: list[SkillEvaluationItem]) -> float:
    """coverage = sum of weights of skills that have valid evaluation evidence.
    
    Normalized between 0.0 and 1.0. Rounded to 4 decimal places.
    """
    if not skills:
        return 0.0
    total_valid_weight = sum(
        item.weight for item in skills
        if item.evaluated_level is not None and item.has_valid_evidence
    )
    return round(min(max(total_valid_weight, 0.0), 1.0), 4)


def evaluate_readiness(skills: list[SkillEvaluationItem]) -> EvaluationSummaryResult:
    """Evaluate overall readiness according to strict rubric and project rules.
    
    Rules:
    - Coverage = sum(weight of evaluated skills with valid evidence)
    - Eligibility Gate: Coverage >= 0.80 AND every core skill has valid evaluation!
    - Readiness score: Weighted sum of attainments across all skills if eligible, else None.
    """
    coverage = calculate_coverage(skills)
    missing_core: list[str] = []
    unevaluated: list[str] = []
    gaps: dict[str, int] = {}
    priorities: dict[str, float] = {}
    attainments: dict[str, float] = {}
    weighted_attainment_sum = 0.0
    total_weight = 0.0

    for item in skills:
        gap = calculate_gap(item.target_level, item.evaluated_level)
        attainment = calculate_attainment(item.evaluated_level, item.target_level)
        priority = calculate_priority(item.weight, gap, item.target_level, item.estimated_hours)
        
        gaps[item.skill_id] = gap
        priorities[item.skill_id] = round(priority, 6)
        attainments[item.skill_id] = round(attainment, 4)
        
        total_weight += item.weight
        weighted_attainment_sum += attainment * item.weight

        if item.evaluated_level is None or not item.has_valid_evidence:
            unevaluated.append(item.skill_name)
            if item.is_core:
                missing_core.append(item.skill_name)

    # Gate: Coverage must be >= 0.80 and NO core skills missing valid evaluation
    # Note: Using 0.7999 tolerance guard to test boundary precision
    is_eligible = (coverage >= 0.80) and (len(missing_core) == 0)
    
    readiness_score: Optional[float] = None
    readiness_level: Optional[str] = None
    
    if is_eligible:
        score_base = (weighted_attainment_sum / total_weight) if total_weight > 0 else 0.0
        readiness_score = round(score_base * 100.0, 2)
        if readiness_score >= 85.0:
            readiness_level = "Sẵn sàng thực tập (Xuất sắc)"
        elif readiness_score >= 70.0:
            readiness_level = "Sẵn sàng thực tập (Đạt chuẩn)"
        else:
            readiness_level = "Cần cải thiện thêm một số tiêu chí"
    else:
        # Withheld: Explicit reason communicated
        readiness_score = None
        if coverage < 0.80 and missing_core:
            readiness_level = f"Chưa phát hành: Độ bao phủ ({coverage * 100:.1f}% < 80%) và thiếu kỹ năng cốt lõi ({', '.join(missing_core)})"
        elif coverage < 0.80:
            readiness_level = f"Chưa phát hành: Độ bao phủ chưa đạt ngưỡng tối thiểu ({coverage * 100:.1f}% < 80%)"
        else:
            readiness_level = f"Chưa phát hành: Chưa hoàn thành đánh giá kỹ năng cốt lõi ({', '.join(missing_core)})"

    return EvaluationSummaryResult(
        coverage=coverage,
        is_readiness_eligible=is_eligible,
        readiness_score=readiness_score,
        readiness_level=readiness_level,
        missing_core_skills=missing_core,
        unevaluated_skills=unevaluated,
        gaps=gaps,
        priorities=priorities,
        attainments=attainments,
    )
