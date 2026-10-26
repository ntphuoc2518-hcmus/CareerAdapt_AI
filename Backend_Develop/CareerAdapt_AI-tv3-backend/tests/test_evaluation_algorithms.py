"""Unit and boundary tests for Evaluation Algorithms (TV3 / T3.4 / F05).

Verifies mathematical purity, division by zero prevention, and strict 80% coverage + core skill gate.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from domain.evaluation import (
    SkillEvaluationItem,
    calculate_gap,
    calculate_attainment,
    calculate_priority,
    calculate_coverage,
    evaluate_readiness
)


class TestPureEvaluationFunctions:

    def test_calculate_gap(self):
        # target=2, evaluated=1 -> gap=1
        assert calculate_gap(target_level=2, current_level=1) == 1
        # target=2, evaluated=2 -> gap=0
        assert calculate_gap(target_level=2, current_level=2) == 0
        # target=2, evaluated=3 (exceeds) -> gap=0
        assert calculate_gap(target_level=2, current_level=3) == 0
        # target=2, evaluated=None (chưa đánh giá) -> gap=2
        assert calculate_gap(target_level=2, current_level=None) == 2

    def test_calculate_attainment(self):
        # evaluated=1, target=2 -> attainment=0.5
        assert calculate_attainment(current_level=1, target_level=2) == 0.5
        # evaluated=2, target=2 -> attainment=1.0
        assert calculate_attainment(current_level=2, target_level=2) == 1.0
        # evaluated=3, target=2 -> capped at 1.0
        assert calculate_attainment(current_level=3, target_level=2) == 1.0
        # unevaluated -> 0.0
        assert calculate_attainment(current_level=None, target_level=2) == 0.0
        # target=0 edge case
        assert calculate_attainment(current_level=1, target_level=0) == 0.0

    def test_calculate_priority_division_by_zero_safety(self):
        # Normal calculation: weight=0.3, gap=1, target=2, hours=10
        # priority = 0.3 * (1/2) / 10 = 0.015
        assert calculate_priority(weight=0.3, gap=1, target_level=2, estimated_hours=10.0) == 0.015
        
        # Division by zero guards:
        assert calculate_priority(weight=0.3, gap=1, target_level=0, estimated_hours=10.0) == 0.0
        assert calculate_priority(weight=0.3, gap=1, target_level=2, estimated_hours=0.0) == 0.0
        assert calculate_priority(weight=0.3, gap=0, target_level=2, estimated_hours=10.0) == 0.0
        assert calculate_priority(weight=0.0, gap=1, target_level=2, estimated_hours=10.0) == 0.0


class TestReadinessEligibilityGate:

    @pytest.fixture
    def standard_skills(self):
        """Standard Data Analyst skill framework: 5 skills, total weight = 1.0."""
        return [
            SkillEvaluationItem("SQL", "SQL", target_level=2, weight=0.30, is_core=True, evaluated_level=None),
            SkillEvaluationItem("PYTHON", "Python", target_level=1, weight=0.15, is_core=False, evaluated_level=None),
            SkillEvaluationItem("DATA_QUALITY", "Data Quality", target_level=2, weight=0.20, is_core=True, evaluated_level=None),
            SkillEvaluationItem("DATA_VIZ", "Data Viz", target_level=2, weight=0.20, is_core=False, evaluated_level=None),
            SkillEvaluationItem("WRITTEN_EXPLANATION", "Explanation", target_level=2, weight=0.15, is_core=False, evaluated_level=None),
        ]

    def test_boundary_coverage_under_80_percent(self, standard_skills):
        """Coverage = 0.7999 or 0.65 (under 80%) -> Readiness must NOT be released!"""
        # Evaluate SQL (0.30), Python (0.15), Data Quality (0.20) -> Coverage = 0.65
        skills = [
            SkillEvaluationItem("SQL", "SQL", target_level=2, weight=0.30, is_core=True, evaluated_level=2, has_valid_evidence=True),
            SkillEvaluationItem("PYTHON", "Python", target_level=1, weight=0.15, is_core=False, evaluated_level=1, has_valid_evidence=True),
            SkillEvaluationItem("DATA_QUALITY", "Data Quality", target_level=2, weight=0.20, is_core=True, evaluated_level=2, has_valid_evidence=True),
            SkillEvaluationItem("DATA_VIZ", "Data Viz", target_level=2, weight=0.20, is_core=False, evaluated_level=None),
            SkillEvaluationItem("WRITTEN_EXPLANATION", "Explanation", target_level=2, weight=0.15, is_core=False, evaluated_level=None),
        ]
        res = evaluate_readiness(skills)
        assert res.coverage == 0.65
        assert res.is_readiness_eligible is False
        assert res.readiness_score is None  # Score must be withheld
        assert "Chưa phát hành" in (res.readiness_level or "")

    def test_coverage_above_80_but_core_skill_missing(self, standard_skills):
        """Coverage >= 80% (0.85) but a CORE skill (DATA_QUALITY) has no evaluation -> Withheld!"""
        # SQL(0.30) + PYTHON(0.15) + DATA_VIZ(0.20) + EXPLANATION(0.15) = 0.80 coverage, but DATA_QUALITY (core) missing!
        skills = [
            SkillEvaluationItem("SQL", "SQL", target_level=2, weight=0.30, is_core=True, evaluated_level=2, has_valid_evidence=True),
            SkillEvaluationItem("PYTHON", "Python", target_level=1, weight=0.15, is_core=False, evaluated_level=1, has_valid_evidence=True),
            SkillEvaluationItem("DATA_QUALITY", "Data Quality", target_level=2, weight=0.20, is_core=True, evaluated_level=None, has_valid_evidence=False),
            SkillEvaluationItem("DATA_VIZ", "Data Viz", target_level=2, weight=0.20, is_core=False, evaluated_level=2, has_valid_evidence=True),
            SkillEvaluationItem("WRITTEN_EXPLANATION", "Explanation", target_level=2, weight=0.15, is_core=False, evaluated_level=2, has_valid_evidence=True),
        ]
        res = evaluate_readiness(skills)
        assert res.coverage == 0.80
        assert res.is_readiness_eligible is False
        assert res.readiness_score is None
        assert "Data Quality" in res.missing_core_skills

    def test_eligible_readiness_released_when_coverage_gte_80_and_all_core_present(self, standard_skills):
        """Coverage = 0.85 and both SQL & DATA_QUALITY are evaluated -> Readiness released!"""
        # SQL (0.30, core) + DATA_QUALITY (0.20, core) + DATA_VIZ (0.20) + EXPLANATION (0.15) = 0.85
        skills = [
            SkillEvaluationItem("SQL", "SQL", target_level=2, weight=0.30, is_core=True, evaluated_level=2, has_valid_evidence=True),
            SkillEvaluationItem("PYTHON", "Python", target_level=1, weight=0.15, is_core=False, evaluated_level=None, has_valid_evidence=False),
            SkillEvaluationItem("DATA_QUALITY", "Data Quality", target_level=2, weight=0.20, is_core=True, evaluated_level=2, has_valid_evidence=True),
            SkillEvaluationItem("DATA_VIZ", "Data Viz", target_level=2, weight=0.20, is_core=False, evaluated_level=2, has_valid_evidence=True),
            SkillEvaluationItem("WRITTEN_EXPLANATION", "Explanation", target_level=2, weight=0.15, is_core=False, evaluated_level=2, has_valid_evidence=True),
        ]
        res = evaluate_readiness(skills)
        assert res.coverage == 0.85
        assert res.is_readiness_eligible is True
        assert res.readiness_score is not None
        assert res.readiness_score > 0
        assert len(res.missing_core_skills) == 0
