"""Deterministic Rule Engine - DAG Roadmap Scheduler & Topological Sequencing.

Algorithm Specification:
1. Detect cycles using Depth-First Search (DFS) with 3-color node marking (WHITE, GRAY, BLACK).
2. Compute Topological Ordering ensuring all prerequisites precede dependent activities.
3. Schedule activities into weekly buckets respecting student's weekly_hours_budget.
4. Record explicit reasons for any unscheduled activities (ZERO_WEEKLY_HOURS, INSUFFICIENT_HOURS,
   EXCEEDS_WEEKLY_BUDGET, MISSING_PREREQUISITE, PREREQUISITE_CYCLE).
"""
from __future__ import annotations
from typing import Any, Optional


def detect_cycle_dfs(activities: list[dict]) -> tuple[bool, list[str]]:
    """Detect cycles in the prerequisite graph using DFS 3-color algorithm.
    
    Returns:
        (has_cycle: bool, cycle_path: list[str])
    """
    # Build adjacency list: activity_id -> list of prerequisite IDs
    # Note: If B depends on A (A is prerequisite of B), edge is A -> B
    adj: dict[str, list[str]] = {a["activity_id"]: [] for a in activities}
    
    # Fill edges: prereq -> dependent
    for a in activities:
        aid = a["activity_id"]
        for p in a.get("prerequisites", []):
            if p in adj:
                adj[p].append(aid)

    # 0 = WHITE (unvisited), 1 = GRAY (visiting in current path), 2 = BLACK (finished)
    color: dict[str, int] = {node: 0 for node in adj}
    parent: dict[str, Optional[str]] = {node: None for node in adj}
    cycle_nodes: list[str] = []

    def dfs(u: str) -> bool:
        color[u] = 1
        for v in adj[u]:
            if color[v] == 1:
                # Cycle detected! Reconstruct path
                curr = u
                cycle_nodes.append(v)
                while curr and curr != v:
                    cycle_nodes.append(curr)
                    curr = parent.get(curr)
                cycle_nodes.append(v)
                cycle_nodes.reverse()
                return True
            if color[v] == 0:
                parent[v] = u
                if dfs(v):
                    return True
        color[u] = 2
        return False

    for node in adj:
        if color[node] == 0:
            if dfs(node):
                return True, cycle_nodes

    return False, []


def topological_sort(activities: list[dict]) -> list[dict]:
    """Sort activities in topological dependency order (Kahn's algorithm).
    
    Raises:
        ValueError if prerequisite graph contains a cycle.
    """
    has_cycle, cycle_path = detect_cycle_dfs(activities)
    if has_cycle:
        raise ValueError(f"Phát hiện chu trình phụ thuộc vô tận (DAG Cycle): {' -> '.join(cycle_path)}")

    activity_map = {a["activity_id"]: a for a in activities}
    original_order = {a["activity_id"]: index for index, a in enumerate(activities)}
    in_degree = {a["activity_id"]: 0 for a in activities}
    adj = {a["activity_id"]: [] for a in activities}

    for a in activities:
        aid = a["activity_id"]
        for p in a.get("prerequisites", []):
            if p in activity_map:
                adj[p].append(aid)
                in_degree[aid] += 1

    priority_key = lambda aid: (
        -float(activity_map[aid].get("priority_score", 0.0)),
        not activity_map[aid].get("is_core", False),
        -float(activity_map[aid].get("skill_weight", 0.0)),
        str(activity_map[aid].get("target_skill", "")),
        original_order[aid],
    )
    queue = sorted([aid for aid, deg in in_degree.items() if deg == 0], key=priority_key)
    sorted_nodes = []

    while queue:
        curr = queue.pop(0)
        sorted_nodes.append(activity_map[curr])
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
        queue.sort(key=priority_key)

    if len(sorted_nodes) < len(activities):
        raise ValueError("Lỗi lập lịch: Không thể sắp xếp thứ tự do phụ thuộc không hợp lệ.")

    return sorted_nodes


def validate_prerequisite_graph(activities: list[dict]) -> dict:
    """Report cycles and prerequisites that do not exist, naming the nodes involved."""
    has_cycle, cycle_path = detect_cycle_dfs(activities)
    known = {a["activity_id"] for a in activities}
    missing = sorted({(a["activity_id"], p) for a in activities for p in a.get("prerequisites", []) if p not in known})
    return {"has_cycle": has_cycle, "cycle_path": cycle_path, "missing_prerequisites": [{"activity_id": a, "prerequisite": p} for a, p in missing]}


def _unscheduled(activity: dict, code: str, reason: str) -> dict:
    return {
        "activity_id": activity["activity_id"], "title": activity.get("title", activity["activity_id"]), "target_skill": activity.get("target_skill"),
        "estimated_hours": activity.get("estimated_hours"), "kind": activity.get("kind", "LEARNING"), "reason_code": code, "reason": reason,
    }


