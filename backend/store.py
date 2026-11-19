"""CareerAdapt AI v4.0 - Runtime store.

Catalogs and learner state are held in memory for fast access and written through to SQLite
(backend/database.py), so a restart keeps profiles, submissions, assessments and history.

Several server processes (5.34): each process keeps its own copy, so every write bumps a revision
counter in ``sync_revisions`` and every request first reloads what another process changed
(``sync_user``, ``sync_content``). Changes to one learner are serialized across processes by a
row in ``user_locks`` held for the whole request (``user_scope``), so two requests never apply
their changes to two different copies and lose one of them.
"""
from __future__ import annotations
import contextvars
import uuid
import copy
import json
import os
import socket
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from backend.ai_service.knowledge import seed_knowledge
from backend.catalog import seed_catalogs
from backend.clock import utcnow
from backend.database import Database, dumps
from data.seed import load_skills, load_tasks, load_activities, load_job_profiles, load_question_bank

UUID_FIELDS = ("submission_id", "assessment_id", "user_id")
PROCESS_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
# A crashed holder frees the learner after this long; a request or a grading step is far shorter.
LOCK_LEASE_SECONDS = float(os.getenv("CAREERADAPT_USER_LOCK_LEASE", "120"))
LOCK_WAIT_SECONDS = float(os.getenv("CAREERADAPT_USER_LOCK_WAIT", "25"))
SHARED_SCOPES = ("content", "reviews")
# Learners whose lock this request or job already holds, so nested calls do not wait on themselves.
_held: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar("careeradapt_user_locks", default=())


class UserBusy(RuntimeError):
    """Another process kept this learner locked for longer than LOCK_WAIT_SECONDS."""


def _restore_uuids(record: dict) -> dict:
    """JSON payloads hold ids as text; runtime records compare them as UUID objects."""
    for field in UUID_FIELDS:
        value = record.get(field)
        if isinstance(value, str):
            try:
                record[field] = uuid.UUID(value)
            except ValueError:
                pass
    return record


