"""Unit and boundary tests for DAG Roadmap Scheduler (TV3 / T3.5 / F06).

Tests cycle detection, prerequisite topological ordering, weekly capacity constraints,
and explicit unscheduled reasons.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from domain.scheduler import ActivityNode, generate_roadmap, detect_cycles


class TestDAGScheduler:

    def test_cycle_detection(self):
        """A depends on B, B depends on C, C depends on A -> Cycle detected!"""
        nodes = {
            "A": ActivityNode("A", "Activity A", "SQL", 3.0, 0.9, prerequisites=["B"]),
            "B": ActivityNode("B", "Activity B", "SQL", 3.0, 0.8, prerequisites=["C"]),
            "C": ActivityNode("C", "Activity C", "SQL", 3.0, 0.7, prerequisites=["A"]),
        }
        cycle = detect_cycles(nodes)
        assert cycle is not None
        assert len(cycle) >= 3

        result = generate_roadmap(list(nodes.values()), hours_per_week=10.0)
        assert result.is_valid is False
        assert "chu trình" in (result.error_message or "").lower()
        assert len(result.unscheduled) == 3

    def test_missing_prerequisite_handling(self):
        """Activity requires a prerequisite that is not in the catalog."""
        nodes = [
            ActivityNode("A", "Activity A", "SQL", 3.0, 0.9, prerequisites=["NON_EXISTENT_PREREQ"]),
            ActivityNode("B", "Activity B", "SQL", 4.0, 0.8, prerequisites=[]),
        ]
        result = generate_roadmap(nodes, hours_per_week=10.0)
        assert result.is_valid is True
        # B should be scheduled in week 1
        assert len(result.schedule) == 1
        assert result.schedule[0].activity_id == "B"
        # A should be unscheduled with clear reason
        assert len(result.unscheduled) == 1
        assert result.unscheduled[0].activity_id == "A"
        assert "thiếu hoạt động tiền quyết" in result.unscheduled[0].reason.lower()

    def test_weekly_hours_capacity_constraint(self):
        """Budget 8h/week. 3 activities of 4h each -> Week 1 has 8h, Week 2 has 4h."""
        nodes = [
            ActivityNode("A1", "Act 1", "SQL", 4.0, 0.9, prerequisites=[]),
            ActivityNode("A2", "Act 2", "SQL", 4.0, 0.8, prerequisites=[]),
            ActivityNode("A3", "Act 3", "SQL", 4.0, 0.7, prerequisites=["A1"]),
        ]
        result = generate_roadmap(nodes, hours_per_week=8.0)
        assert result.is_valid is True
        assert result.total_weeks == 2
        assert result.total_scheduled_hours == 12.0

        week1 = [x for x in result.schedule if x.week_number == 1]
        week2 = [x for x in result.schedule if x.week_number == 2]

        assert sum(x.allocated_hours for x in week1) <= 8.0
        assert sum(x.allocated_hours for x in week2) <= 8.0
        assert len(week1) == 2
        assert len(week2) == 1

    def test_activity_exceeding_entire_weekly_budget(self):
        """Activity takes 15h, but weekly budget is 10h -> cannot fit, marked unscheduled."""
        nodes = [
            ActivityNode("HUGE_ACT", "Heavy Project", "SQL", 15.0, 0.9, prerequisites=[]),
            ActivityNode("SMALL_ACT", "Quick Task", "SQL", 3.0, 0.5, prerequisites=[]),
        ]
        result = generate_roadmap(nodes, hours_per_week=10.0)
        assert result.is_valid is True
        assert len(result.schedule) == 1
        assert result.schedule[0].activity_id == "SMALL_ACT"
        assert len(result.unscheduled) == 1
        assert result.unscheduled[0].activity_id == "HUGE_ACT"
        assert "vượt quá ngân sách" in result.unscheduled[0].reason.lower()

    def test_zero_weekly_hours_handling(self):
        """hours_per_week = 0 -> cleanly rejected without division by zero or infinite loop."""
        nodes = [
            ActivityNode("A1", "Act 1", "SQL", 4.0, 0.9, prerequisites=[]),
        ]
        result = generate_roadmap(nodes, hours_per_week=0.0)
        assert result.is_valid is False
        assert len(result.unscheduled) == 1
        assert "bằng 0" in result.unscheduled[0].reason.lower()
