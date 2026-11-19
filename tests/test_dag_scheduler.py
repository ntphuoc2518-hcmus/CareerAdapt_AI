"""Unit Test Suite: DAG Roadmap Scheduler & Cycle Detection.

Covers:
1. Weekly hours equal to 0 (all activities unscheduled)
2. Deadline too short / capacity exceeded (unscheduled activities with explicit reasons)
3. Prerequisites satisfaction order (Topological sorting)
4. Cycle Detection using DFS 3-color algorithm
"""
import pytest
from backend.engine.dag_scheduler import (
    detect_cycle_dfs, topological_sort, schedule_dag_roadmap
)

SAMPLE_ACTIVITIES = [
    {"activity_id": "ACT_SQL_01", "title": "SQL Basics", "estimated_hours": 4.0, "prerequisites": []},
    {"activity_id": "ACT_DQ_01", "title": "Data Quality", "estimated_hours": 3.0, "prerequisites": ["ACT_SQL_01"]},
    {"activity_id": "ACT_PY_01", "title": "Python Basics", "estimated_hours": 3.0, "prerequisites": []},
    {"activity_id": "ACT_VIZ_01", "title": "Data Viz", "estimated_hours": 4.0, "prerequisites": ["ACT_PY_01"]},
    {"activity_id": "ACT_COMM_01", "title": "Communication", "estimated_hours": 2.0, "prerequisites": ["ACT_DQ_01"]}
]


def test_weekly_hours_equal_zero():
    """Weekly hours budget = 0 -> All activities unscheduled with reason."""
    res = schedule_dag_roadmap(SAMPLE_ACTIVITIES, weekly_hours_budget=0, target_timeline_weeks=8)
    assert len(res["scheduled_weeks"]) == 0
    assert len(res["unscheduled_activities"]) == len(SAMPLE_ACTIVITIES)
    for u in res["unscheduled_activities"]:
        assert "weekly_hours" in u["reason"]


def test_deadline_too_short_or_capacity_exceeded():
    """Weekly budget is 4 hours, but timeline is only 1 week (only 1 activity fits, 4 unscheduled)."""
    res = schedule_dag_roadmap(SAMPLE_ACTIVITIES, weekly_hours_budget=4.0, target_timeline_weeks=1)
    assert len(res["scheduled_weeks"]) == 1
    assert len(res["unscheduled_activities"]) > 0
    assert res["meets_deadline"] is False


def test_prerequisites_order_guarantee():
    """Prerequisites must appear in earlier weeks than dependent activities."""
    res = schedule_dag_roadmap(SAMPLE_ACTIVITIES, weekly_hours_budget=4.0, target_timeline_weeks=8)
    scheduled_weeks = res["scheduled_weeks"]
    
    # Map activity_id to scheduled week_number
    week_map = {}
    for w in scheduled_weeks:
        for a in w["activities"]:
            week_map[a["activity_id"]] = w["week_number"]

    # ACT_DQ_01 depends on ACT_SQL_01 -> must be in >= ACT_SQL_01 week
    assert week_map["ACT_DQ_01"] >= week_map["ACT_SQL_01"]
    # ACT_COMM_01 depends on ACT_DQ_01
    assert week_map["ACT_COMM_01"] >= week_map["ACT_DQ_01"]
    # ACT_VIZ_01 depends on ACT_PY_01
    assert week_map["ACT_VIZ_01"] >= week_map["ACT_PY_01"]


def test_dag_cycle_detection():
    """Cyclic dependency (A -> B -> C -> A) must be detected by DFS."""
    cyclic_graph = [
        {"activity_id": "A", "prerequisites": ["C"]},
        {"activity_id": "B", "prerequisites": ["A"]},
        {"activity_id": "C", "prerequisites": ["B"]}
    ]
    has_cycle, cycle_path = detect_cycle_dfs(cyclic_graph)
    assert has_cycle is True
    assert len(cycle_path) >= 3

    # Topological sort must raise ValueError on cyclic graph
    with pytest.raises(ValueError) as excinfo:
        topological_sort(cyclic_graph)
    assert "DAG Cycle" in str(excinfo.value)