def schedule_dag_roadmap(
    activities: list[dict],
    weekly_hours_budget: float,
    target_timeline_weeks: int,
    completed_activity_ids: Optional[set[str]] = None,
    earliest_week_by_activity: Optional[dict[str, int]] = None
) -> dict:
    """Place activities into weeks without exceeding the weekly budget or breaking prerequisites.

    Activities are taken in priority-respecting topological order. Each one goes into the earliest
    week after its prerequisites that has room. An activity is split across weeks only when it is
    marked ``splittable``, and it is scheduled only if all of its hours fit before the deadline, so
    the plan never shows work that cannot finish. The budget is never raised to fit more.

    Returns a dictionary with scheduled_weeks, unscheduled_activities (each with reason_code and
    reason), total_scheduled_hours, total_weeks_needed, meets_deadline and status_message.
    """
    completed_activity_ids = set(completed_activity_ids or ())
    earliest_week_by_activity = earliest_week_by_activity or {}
    base = {"target_timeline_weeks": target_timeline_weeks, "weekly_hours_budget": weekly_hours_budget}

    if weekly_hours_budget <= 0:
        return {
            **base, "scheduled_weeks": [],
            "unscheduled_activities": [_unscheduled(a, "ZERO_WEEKLY_HOURS", "Quỹ thời gian học mỗi tuần bằng 0 (weekly_hours <= 0)") for a in activities],
            "total_scheduled_hours": 0.0, "total_weeks_needed": 0, "meets_deadline": False,
            "status_message": "Vui lòng cấu hình quỹ thời gian học mỗi tuần (> 0 giờ) để tạo lộ trình."
        }

    try:
        sorted_activities = topological_sort(activities)
    except ValueError as error:
        return {
            **base, "scheduled_weeks": [], "blocked": True, "cycle_path": detect_cycle_dfs(activities)[1],
            "unscheduled_activities": [_unscheduled(a, "PREREQUISITE_CYCLE", str(error)) for a in activities],
            "total_scheduled_hours": 0.0, "total_weeks_needed": 0, "meets_deadline": False,
            "status_message": f"Lỗi chu trình DAG: {error}"
        }

    used = {week: 0.0 for week in range(1, target_timeline_weeks + 1)}
    placed: dict[int, list[dict]] = {}
    finish_week: dict[str, int] = {}
    unscheduled: list[dict] = []
    epsilon = 1e-9

    for activity in sorted_activities:
        activity_id = activity["activity_id"]
        if activity_id in completed_activity_ids:
            continue
        hours = float(activity.get("estimated_hours", 2.0))
        prerequisites = activity.get("prerequisites", [])
        blocked = [p for p in prerequisites if p not in completed_activity_ids and p not in finish_week]
        if blocked:
            unscheduled.append(_unscheduled(activity, "MISSING_PREREQUISITE", f"Tiên quyết chưa đạt hoặc chưa xếp được: {', '.join(blocked)}"))
            continue
        start = max([max(int(earliest_week_by_activity.get(activity_id, 1)), 1)] + [finish_week[p] for p in prerequisites if p in finish_week])
        splittable = bool(activity.get("splittable"))
        if not splittable and hours > weekly_hours_budget + epsilon:
            unscheduled.append(_unscheduled(activity, "EXCEEDS_WEEKLY_BUDGET", f"Thời lượng học phần ({hours:g}h) vượt quỹ giờ mỗi tuần ({weekly_hours_budget:g}h) và không thể chia nhỏ."))
            continue
        segments: list[tuple[int, float]] = []
        if splittable:
            free = sum(weekly_hours_budget - used[week] for week in used if week >= start)
            if free + epsilon >= hours:
                left = hours
                for week in sorted(week for week in used if week >= start):
                    portion = min(left, weekly_hours_budget - used[week])
                    if portion > epsilon:
                        segments.append((week, portion))
                        left -= portion
                    if left <= epsilon:
                        break
        else:
            week = next((week for week in sorted(used) if week >= start and used[week] + hours <= weekly_hours_budget + epsilon), None)
            if week is not None:
                segments = [(week, hours)]
        if not segments:
            unscheduled.append(_unscheduled(activity, "INSUFFICIENT_HOURS", f"Không đủ giờ trong {target_timeline_weeks} tuần với {weekly_hours_budget:g}h/tuần."))
            continue
        for index, (week, portion) in enumerate(segments):
            used[week] += portion
            placed.setdefault(week, []).append({**activity, "allocated_hours": round(portion, 2), "segment": index + 1, "total_segments": len(segments)})
        finish_week[activity_id] = segments[-1][0]

    scheduled_weeks = [
        {
            "week_number": week,
            "allocated_hours": round(used[week], 2),
            "remaining_capacity": round(weekly_hours_budget - used[week], 2),
            "activities": placed[week],
        }
        for week in sorted(placed)
    ]
    total_scheduled_hours = sum(week["allocated_hours"] for week in scheduled_weeks)
    total_weeks_needed = max((week["week_number"] for week in scheduled_weeks), default=0)
    meets_deadline = not unscheduled
    return {
        **base, "scheduled_weeks": scheduled_weeks, "unscheduled_activities": unscheduled,
        "total_scheduled_hours": round(total_scheduled_hours, 2), "total_weeks_needed": total_weeks_needed, "meets_deadline": meets_deadline,
        "status_message": "Lộ trình đã xếp đủ các hoạt động trong thời hạn." if meets_deadline else "Một số hoạt động chưa thể xếp lịch; xem lý do bên dưới."
    }
