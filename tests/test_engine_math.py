"""Unit Test Suite: Deterministic Rule Engine - Mathematical Boundary Cases.

Covers:
1. Empty assessment data (UNASSESSED state is None, never level 0)
2. Missing core skills (SQL or DATA_QUALITY absent)
3. Coverage threshold boundaries (coverage < 0.80 vs >= 0.80)
4. Current level exceeding target level (attainment capped at 1.0)
5. Gap = 0 when competency met
6. Priority ranking calculation (weight * gap)
"""
import pytest
from backend.engine.gap_coverage import (
    calculate_gap, calculate_attainment, calculate_priority,
    evaluate_competency_framework
)

# Standardized 5-skill Data Analyst Framework
SAMPLE_SKILLS = [
    {"skill_code": "SQL", "target_level": 2, "weight": 0.30, "is_core": True},
    {"skill_code": "DATA_QUALITY", "target_level": 2, "weight": 0.20, "is_core": True},
    {"skill_code": "PYTHON", "target_level": 1, "weight": 0.15, "is_core": False},
    {"skill_code": "DATA_VIZ", "target_level": 2, "weight": 0.20, "is_core": False},
    {"skill_code": "WRITTEN_COMM", "target_level": 2, "weight": 0.15, "is_core": False}
]


def test_empty_assessment_data():
    """Empty assessment data: coverage = 0, readiness locked as None."""
    res = evaluate_competency_framework(SAMPLE_SKILLS, {})
    assert res["coverage"] == 0.0
    assert res["readiness"] is None
    assert res["is_readiness_locked"] is True
    assert not res["core_skills_met"]
    assert "SQL" in res["missing_core_skills"]
    assert "DATA_QUALITY" in res["missing_core_skills"]


def test_missing_core_skills_blocks_readiness():
    """Even if coverage is high (e.g. 0.50), missing core skill blocks readiness."""
    # Assessed: PYTHON (0.15), DATA_VIZ (0.20), WRITTEN_COMM (0.15) -> coverage = 0.50
    assessed = {"PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2}
    res = evaluate_competency_framework(SAMPLE_SKILLS, assessed)
    assert res["coverage"] == 0.50
    assert res["readiness"] is None
    assert res["is_readiness_locked"] is True
    assert not res["core_skills_met"]


def test_coverage_boundary_below_80_percent():
    """Coverage at 0.65 (SQL 0.30 + DATA_QUALITY 0.20 + PYTHON 0.15) < 0.80 -> locked."""
    assessed = {"SQL": 2, "DATA_QUALITY": 2, "PYTHON": 1}
    res = evaluate_competency_framework(SAMPLE_SKILLS, assessed)
    assert res["coverage"] == 0.65
    assert res["core_skills_met"] is True
    assert res["readiness"] is None
    assert res["is_readiness_locked"] is True
    assert any("80%" in r for r in res["lock_reasons"])


def test_coverage_boundary_at_and_above_80_percent():
    """Coverage reaches 0.85 (SQL 0.30 + DQ 0.20 + PYTHON 0.15 + DATA_VIZ 0.20) >= 0.80 -> releases readiness."""
    assessed = {
        "SQL": 2,          # attainment: 2/2 = 1.0 (w=0.30) -> 0.30
        "DATA_QUALITY": 2, # attainment: 2/2 = 1.0 (w=0.20) -> 0.20
        "PYTHON": 1,       # attainment: 1/1 = 1.0 (w=0.15) -> 0.15
        "DATA_VIZ": 2      # attainment: 2/2 = 1.0 (w=0.20) -> 0.20
    }
    # Total weighted attainment = 0.85 / coverage 0.85 = 100%
    res = evaluate_competency_framework(SAMPLE_SKILLS, assessed)
    assert res["coverage"] == 0.85
    assert res["core_skills_met"] is True
    assert res["is_readiness_locked"] is False
    assert res["readiness"] == 100.0


def test_gap_and_attainment_capping():
    """Level exceeding target level: gap = 0, attainment capped at 1.0."""
    target = 2
    level_exceeded = 3
    assert calculate_gap(target, level_exceeded) == 0
    assert calculate_attainment(target, level_exceeded) == 1.0

    # Unassessed is unknown, not level 0: it has no gap yet.
    assert calculate_gap(target, None) is None


def test_priority_ranking():
    """Priority score = weight * gap."""
    # SQL: target 2, level 0 -> gap 2, weight 0.30 -> priority = 0.60
    assert calculate_priority(0.30, 2) == 0.60
    # PYTHON: target 1, level 1 -> gap 0, weight 0.15 -> priority = 0.0
    assert calculate_priority(0.15, 0) == 0.0
