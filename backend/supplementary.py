"""Self-study material for JD requirements the catalog cannot measure (no rubric, so never scheduled or graded)."""
from __future__ import annotations

import json
from pathlib import Path

from backend.engine.skill_report import normalize

TOPICS = json.loads((Path(__file__).resolve().parents[1] / "data" / "supplementary_topics_v1.json").read_text(encoding="utf-8"))["topics"]
FIELDS = ("resource_id", "title", "provider", "url", "language", "estimated_minutes")
MAX_LINKS = 4


def resources_for_requirement(label: str, usable: list[dict]) -> list[dict]:
    """Approved, reachable resources of every topic whose terms occur in the requirement text."""
    text = normalize(label)
    by_id = {item["resource_id"]: item for item in usable}
    found: dict[str, dict] = {}
    for topic in TOPICS:
        if not any(term in text for term in topic["terms"]):
            continue
        for resource_id in topic["resource_ids"]:
            if resource_id in by_id:
                found.setdefault(resource_id, {key: by_id[resource_id].get(key) for key in FIELDS})
    return list(found.values())[:MAX_LINKS]


def attach(unscheduled: list[dict], usable: list[dict]) -> None:
    """Add current self-study links to the JD requirements left off a plan. Read at view time, so an old plan shows today's catalog."""
    for item in unscheduled:
        if item.get("kind") == "JD_REQUIREMENT":
            item["self_study"] = resources_for_requirement(item.get("title") or "", usable)