class InMemoryStore:
    def __init__(self):
        self._persistence_enabled = "pytest" not in sys.modules and os.environ.get("CAREERADAPT_DISABLE_PERSISTENCE") != "1"
        data_dir = Path(__file__).resolve().parents[1] / "data"
        # Legacy learner file: read once on first start, never modified.
        self._runtime_path = Path(os.environ.get("CAREERADAPT_STATE_PATH", str(data_dir / "learner_state_v1.json")))
        self.db = Database(os.environ.get("CAREERADAPT_DB", str(data_dir / "careeradapt.sqlite3")) if self._persistence_enabled else ":memory:")
        # Admin edits to the question bank live in an overrides file next to the seed bank, so the
        # curated seed file stays untouched and a restart keeps every edit (and the bumped version).
        self._question_bank_overrides_path = Path(os.environ.get(
            "CAREERADAPT_QUESTION_BANK_OVERRIDES_PATH",
            str(Path(__file__).resolve().parents[1] / "data" / "question_bank_overrides_v1.json")
        ))
        # Seeding and the first load happen one process at a time (several server processes may start together).
        with self.db.startup_lock():
            self.reset()
            self._load_persisted_user_state()

    def reset(self):
        """Reset store to default initial state from seed data files."""
        self._load_catalogs()

        # 2. Dynamic User & Runtime Data
        self.profiles: dict[uuid.UUID, dict] = {}
        self.submissions: dict[uuid.UUID, dict] = {}
        self.assessments: dict[uuid.UUID, dict] = {}
        self.progress_assessment_history: dict[uuid.UUID, list[dict]] = {}
        self.roadmaps: dict[uuid.UUID, dict] = {}
        self.review_queue: list[dict] = []
        self.test_attempts: dict[str, dict] = {}
        # Revision of each scope this process last loaded or wrote (see sync_user).
        self._revisions: dict[str, int] = {}
        if not self._persistence_enabled:
            self.db.clear()
        seed_catalogs(self.db)
        seed_knowledge(self.db)

    def _load_catalogs(self) -> None:
        """Skills, tasks, activities, job profiles and the question bank: seed files plus admin edits."""
        # 1. Base Framework Catalogs
        skills_file = load_skills()
        self.career_metadata = {
            "career_code": skills_file["career_code"],
            "career_title": skills_file["career_title"],
            "version_tag": skills_file["version_tag"],
            "target_stage": skills_file.get("target_stage", "Chuẩn bị thực tập"),
            "published_at": "2026-01-15T08:00:00Z"
        }
        self.skills: list[dict] = skills_file["skills"]
        self.tasks: list[dict] = load_tasks()
        self.task_versions: dict[str, list[dict]] = {}
        self.activities: list[dict] = load_activities()
        self._apply_content_state()
        for task in self.tasks:
            task.setdefault("content_version", 1)
            self.task_versions.setdefault(task["task_id"], [copy.deepcopy(task)])
        self.job_profiles: list[dict] = load_job_profiles()
        bank = load_question_bank()
        self.question_bank_version: str = bank["bank_version"]
        self.difficulty_points: dict = bank["difficulty_points"]
        self.test_blueprints: list[dict] = bank["blueprints"]
        self.question_items: list[dict] = bank["items"]
        for item in self.question_items:
            item.setdefault("status", "ACTIVE")
        self._apply_question_bank_overrides()

    def _apply_content_state(self) -> None:
        """Administrator edits to skills, tasks and activities replace the seed files."""
        if not self._persistence_enabled:
            return
        for row in self.db.query("SELECT key, payload FROM content_state"):
            value = json.loads(row["payload"])
            if row["key"] == "skills":
                self.skills = value
            elif row["key"] == "tasks":
                self.tasks = value
            elif row["key"] == "activities":
                self.activities = value
            elif row["key"] == "task_versions":
                self.task_versions = value

    def persist_content(self, *keys: str) -> None:
        """Write administrator content changes; call after mutating the matching catalog."""
        now = utcnow().isoformat()
        for key in keys:
            self.db.execute(
                "INSERT INTO content_state(key, payload, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
                (key, dumps(getattr(self, key)), now),
            )
        if keys:
            self._bump("content")

    def _load_persisted_user_state(self) -> None:
        """Restore learner state, submissions and assessments after a restart."""
        if not self._persistence_enabled:
            return
        self._import_legacy_state()
        for row in self.db.query("SELECT user_id, payload FROM learner_state"):
            self._hydrate_learner(uuid.UUID(row["user_id"]), json.loads(row["payload"]))
        for row in self.db.query("SELECT payload FROM assessment_attempts"):
            record = _restore_uuids(json.loads(row["payload"]))
            self.submissions[record["submission_id"]] = record
        for row in self.db.query("SELECT payload FROM final_assessments"):
            record = _restore_uuids(json.loads(row["payload"]))
            self.assessments[record["submission_id"]] = record
            if record.get("status") == "NEEDS_REVIEW":
                self.review_queue.append(self._review_item(record))
        self._revisions = {row["scope"]: row["revision"] for row in self.db.query("SELECT scope, revision FROM sync_revisions")}

    @staticmethod
    def _review_item(record: dict) -> dict:
        return _restore_uuids(copy.deepcopy(record.get("review_item")) or {
            "submission_id": str(record["submission_id"]), "user_id": str(record["user_id"]), "task_id": record.get("task_id"),
            "reason": record.get("review_reason") or "Cần người chấm xác nhận.", "created_at": record.get("created_at"),
        })

    # ------------------------------------------------------------------
    # Several processes on one database
    # ------------------------------------------------------------------
    def _bump(self, scope: str) -> None:
        """Record that this process changed ``scope``; the others reload it on their next request."""
        row = self.db.query("INSERT INTO sync_revisions(scope, revision) VALUES (?, 1) ON CONFLICT(scope) DO UPDATE SET revision = revision + 1 RETURNING revision", (scope,))
        self._revisions[scope] = row[0]["revision"]

    def _stored_revision(self, scope: str) -> int:
        row = self.db.one("SELECT revision FROM sync_revisions WHERE scope = ?", (scope,))
        return row["revision"] if row else 0

    def _forget_user(self, user_id: uuid.UUID) -> None:
        for container in (self.profiles, self.roadmaps, self.progress_assessment_history):
            container.pop(user_id, None)
        for key in [key for key, item in self.submissions.items() if item.get("user_id") == user_id]:
            self.submissions.pop(key, None)
        for key in [key for key, item in self.assessments.items() if item.get("user_id") == user_id]:
            self.assessments.pop(key, None)
        for key in [key for key, item in self.test_attempts.items() if item.get("user_id") == str(user_id)]:
            self.test_attempts.pop(key, None)

    def _reload_user(self, user_id: uuid.UUID) -> None:
        """Replace this process's copy of one learner with what the database holds now."""
        self._forget_user(user_id)
        key = str(user_id)
        row = self.db.one("SELECT payload FROM learner_state WHERE user_id = ?", (key,))
        if row:
            self._hydrate_learner(user_id, json.loads(row["payload"]))
        for row in self.db.query("SELECT payload FROM assessment_attempts WHERE user_id = ?", (key,)):
            record = _restore_uuids(json.loads(row["payload"]))
            self.submissions[record["submission_id"]] = record
        for row in self.db.query("SELECT payload FROM final_assessments WHERE user_id = ?", (key,)):
            record = _restore_uuids(json.loads(row["payload"]))
            self.assessments[record["submission_id"]] = record

    def sync_user(self, user_id: uuid.UUID) -> bool:
        """Reload one learner if another process changed them. Returns True when a reload happened."""
        scope = str(user_id)
        stored = self._stored_revision(scope)
        if stored == self._revisions.get(scope, 0):
            return False
        self._reload_user(user_id)
        self._revisions[scope] = stored
        return True

    def sync_content(self) -> bool:
        """Reload skills, tasks, activities and the question bank if an administrator changed them elsewhere."""
        stored = self._stored_revision("content")
        if stored == self._revisions.get("content", 0):
            return False
        self._load_catalogs()
        self._revisions["content"] = stored
        return True

    def sync_reviews(self) -> bool:
        """Rebuild the human-review queue if another process added to it or resolved an item."""
        stored = self._stored_revision("reviews")
        if stored == self._revisions.get("reviews", 0):
            return False
        self.review_queue = [self._review_item(_restore_uuids(json.loads(row["payload"])))
                             for row in self.db.query("SELECT payload FROM final_assessments WHERE status = 'NEEDS_REVIEW' ORDER BY created_at")]
        self._revisions["reviews"] = stored
        return True

    def sync_all(self) -> int:
        """Bring every learner this process holds or should hold up to date (background work, cross-learner views)."""
        reloaded = 0
        self.sync_content()
        self.sync_reviews()
        for row in self.db.query("SELECT scope, revision FROM sync_revisions"):
            if row["scope"] in SHARED_SCOPES or row["revision"] == self._revisions.get(row["scope"], 0):
                continue
            try:
                user_id = uuid.UUID(row["scope"])
            except ValueError:
                continue
            self._reload_user(user_id)
            self._revisions[row["scope"]] = row["revision"]
            reloaded += 1
        return reloaded

    def acquire_user(self, user_id: uuid.UUID) -> str:
        """Hold the learner across every process; returns the owner token for release_user. Blocks while another holds it."""
        key = str(user_id)
        owner = f"{PROCESS_ID}:{uuid.uuid4().hex[:8]}"
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            now = time.time()
            with self.db.transaction():
                self.db.execute("DELETE FROM user_locks WHERE user_id = ? AND expires_at < ?", (key, now))
                self.db.execute("INSERT OR IGNORE INTO user_locks(user_id, owner, expires_at) VALUES (?, ?, ?)", (key, owner, now + LOCK_LEASE_SECONDS))
                holder = self.db.one("SELECT owner FROM user_locks WHERE user_id = ?", (key,))
            if holder and holder["owner"] == owner:
                return owner
            if time.monotonic() > deadline:
                raise UserBusy(key)
            time.sleep(0.05)

    def release_user(self, user_id: uuid.UUID, owner: str) -> None:
        self.db.execute("DELETE FROM user_locks WHERE user_id = ? AND owner = ?", (str(user_id), owner))

    @staticmethod
    def holds(user_id: uuid.UUID) -> bool:
        return str(user_id) in _held.get()

    @staticmethod
    def mark_held(user_id: uuid.UUID) -> contextvars.Token:
        return _held.set(_held.get() + (str(user_id),))

    @staticmethod
    def unmark_held(token: contextvars.Token) -> None:
        _held.reset(token)

    @contextmanager
    def user_scope(self, user_id: uuid.UUID):
        """Change one learner safely from outside a request (a grading job) or for another learner (a reviewer).

        Takes the learner's lock unless this context already holds it, then reloads the learner's copy so the
        change starts from the latest state."""
        if self.holds(user_id):
            self.sync_user(user_id)
            yield
            return
        owner = self.acquire_user(user_id)
        token = self.mark_held(user_id)
        try:
            self.sync_content()
            self.sync_user(user_id)
            yield
        finally:
            self.unmark_held(token)
            self.release_user(user_id, owner)

    def _import_legacy_state(self) -> None:
        """One-way import of data/learner_state_v1.json; the file is left in place as a backup."""
        if self.db.get_meta("legacy_learner_state_imported") or not self._runtime_path.exists():
            return
        try:
            loaded = json.loads(self._runtime_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return  # Keep the file for inspection and start without it.
        if not isinstance(loaded, dict):
            return
        with self.db.transaction():
            for raw_user_id, saved in loaded.items():
                try:
                    user_id = uuid.UUID(raw_user_id)
                except (ValueError, TypeError):
                    continue
                if not isinstance(saved, dict):
                    continue
                versions = saved.pop("roadmap_history", None) or []
                self.db.execute(
                    "INSERT OR IGNORE INTO learner_state(user_id, payload, updated_at) VALUES (?, ?, ?)",
                    (str(user_id), dumps(saved), str(saved.get("updated_at") or utcnow().isoformat())),
                )
                # Old history can repeat a version number, so number by position to keep every entry.
                for index, version in enumerate(v for v in versions if isinstance(v, dict)):
                    imported = {**version, "roadmap_id": str(uuid.uuid4()), "roadmap_version": index + 1, "legacy_roadmap_version": version.get("roadmap_version")}
                    self.save_roadmap_version(user_id, imported, change_reason="Nhập từ dữ liệu phiên bản trước")
            self.db.set_meta("legacy_learner_state_imported", utcnow().isoformat())

    def _hydrate_learner(self, user_id: uuid.UUID, saved: dict) -> None:
        profile = saved.get("profile")
        if isinstance(profile, dict):
            profile["user_id"] = user_id
            self.profiles[user_id] = profile
        activity_progress = saved.get("activity_progress") if isinstance(saved.get("activity_progress"), dict) else {}
        if isinstance(saved.get("roadmap"), dict) and saved["roadmap"]:
            self.roadmaps[user_id] = _restore_uuids(saved["roadmap"])
        elif profile or activity_progress:
            self.roadmaps[user_id] = {
                "user_id": user_id,
                "activity_progress": activity_progress,
                "activity_week_assignments": saved.get("activity_week_assignments", {}),
                "updated_at": saved.get("updated_at", utcnow().isoformat()),
            }
        history = saved.get("assessment_history")
        history = [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []
        if history:
            self.progress_assessment_history[user_id] = history
        for attempt in saved.get("test_attempts", []) or []:
            if isinstance(attempt, dict) and attempt.get("attempt_id"):
                attempt["user_id"] = str(user_id)
                self.test_attempts[attempt["attempt_id"]] = attempt

    @staticmethod
    def _atomic_write_json(path: Path, payload: Any) -> None:
        """Write JSON to a temp file then replace, so a crash never leaves a half-written file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary_path.replace(path)

    # ------------------------------------------------------------------
    # Question bank versioning
    # ------------------------------------------------------------------
    def _apply_question_bank_overrides(self) -> None:
        if not self._persistence_enabled or not self._question_bank_overrides_path.exists():
            return
        try:
            saved = json.loads(self._question_bank_overrides_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(saved, dict):
            return
        for item in saved.get("items", []) or []:
            if isinstance(item, dict) and item.get("item_id"):
                self._upsert_question_item(item)
        if isinstance(saved.get("bank_version"), str):
            self.question_bank_version = saved["bank_version"]

    def _upsert_question_item(self, item: dict) -> dict:
        existing = self.get_question_item(item["item_id"])
        if existing is None:
            self.question_items.append(item)
            return item
        existing.clear()
        existing.update(item)
        return existing

    @staticmethod
    def next_bank_version(version: str) -> str:
        """QB-DA-1.0 -> QB-DA-1.1; a version without a numeric minor gets '.1' appended."""
        head, _, minor = version.rpartition(".")
        if head and minor.isdigit():
            return f"{head}.{int(minor) + 1}"
        return f"{version}.1"

    def save_question_item(self, item: dict) -> dict:
        """Create or replace a bank item, bump the bank version and persist the edit durably.

        Attempts freeze their items and bank_version at start, so earlier attempts keep scoring
        against the content they were given."""
        saved = self._upsert_question_item(copy.deepcopy(item))
        self.question_bank_version = self.next_bank_version(self.question_bank_version)
        if self._persistence_enabled:
            overrides: dict[str, Any] = {"items": []}
            if self._question_bank_overrides_path.exists():
                try:
                    loaded = json.loads(self._question_bank_overrides_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict) and isinstance(loaded.get("items"), list):
                        overrides = loaded
                except (OSError, json.JSONDecodeError):
                    pass
            overrides["items"] = [i for i in overrides["items"] if isinstance(i, dict) and i.get("item_id") != saved["item_id"]]
            overrides["items"].append(copy.deepcopy(saved))
            overrides["bank_version"] = self.question_bank_version
            overrides["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._atomic_write_json(self._question_bank_overrides_path, overrides)
        self._bump("content")
        return saved

    def persist_user_runtime(self, user_id: uuid.UUID) -> None:
        """Write the learner's profile, roadmap and compact histories in one row."""
        user_key = str(user_id)
        profile = copy.deepcopy(self.profiles.get(user_id))
        if profile:
            profile.pop("user_id", None)
        roadmap = self.roadmaps.get(user_id, {})
        history = copy.deepcopy(self.progress_assessment_history.get(user_id, []))
        attempts = copy.deepcopy(self.user_test_attempts(user_id))
        if not profile and not roadmap and not history and not attempts:
            self.db.execute("DELETE FROM learner_state WHERE user_id = ?", (user_key,))
            self._bump(user_key)
            return
        now = utcnow().isoformat()
        payload = {
            "profile": profile,
            "roadmap": roadmap,
            "assessment_history": history,
            "test_attempts": attempts,
            "updated_at": roadmap.get("updated_at", now),
        }
        self.db.execute(
            "INSERT INTO learner_state(user_id, payload, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
            (user_key, dumps(payload), now),
        )
        self._bump(user_key)

    # ------------------------------------------------------------------
    # Assessment records (write-through)
    # ------------------------------------------------------------------
    def save_submission(self, record: dict) -> None:
        self.submissions[record["submission_id"]] = record
        self.db.execute(
            """INSERT INTO assessment_attempts(submission_id, user_id, task_id, task_version, mode, status, idempotency_key,
                   content_hash, grade_attempts, started_at, submitted_at, updated_at, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(submission_id) DO UPDATE SET status = excluded.status, grade_attempts = excluded.grade_attempts,
                   updated_at = excluded.updated_at, payload = excluded.payload""",
            (str(record["submission_id"]), str(record["user_id"]), record.get("task_id", ""), record.get("task_version"),
             record.get("mode", "ASSESSMENT"), record.get("status", "RECEIVED"), record.get("idempotency_key"),
             record.get("content_hash"), int(record.get("grade_attempts", 0)), record.get("started_at"),
             record.get("submitted_at") or utcnow().isoformat(), utcnow().isoformat(), dumps(record)),
        )
        self._bump(str(record["user_id"]))

    def save_assessment(self, record: dict) -> None:
        self.assessments[record["submission_id"]] = record
        now = utcnow().isoformat()
        review = record.get("human_review") or {}
        self.db.execute(
            """INSERT INTO final_assessments(submission_id, user_id, task_id, mode, status, final_score, passed, final_level,
                   reviewer_id, reason, created_at, updated_at, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(submission_id) DO UPDATE SET status = excluded.status, final_score = excluded.final_score,
                   passed = excluded.passed, final_level = excluded.final_level, reviewer_id = excluded.reviewer_id,
                   reason = excluded.reason, updated_at = excluded.updated_at, payload = excluded.payload""",
            (str(record["submission_id"]), str(record["user_id"]), record.get("task_id", ""), record.get("mode", "ASSESSMENT"),
             record.get("status", ""), record.get("final_score"), None if record.get("passed") is None else int(bool(record["passed"])),
             record.get("final_level"), review.get("reviewed_by"), record.get("review_reason"), str(record.get("created_at") or now), now, dumps(record)),
        )
        self._bump(str(record["user_id"]))
        self._bump("reviews")

    def add_skill_evidence(self, user_id: uuid.UUID, skill_code: str, level: int, source_type: str, source_id: str, **details: Any) -> None:
        self.db.execute(
            """INSERT OR IGNORE INTO skill_evidence(evidence_id, user_id, skill_code, level, score, source_type, source_id, task_id,
                   task_version, rubric_version, jd_id, jd_version, mapping_version, scope_note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), str(user_id), skill_code, int(level), details.get("score"), source_type, str(source_id), details.get("task_id"),
             details.get("task_version"), details.get("rubric_version"), details.get("jd_id"), details.get("jd_version"),
             details.get("mapping_version"), details.get("scope_note"), details.get("created_at") or utcnow().isoformat()),
        )

    def skill_evidence(self, user_id: uuid.UUID, skill_code: Optional[str] = None) -> list[dict]:
        sql = "SELECT * FROM skill_evidence WHERE user_id = ? AND archived_by_run IS NULL"
        parameters: list[Any] = [str(user_id)]
        if skill_code:
            sql += " AND skill_code = ?"
            parameters.append(skill_code)
        return self.db.query(sql + " ORDER BY created_at, rowid", parameters)

    # ------------------------------------------------------------------
    # Roadmap history
    # ------------------------------------------------------------------
    def latest_roadmap_version(self, user_id: uuid.UUID) -> int:
        row = self.db.one("SELECT MAX(version) AS version FROM roadmap_versions WHERE user_id = ?", (str(user_id),))
        return int((row or {}).get("version") or 0)

    def save_roadmap_version(self, user_id: uuid.UUID, roadmap: dict, change_reason: str = "") -> None:
        version = int(roadmap.get("roadmap_version") or 1)
        target = roadmap.get("target") or {}
        self.db.execute(
            """INSERT INTO roadmap_versions(roadmap_id, user_id, version, jd_id, jd_version, mapping_version,
                   algorithm_version, change_reason, payload, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(roadmap.get("roadmap_id") or uuid.uuid4()), str(user_id), version, target.get("jd_id"), target.get("jd_version"),
             target.get("mapping_version"), roadmap.get("algorithm_version"), change_reason or roadmap.get("change_reason"),
             dumps(roadmap), str(roadmap.get("created_at") or utcnow().isoformat())),
        )

    def roadmap_history(self, user_id: uuid.UUID) -> list[dict]:
        rows = self.db.query("SELECT payload, change_reason FROM roadmap_versions WHERE user_id = ? AND archived_by_run IS NULL ORDER BY version", (str(user_id),))
        return [{**json.loads(row["payload"]), "change_reason": row["change_reason"]} for row in rows]

    def record_progress_assessment(self, user_id: uuid.UUID, assessment: dict) -> None:
        """Keep a compact, comparable assessment snapshot without storing learner work."""
        submission_id = str(assessment.get("submission_id", assessment.get("assessment_id", "")))
        if not submission_id:
            return
        snapshot = {
            "submission_id": submission_id,
            "task_id": assessment.get("task_id"),
            "mode": assessment.get("mode"),
            "status": assessment.get("status"),
            "final_level": assessment.get("final_level"),
            "final_score": assessment.get("final_score"),
            "passed": assessment.get("passed"),
            "task_version": assessment.get("task_version"),
            "criteria_snapshot": assessment.get("criteria_snapshot"),
            "per_skill_results": copy.deepcopy(assessment.get("per_skill_results", {})),
            "created_at": assessment.get("created_at", datetime.now(timezone.utc).isoformat()),
            "progress_comparison": copy.deepcopy(assessment.get("progress_comparison"))
        }
        history = self.progress_assessment_history.setdefault(user_id, [])
        existing_index = next((index for index, item in enumerate(history) if item.get("submission_id") == submission_id), None)
        if existing_index is None:
            history.append(snapshot)
        else:
            history[existing_index] = snapshot
        history.sort(key=lambda item: item.get("created_at", ""))

    def user_test_attempts(self, user_id: uuid.UUID) -> list[dict]:
        return sorted((a for a in self.test_attempts.values() if a.get("user_id") == str(user_id)), key=lambda a: a.get("started_at", ""))

    def get_question_item(self, item_id: str) -> Optional[dict]:
        return next((item for item in self.question_items if item["item_id"] == item_id), None)

    def get_blueprint(self, blueprint_id: str) -> Optional[dict]:
        return next((bp for bp in self.test_blueprints if bp["blueprint_id"] == blueprint_id), None)

    def get_skill(self, skill_code: str) -> Optional[dict]:
        for s in self.skills:
            if s["skill_code"] == skill_code:
                return s
        return None

    def get_task(self, task_id: str) -> Optional[dict]:
        for t in self.tasks:
            if t["task_id"] == task_id or t.get("base_id") == task_id:
                return t
        return None

    def get_activity(self, activity_id: str) -> Optional[dict]:
        for a in self.activities:
            if a["activity_id"] == activity_id:
                return a
        return None

    def get_job_profile(self, profile_id: str) -> Optional[dict]:
        for profile in self.job_profiles:
            if profile["profile_id"] == profile_id:
                return profile
        return None

    def archive_task_version(self, task: dict) -> None:
        """Keep a copy of each task definition used by past submissions."""
        task_id = task["task_id"]
        versions = self.task_versions.setdefault(task_id, [])
        current_version = task.get("content_version", 1)
        if not any(item.get("content_version") == current_version for item in versions):
            versions.append(copy.deepcopy(task))

    def get_or_create_profile(self, user_id: uuid.UUID) -> dict:
        if user_id not in self.profiles:
            self.profiles[user_id] = {
                "user_id": user_id,
                "target_career_id": "DATA_ANALYST",
                "target_career_version": self.career_metadata["version_tag"],
                "job_profile_id": "VN_ENTRY_ANALYST",
                "weekly_hours_budget": 4.0,
                "target_timeline_weeks": 8,
                "major": "Công nghệ thông tin / Toán tin",
                # A new profile starts unassessed and undeclared; learners enter their own baseline.
                "self_reported_skills": [],
                "assessed_skills": {},  # skill_code -> {"level": int, "submission_id": uuid, "assessed_at": str}
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        return self.profiles[user_id]

    def add_history_event(self, user_id: uuid.UUID, event_type: str, detail: str, version: str = "v4.0", meta: Optional[dict] = None):
        self.db.execute(
            "INSERT INTO history_events(event_id, user_id, event, time, version, detail, meta) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), str(user_id), event_type, utcnow().isoformat(), version, detail, dumps(meta) if meta else None),
        )

    def history_events(self, user_id: uuid.UUID) -> list[dict]:
        rows = self.db.query("SELECT event_id, event, time, version, detail, meta FROM history_events WHERE user_id = ? AND archived_by_run IS NULL ORDER BY time, rowid", (str(user_id),))
        return [{**row, "meta": json.loads(row["meta"]) if row["meta"] else None} for row in rows]

    def log_security_event(self, user_id: Optional[uuid.UUID], event: str, detail: str) -> None:
        self.db.execute(
            "INSERT INTO security_events(event_id, user_id, event, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), str(user_id) if user_id else None, event, detail, utcnow().isoformat()),
        )

    def purge_user_data(self, user_id: uuid.UUID) -> int:
        """Right to erasure: delete the learner's profile, history, submissions and roadmaps."""
        records_deleted = 0
        for container in (self.profiles, self.roadmaps, self.progress_assessment_history):
            if user_id in container:
                del container[user_id]
                records_deleted += 1

        user_subs = [s_id for s_id, s in self.submissions.items() if s.get("user_id") == user_id]
        for s_id in user_subs:
            del self.submissions[s_id]
            records_deleted += 1
            if s_id in self.assessments:
                del self.assessments[s_id]
                records_deleted += 1

        for attempt_id in [a["attempt_id"] for a in self.user_test_attempts(user_id)]:
            del self.test_attempts[attempt_id]
            records_deleted += 1

        self.review_queue = [r for r in self.review_queue if r.get("user_id") != user_id]
        records_deleted += self.db.purge_user(str(user_id))
        self._bump(str(user_id))
        self.log_security_event(user_id, "DATA_ERASED", "Người dùng yêu cầu xóa hồ sơ và bài nộp.")
        return records_deleted


# Global singleton instance
store = InMemoryStore()
