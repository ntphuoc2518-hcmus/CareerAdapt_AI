"""Seed and read the JD library and learning resource catalog (both versioned, in SQLite)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from backend.clock import utcnow
from backend.database import Database, dumps
from backend.engine.jd_parser import MAPPING_VERSION, text_hash

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
USABLE_RESOURCE_LINK = ("OK", "UNKNOWN")


def seed_catalogs(db: Database) -> None:
    """Insert entries that are missing. Existing rows are never overwritten, so admin decisions stand."""
    library = json.loads((DATA_DIR / "jd_library_v4.json").read_text(encoding="utf-8"))
    resources = json.loads((DATA_DIR / "learning_resources_v4.json").read_text(encoding="utf-8"))
    now = utcnow().isoformat()
    with db.transaction():
        for entry in library["entries"]:
            if db.one("SELECT 1 FROM job_descriptions WHERE jd_id = ?", (entry["jd_id"],)):
                continue
            db.execute(
                "INSERT INTO job_descriptions(jd_id, origin, owner_user_id, title, employer, role_level, industry, language, latest_version, created_at) "
                "VALUES (?, 'LIBRARY', NULL, ?, ?, ?, ?, ?, 1, ?)",
                (entry["jd_id"], entry["title"], entry.get("employer"), entry.get("role_level"), entry.get("industry"), entry.get("language"), now),
            )
            summary = f"{entry.get('description', '')}\n{entry.get('scope_note', '')}"
            payload = {key: entry.get(key) for key in ("description", "scope_note", "sources", "requirements_by_skill", "additional_requirements", "review_note")}
            payload["config_id"] = "LIBRARY"
            db.execute(
                """INSERT INTO jd_versions(jd_id, jd_version, raw_text, raw_text_hash, source_url, source_type, source_date, file_name, mapping_version,
                       review_status, reviewer_id, reviewed_at, last_checked_at, next_review_at, link_status, scope_status, payload, created_at)
                   VALUES (?, 1, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, 'IN_SCOPE', ?, ?)""",
                (entry["jd_id"], summary, text_hash(summary), entry.get("source_url"), entry.get("source_type"), entry.get("source_date"), MAPPING_VERSION,
                 entry["review_status"], entry.get("reviewer_id"), entry.get("last_checked_at") if entry["review_status"] == "APPROVED" else None,
                 entry.get("last_checked_at"), entry.get("next_review_at"), entry.get("link_status"), dumps(payload), now),
            )
            for code, requirement in entry["requirements_by_skill"].items():
                if float(requirement.get("weight", 0)) <= 0:
                    continue
                db.execute(
                    """INSERT INTO jd_requirements(requirement_id, jd_id, jd_version, source_excerpt, normalized_text, requirement_type, skill_code, in_catalog,
                           target_level, weight, confidence, mapping_rule, needs_confirmation, payload)
                       VALUES (?, ?, 1, ?, ?, ?, ?, 1, ?, ?, 1.0, 'CURATED', 0, ?)""",
                    (f"{entry['jd_id']}-{code}", entry["jd_id"], requirement.get("rationale"), requirement.get("rationale"), requirement["requirement_type"], code,
                     requirement["target_level"], requirement["weight"], dumps({"excerpt_kind": "PARAPHRASE"})),
                )
            for index, label in enumerate(entry.get("additional_requirements", [])):
                db.execute(
                    """INSERT INTO jd_requirements(requirement_id, jd_id, jd_version, source_excerpt, normalized_text, requirement_type, skill_code, in_catalog,
                           target_level, weight, confidence, mapping_rule, needs_confirmation, payload)
                       VALUES (?, ?, 1, ?, ?, 'UNSPECIFIED', NULL, 0, NULL, 0, 1.0, 'OUTSIDE_CATALOG', 0, ?)""",
                    (f"{entry['jd_id']}-X{index}", entry["jd_id"], label, label, dumps({"label": label, "excerpt_kind": "PARAPHRASE"})),
                )
        for resource in resources["resources"]:
            if db.one("SELECT 1 FROM learning_resources WHERE resource_id = ?", (resource["resource_id"],)):
                continue
            db.execute(
                """INSERT INTO learning_resources(resource_id, resource_version, is_current, status, link_status, last_checked_at, next_review_at,
                       reviewer_id, payload, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                (resource["resource_id"], resource["resource_version"], resource["status"], resource["link_status"], resource["last_checked_at"],
                 resource["next_review_at"], resource["reviewer_id"], dumps(resource), now),
            )


def _resource_view(row: dict) -> dict:
    payload = json.loads(row["payload"])
    payload.update({key: row[key] for key in ("resource_id", "resource_version", "status", "link_status", "last_checked_at", "next_review_at", "reviewer_id")})
    return payload


def is_usable(resource: dict) -> bool:
    """Only approved resources with a working or not-yet-disproved link reach learners."""
    return resource["status"] == "APPROVED" and resource["link_status"] in USABLE_RESOURCE_LINK and bool(resource.get("last_checked_at"))


def list_resources(db: Database, approved_only: bool = True) -> list[dict]:
    rows = db.query("SELECT * FROM learning_resources WHERE is_current = 1 ORDER BY resource_id")
    resources = [_resource_view(row) for row in rows]
    return [item for item in resources if is_usable(item)] if approved_only else resources


def get_resource(db: Database, resource_id: str) -> Optional[dict]:
    row = db.one("SELECT * FROM learning_resources WHERE resource_id = ? AND is_current = 1", (resource_id,))
    return _resource_view(row) if row else None


def save_resource_version(db: Database, resource: dict) -> dict:
    """Append a new immutable version and make it current."""
    resource_id = resource["resource_id"]
    latest = db.one("SELECT MAX(resource_version) AS version FROM learning_resources WHERE resource_id = ?", (resource_id,))
    version = int((latest or {}).get("version") or 0) + 1
    record = {**resource, "resource_version": version}
    with db.transaction():
        db.execute("UPDATE learning_resources SET is_current = 0 WHERE resource_id = ?", (resource_id,))
        db.execute(
            """INSERT INTO learning_resources(resource_id, resource_version, is_current, status, link_status, last_checked_at, next_review_at,
                   reviewer_id, payload, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)""",
            (resource_id, version, record.get("status", "DRAFT"), record.get("link_status", "UNCHECKED"), record.get("last_checked_at"),
             record.get("next_review_at"), record.get("reviewer_id"), dumps(record), utcnow().isoformat()),
        )
    return get_resource(db, resource_id)


def update_resource_state(db: Database, resource_id: str, **fields: Any) -> Optional[dict]:
    """Status and link checks change the current version in place; content edits use a new version."""
    allowed = {"status", "link_status", "last_checked_at", "next_review_at", "reviewer_id"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        db.execute(f"UPDATE learning_resources SET {assignments} WHERE resource_id = ? AND is_current = 1", (*updates.values(), resource_id))
    return get_resource(db, resource_id)
