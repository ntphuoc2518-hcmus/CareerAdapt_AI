"""DAG Roadmap Scheduler for CareerAdapt AI (TV3 / F06).

Rules:
1. Validates Directed Acyclic Graph (DAG) - detects cycles and missing prerequisites.
2. Respects weekly hours budget (no week exceeds hours_per_week).
3. Orders activities by priority (highest priority first when prerequisites are met).
4. Unscheduled activities are never silently dropped; they are explicitly listed with clear reasons.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ActivityNode:
    activity_id: str
    title: str
    skill_id: str
    estimated_hours: float
    priority: float
    prerequisites: list[str] = field(default_factory=list)


@dataclass
class ScheduledItem:
    week_number: int
    activity_id: str
    title: str
    skill_id: str
    allocated_hours: float
    prerequisites_met: list[str]


@dataclass
class UnscheduledItem:
    activity_id: str
    title: str
    reason: str


@dataclass
class ScheduleResult:
    is_valid: bool
    total_scheduled_hours: float
    total_weeks: int
    weekly_hours_budget: float
    schedule: list[ScheduledItem]
    unscheduled: list[UnscheduledItem]
    error_message: Optional[str] = None


class CycleDetectedError(Exception):
    """Raised when the prerequisite graph contains a directed cycle."""
    pass


def detect_cycles(nodes: dict[str, ActivityNode]) -> Optional[list[str]]:
    """Return list of node IDs involved in a cycle if any, else None."""
    # 0 = unvisited, 1 = visiting, 2 = visited
    state: dict[str, int] = {k: 0 for k in nodes}
    cycle_path: list[str] = []

    def dfs(curr: str, path: list[str]) -> bool:
        state[curr] = 1
        path.append(curr)
        for prereq in nodes[curr].prerequisites:
            if prereq in nodes:
                if state[prereq] == 1:
                    cycle_path.extend(path[path.index(prereq):] + [prereq])
                    return True
                elif state[prereq] == 0:
                    if dfs(prereq, path):
                        return True
        path.pop()
        state[curr] = 2
        return False

    for node_id in nodes:
        if state[node_id] == 0:
            if dfs(node_id, []):
                return cycle_path
    return None


def generate_roadmap(
    activities: list[ActivityNode],
    hours_per_week: float,
    max_weeks: int = 10
) -> ScheduleResult:
    """Generate a valid, deterministic roadmap honoring prerequisites and weekly hour limits."""
    if hours_per_week <= 0:
        return ScheduleResult(
            is_valid=False,
            total_scheduled_hours=0.0,
            total_weeks=0,
            weekly_hours_budget=hours_per_week,
            schedule=[],
            unscheduled=[
                UnscheduledItem(
                    activity_id=a.activity_id,
                    title=a.title,
                    reason="Quỹ thời gian mỗi tuần bằng 0, không thể xếp lịch."
                ) for a in activities
            ],
            error_message="Quỹ thời gian học tập mỗi tuần phải lớn hơn 0 giờ."
        )

    node_map = {a.activity_id: a for a in activities}
    
    # 1. Cycle detection
    cycle = detect_cycles(node_map)
    if cycle:
        cycle_str = " -> ".join(cycle)
        return ScheduleResult(
            is_valid=False,
            total_scheduled_hours=0.0,
            total_weeks=0,
            weekly_hours_budget=hours_per_week,
            schedule=[],
            unscheduled=[
                UnscheduledItem(
                    activity_id=a.activity_id,
                    title=a.title,
                    reason=f"Đồ thị hoạt động có chu trình phụ thuộc vòng quanh: {cycle_str}"
                ) for a in activities
            ],
            error_message=f"Phát hiện chu trình phụ thuộc trong cây hoạt động: {cycle_str}"
        )

    # 2. Check for missing prerequisites in the catalog
    unscheduled: list[UnscheduledItem] = []
    schedulable_nodes: dict[str, ActivityNode] = {}
    
    for a in activities:
        missing_prereqs = [p for p in a.prerequisites if p not in node_map]
        if missing_prereqs:
            unscheduled.append(UnscheduledItem(
                activity_id=a.activity_id,
                title=a.title,
                reason=f"Thiếu hoạt động tiền quyết trong danh mục: {', '.join(missing_prereqs)}"
            ))
        else:
            schedulable_nodes[a.activity_id] = a

    # 3. Schedule week by week
    completed_activity_ids: set[str] = set()
    schedule: list[ScheduledItem] = []
    current_week = 1
    total_hours = 0.0

    while schedulable_nodes and current_week <= max_weeks:
        week_hours_remaining = hours_per_week
        activities_scheduled_this_week = 0

        # Find all available activities whose prerequisites are already satisfied
        available = [
            a for a in schedulable_nodes.values()
            if all(p in completed_activity_ids for p in a.prerequisites)
        ]

        if not available:
            # Cannot schedule any more because remaining have unmet prerequisites that couldn't be scheduled
            break

        # Sort available activities by priority descending, then by title for determinism
        available.sort(key=lambda x: (x.priority, x.estimated_hours), reverse=True)

        for act in available:
            if act.estimated_hours <= week_hours_remaining:
                schedule.append(ScheduledItem(
                    week_number=current_week,
                    activity_id=act.activity_id,
                    title=act.title,
                    skill_id=act.skill_id,
                    allocated_hours=act.estimated_hours,
                    prerequisites_met=list(act.prerequisites)
                ))
                week_hours_remaining -= act.estimated_hours
                total_hours += act.estimated_hours
                completed_activity_ids.add(act.activity_id)
                del schedulable_nodes[act.activity_id]
                activities_scheduled_this_week += 1

        if activities_scheduled_this_week == 0:
            # If the next available activity's hours exceed the entire weekly budget, schedule what fits or bump week
            # If an activity alone exceeds hours_per_week, it cannot fit in one single week unless split
            biggest_available = available[0]
            if biggest_available.estimated_hours > hours_per_week:
                unscheduled.append(UnscheduledItem(
                    activity_id=biggest_available.activity_id,
                    title=biggest_available.title,
                    reason=f"Thời lượng hoạt động ({biggest_available.estimated_hours}h) vượt quá ngân sách cả tuần ({hours_per_week}h)."
                ))
                del schedulable_nodes[biggest_available.activity_id]
                continue

        current_week += 1

    # Any remaining nodes could not be scheduled within max_weeks
    for act in schedulable_nodes.values():
        unscheduled.append(UnscheduledItem(
            activity_id=act.activity_id,
            title=act.title,
            reason=f"Vượt quá số tuần tối đa ({max_weeks} tuần) với quỹ giờ hiện tại ({hours_per_week}h/tuần)."
        ))

    actual_weeks_used = max([item.week_number for item in schedule], default=0)

    return ScheduleResult(
        is_valid=True,
        total_scheduled_hours=round(total_hours, 2),
        total_weeks=actual_weeks_used,
        weekly_hours_budget=hours_per_week,
        schedule=schedule,
        unscheduled=unscheduled
    )
