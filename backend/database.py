"""Durable domain store (SQLite) for CareerAdapt AI v4.0.

Queryable columns carry the guarantees the spec asks for at the database level: one Assessment per
submission, one idempotency key per user, one reminder per dedupe key, one mini-test per due date.
Full records stay in a JSON ``payload`` column so an entity can grow without a migration.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from backend.filelock import exclusive

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS learner_state (
    user_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history_events (
    event_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, event TEXT NOT NULL, time TEXT NOT NULL,
    version TEXT, detail TEXT, meta TEXT, archived_by_run TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_user ON history_events(user_id, time);

-- Content administrators can change; a row replaces the matching seed file.
CREATE TABLE IF NOT EXISTS content_state (key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);

-- JD library and learner-imported JDs (versions are immutable).
CREATE TABLE IF NOT EXISTS job_descriptions (
    jd_id TEXT PRIMARY KEY, origin TEXT NOT NULL, owner_user_id TEXT, title TEXT NOT NULL, employer TEXT,
    role_level TEXT, industry TEXT, language TEXT, latest_version INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jd_versions (
    jd_id TEXT NOT NULL, jd_version INTEGER NOT NULL, raw_text TEXT, raw_text_hash TEXT NOT NULL,
    source_url TEXT, source_type TEXT, source_date TEXT, file_name TEXT, mapping_version TEXT NOT NULL,
    review_status TEXT NOT NULL, reviewer_id TEXT, reviewed_at TEXT, last_checked_at TEXT, next_review_at TEXT,
    link_status TEXT, scope_status TEXT, payload TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (jd_id, jd_version)
);
CREATE TABLE IF NOT EXISTS jd_requirements (
    requirement_id TEXT PRIMARY KEY, jd_id TEXT NOT NULL, jd_version INTEGER NOT NULL, source_excerpt TEXT,
    normalized_text TEXT, requirement_type TEXT NOT NULL, skill_code TEXT, in_catalog INTEGER NOT NULL,
    target_level INTEGER, weight REAL, confidence REAL NOT NULL, mapping_rule TEXT, needs_confirmation INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jd_req ON jd_requirements(jd_id, jd_version);
CREATE TABLE IF NOT EXISTS target_versions (
    target_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, version INTEGER NOT NULL, jd_id TEXT, jd_version INTEGER,
    mapping_version TEXT, config_id TEXT, payload TEXT NOT NULL, created_at TEXT NOT NULL, archived_by_run TEXT,
    UNIQUE (user_id, version)
);

-- Assessment trail.
CREATE TABLE IF NOT EXISTS assessment_attempts (
    submission_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT NOT NULL, task_version INTEGER,
    mode TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT, content_hash TEXT, grade_attempts INTEGER NOT NULL DEFAULT 0,
    started_at TEXT, submitted_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload TEXT NOT NULL,
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_attempt_user ON assessment_attempts(user_id, submitted_at);
CREATE INDEX IF NOT EXISTS idx_attempt_status ON assessment_attempts(status);
CREATE TABLE IF NOT EXISTS submission_answers (
    submission_id TEXT NOT NULL, question_id TEXT NOT NULL, answer_text TEXT, answer_hash TEXT NOT NULL,
    format_validation TEXT NOT NULL, submitted_at TEXT NOT NULL,
    PRIMARY KEY (submission_id, question_id)
);
CREATE TABLE IF NOT EXISTS test_case_results (
    submission_id TEXT NOT NULL, test_case_id TEXT NOT NULL, version TEXT NOT NULL, criterion_id TEXT,
    expected_summary TEXT, actual_summary TEXT, passed INTEGER NOT NULL, points_awarded REAL NOT NULL, points_max REAL NOT NULL,
    failure_code TEXT, PRIMARY KEY (submission_id, test_case_id)
);
CREATE TABLE IF NOT EXISTS rubric_scores (
    submission_id TEXT NOT NULL, criterion_id TEXT NOT NULL, version TEXT NOT NULL, skill_code TEXT,
    points_awarded REAL NOT NULL, max_points REAL NOT NULL, level_proposed INTEGER, level_accepted INTEGER,
    critical_flag INTEGER NOT NULL, rule_version TEXT NOT NULL, PRIMARY KEY (submission_id, criterion_id)
);
CREATE TABLE IF NOT EXISTS ai_feedback_traces (
    trace_id TEXT PRIMARY KEY, submission_id TEXT NOT NULL, grade_attempt INTEGER NOT NULL, provider TEXT, model TEXT,
    prompt_version TEXT, rubric_version TEXT, response_schema_version TEXT, evidence_refs TEXT,
    validation_result TEXT NOT NULL, latency_ms INTEGER, error TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trace_submission ON ai_feedback_traces(submission_id);
CREATE TABLE IF NOT EXISTS final_assessments (
    submission_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
    final_score REAL, passed INTEGER, final_level INTEGER, reviewer_id TEXT, reason TEXT, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_final_user ON final_assessments(user_id, created_at);
-- Append-only: the current level of a skill is the latest row, the history is the chart.
CREATE TABLE IF NOT EXISTS skill_evidence (
    evidence_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, skill_code TEXT NOT NULL, level INTEGER NOT NULL, score REAL,
    source_type TEXT NOT NULL, source_id TEXT NOT NULL, task_id TEXT, task_version INTEGER, rubric_version TEXT,
    jd_id TEXT, jd_version INTEGER, mapping_version TEXT, scope_note TEXT, created_at TEXT NOT NULL, archived_by_run TEXT,
    UNIQUE (source_id, skill_code)
);
CREATE INDEX IF NOT EXISTS idx_evidence_user ON skill_evidence(user_id, skill_code, created_at);
CREATE TABLE IF NOT EXISTS calibration_samples (
    sample_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, anonymized_text TEXT NOT NULL, reference_level INTEGER NOT NULL,
    system_level INTEGER, reviewer_scores TEXT, disagreement_type TEXT, split TEXT NOT NULL, approved INTEGER NOT NULL,
    consent_basis TEXT, created_by TEXT, created_at TEXT NOT NULL
);

-- Learning catalog.
CREATE TABLE IF NOT EXISTS learning_resources (
    resource_id TEXT NOT NULL, resource_version INTEGER NOT NULL, is_current INTEGER NOT NULL, status TEXT NOT NULL,
    link_status TEXT NOT NULL, last_checked_at TEXT, next_review_at TEXT, reviewer_id TEXT, payload TEXT NOT NULL,
    created_at TEXT NOT NULL, PRIMARY KEY (resource_id, resource_version)
);
CREATE INDEX IF NOT EXISTS idx_resource_current ON learning_resources(is_current, status);

-- Roadmap and progress history.
CREATE TABLE IF NOT EXISTS roadmap_versions (
    roadmap_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, version INTEGER NOT NULL, jd_id TEXT, jd_version INTEGER,
    mapping_version TEXT, algorithm_version TEXT, change_reason TEXT, payload TEXT NOT NULL, created_at TEXT NOT NULL, archived_by_run TEXT,
    UNIQUE (user_id, version)
);
CREATE TABLE IF NOT EXISTS progress_records (
    record_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, activity_id TEXT NOT NULL, roadmap_version INTEGER,
    from_status TEXT, to_status TEXT NOT NULL, progress_percent INTEGER, note TEXT, created_at TEXT NOT NULL, archived_by_run TEXT
);
CREATE INDEX IF NOT EXISTS idx_progress_user ON progress_records(user_id, created_at);

-- Review cycles, mini-tests and reminders.
CREATE TABLE IF NOT EXISTS learning_checkins (
    checkin_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, activity_id TEXT NOT NULL, skill_code TEXT NOT NULL,
    roadmap_version INTEGER, cycle_days INTEGER NOT NULL, anchor_date TEXT NOT NULL, due_at TEXT NOT NULL, timezone TEXT NOT NULL,
    status TEXT NOT NULL, superseded_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkin_due ON learning_checkins(status, due_at);
CREATE INDEX IF NOT EXISTS idx_checkin_user ON learning_checkins(user_id, activity_id);
CREATE TABLE IF NOT EXISTS micro_assessments (
    micro_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, checkin_id TEXT NOT NULL, due_at TEXT NOT NULL, skill_code TEXT NOT NULL,
    activity_id TEXT NOT NULL, status TEXT NOT NULL, bank_version TEXT, idempotency_key TEXT, attempts INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL, created_at TEXT NOT NULL, submitted_at TEXT,
    UNIQUE (checkin_id, due_at)
);
CREATE INDEX IF NOT EXISTS idx_micro_user ON micro_assessments(user_id, created_at);
CREATE TABLE IF NOT EXISTS reminder_jobs (
    reminder_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL, ref_id TEXT, dedupe_key TEXT NOT NULL UNIQUE,
    scheduled_at TEXT NOT NULL, sent_at TEXT, status TEXT NOT NULL, snooze_until TEXT, title TEXT NOT NULL, body TEXT,
    payload TEXT, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminder_user ON reminder_jobs(user_id, status);
CREATE TABLE IF NOT EXISTS reminder_preferences (user_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS security_events (
    event_id TEXT PRIMARY KEY, user_id TEXT, event TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL
);

-- Career Adapt process. The partial unique index is the one-process-per-account rule itself.
CREATE TABLE IF NOT EXISTS career_runs (
    run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, career_code TEXT NOT NULL, status TEXT NOT NULL, step TEXT NOT NULL,
    payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT, archived_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_career_run_active ON career_runs(user_id) WHERE status != 'ARCHIVED';
CREATE INDEX IF NOT EXISTS idx_career_run_user ON career_runs(user_id, created_at);
-- One run has one exam: the unique run_id is what makes the test single-attempt.
CREATE TABLE IF NOT EXISTS exam_attempts (
    attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE, user_id TEXT NOT NULL, status TEXT NOT NULL, submission_id TEXT,
    started_at TEXT NOT NULL, expires_at TEXT NOT NULL, submitted_at TEXT, auto_submitted INTEGER NOT NULL DEFAULT 0,
    violations INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exam_status ON exam_attempts(status, expires_at);
CREATE TABLE IF NOT EXISTS exam_responses (
    attempt_id TEXT NOT NULL, question_id TEXT NOT NULL, answer_text TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (attempt_id, question_id)
);
CREATE TABLE IF NOT EXISTS exam_events (
    event_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exam_events ON exam_events(attempt_id);
"""

# The AI platform has its own version key: its tables are all new, so the core schema stays as it is.
AI_SCHEMA_VERSION = 1
AI_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_conversations (
    conversation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, summary TEXT, summarized_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_conversation_user ON ai_conversations(user_id, updated_at);
CREATE TABLE IF NOT EXISTS ai_messages (
    message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
    meta TEXT, created_at TEXT NOT NULL, UNIQUE (conversation_id, seq)
);

-- Shared knowledge. Every version is kept; only a current, approved version can be retrieved.
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id TEXT NOT NULL, version INTEGER NOT NULL, is_current INTEGER NOT NULL, status TEXT NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL,
    origin TEXT NOT NULL, language TEXT, source_url TEXT, body TEXT NOT NULL, content_hash TEXT NOT NULL, meta TEXT, reviewer_id TEXT, reviewed_at TEXT,
    created_by TEXT, created_at TEXT NOT NULL, PRIMARY KEY (document_id, version)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_current ON knowledge_documents(is_current, status);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version INTEGER NOT NULL, ordinal INTEGER NOT NULL, heading TEXT, content TEXT NOT NULL,
    meta TEXT, embedding BLOB, embedding_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunk_document ON knowledge_chunks(document_id, version);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(chunk_id UNINDEXED, heading, content, tokenize = 'unicode61 remove_diacritics 2');

-- Counts and outcomes only: no prompt or reply text is stored here.
CREATE TABLE IF NOT EXISTS ai_usage_traces (
    trace_id TEXT PRIMARY KEY, user_id TEXT, conversation_id TEXT, task TEXT NOT NULL, provider TEXT, model TEXT, status TEXT NOT NULL, error TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0, latency_ms INTEGER, attempts INTEGER NOT NULL DEFAULT 1, detail TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON ai_usage_traces(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_time ON ai_usage_traces(created_at);
"""

# Learning Roadmap 2.0: study time, review cycles, practice and the final assessment. All tables are new,
# so no existing row is touched. Study time and assessment results are kept in separate tables on purpose.
ROADMAP_SCHEMA_VERSION = 1
ROADMAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS lesson_plans (
    plan_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, activity_id TEXT NOT NULL, review_cycle_days INTEGER NOT NULL,
    created_at TEXT NOT NULL, archived_by_run TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_lesson_plan ON lesson_plans(user_id, activity_id) WHERE archived_by_run IS NULL;
CREATE TABLE IF NOT EXISTS study_sessions (
    session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, activity_id TEXT NOT NULL, status TEXT NOT NULL,
    started_at TEXT NOT NULL, segment_started_at TEXT, last_heartbeat_at TEXT, paused_at TEXT, ended_at TEXT,
    accumulated_seconds INTEGER NOT NULL DEFAULT 0, pause_reason TEXT, end_reason TEXT, roadmap_version INTEGER,
    updated_at TEXT NOT NULL, archived_by_run TEXT
);
-- One running timer per account, and one open session per lesson: a second tab joins the same session.
CREATE UNIQUE INDEX IF NOT EXISTS ux_study_running ON study_sessions(user_id) WHERE status = 'RUNNING';
CREATE UNIQUE INDEX IF NOT EXISTS ux_study_open ON study_sessions(user_id, activity_id) WHERE status IN ('RUNNING', 'PAUSED');
CREATE INDEX IF NOT EXISTS idx_study_user ON study_sessions(user_id, activity_id);
CREATE TABLE IF NOT EXISTS practice_attempts (
    attempt_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, activity_id TEXT NOT NULL, exercise_id TEXT NOT NULL,
    answer_text TEXT NOT NULL, score REAL, payload TEXT NOT NULL, created_at TEXT NOT NULL, archived_by_run TEXT
);
CREATE INDEX IF NOT EXISTS idx_practice_user ON practice_attempts(user_id, activity_id);
CREATE TABLE IF NOT EXISTS final_attempts (
    attempt_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, roadmap_version INTEGER, status TEXT NOT NULL,
    started_at TEXT NOT NULL, expires_at TEXT NOT NULL, submitted_at TEXT, auto_submitted INTEGER NOT NULL DEFAULT 0,
    violations INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL, archived_by_run TEXT
);
-- At most one final assessment in progress per account.
CREATE UNIQUE INDEX IF NOT EXISTS ux_final_open ON final_attempts(user_id) WHERE status IN ('IN_PROGRESS', 'SUBMITTED', 'GRADING');
CREATE INDEX IF NOT EXISTS idx_final_user ON final_attempts(user_id, started_at);
"""
ROADMAP_ARCHIVABLE_TABLES = ("lesson_plans", "study_sessions", "practice_attempts", "final_attempts")

# Rows a reset takes out of the learner's view. They stay, tagged with the run that archived them.
ARCHIVABLE_TABLES = ("history_events", "target_versions", "skill_evidence", "roadmap_versions", "progress_records")

USER_TABLES = (
    ("learner_state", "user_id"), ("history_events", "user_id"), ("target_versions", "user_id"),
    ("assessment_attempts", "user_id"), ("final_assessments", "user_id"), ("skill_evidence", "user_id"),
    ("roadmap_versions", "user_id"), ("progress_records", "user_id"), ("learning_checkins", "user_id"),
    ("micro_assessments", "user_id"), ("reminder_jobs", "user_id"), ("reminder_preferences", "user_id"),
    ("career_runs", "user_id"), ("exam_attempts", "user_id"), ("ai_conversations", "user_id"), ("ai_usage_traces", "user_id"),
    ("lesson_plans", "user_id"), ("study_sessions", "user_id"), ("practice_attempts", "user_id"), ("final_attempts", "user_id"),
)
SUBMISSION_TABLES = ("submission_answers", "test_case_results", "rubric_scores", "ai_feedback_traces")

# Foreign keys added by FK_SCHEMA_VERSION 1 (2026-11-15). Only links whose parent lives in this file: user ids
# point into accounts.sqlite3, which SQLite cannot reference. exam_responses and exam_events are left out because
# they hold rows of both exam_attempts and final_attempts. ON DELETE CASCADE matches what purge_user already does.
FK_SCHEMA_VERSION = 1
FOREIGN_KEYS = {
    "ai_messages": "FOREIGN KEY (conversation_id) REFERENCES ai_conversations(conversation_id) ON DELETE CASCADE",
    "exam_attempts": "FOREIGN KEY (run_id) REFERENCES career_runs(run_id) ON DELETE CASCADE",
    "submission_answers": "FOREIGN KEY (submission_id) REFERENCES assessment_attempts(submission_id) ON DELETE CASCADE",
    "test_case_results": "FOREIGN KEY (submission_id) REFERENCES assessment_attempts(submission_id) ON DELETE CASCADE",
    "rubric_scores": "FOREIGN KEY (submission_id) REFERENCES assessment_attempts(submission_id) ON DELETE CASCADE",
    "ai_feedback_traces": "FOREIGN KEY (submission_id) REFERENCES assessment_attempts(submission_id) ON DELETE CASCADE",
    "final_assessments": "FOREIGN KEY (submission_id) REFERENCES assessment_attempts(submission_id) ON DELETE CASCADE",
    "jd_versions": "FOREIGN KEY (jd_id) REFERENCES job_descriptions(jd_id) ON DELETE CASCADE",
    "jd_requirements": "FOREIGN KEY (jd_id, jd_version) REFERENCES jd_versions(jd_id, jd_version) ON DELETE CASCADE",
    "knowledge_chunks": "FOREIGN KEY (document_id, version) REFERENCES knowledge_documents(document_id, version) ON DELETE CASCADE",
}

# Questions written by subject-matter experts (5.35). A contribution is a draft until a reviewer other than its
# author approves it; only then is it published, to exam_bank_items (exam) or the test question bank.
CONTRIB_SCHEMA_VERSION = 2
CONTRIB_SCHEMA = """
CREATE TABLE IF NOT EXISTS contributors (
    user_id TEXT PRIMARY KEY, email TEXT, full_name TEXT, granted_by TEXT NOT NULL, granted_at TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS question_contributions (
    contribution_id TEXT PRIMARY KEY, bank TEXT NOT NULL CHECK (bank IN ('EXAM', 'TEST')), author_id TEXT NOT NULL, author_name TEXT,
    skill_code TEXT NOT NULL, level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 3), status TEXT NOT NULL, payload TEXT NOT NULL,
    validation TEXT, fingerprint TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, review_note TEXT, reviewer_id TEXT,
    published_item_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, submitted_at TEXT, decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_contrib_status ON question_contributions(status, submitted_at);
CREATE INDEX IF NOT EXISTS idx_contrib_author ON question_contributions(author_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_contrib_fingerprint ON question_contributions(fingerprint);
CREATE TABLE IF NOT EXISTS contribution_events (
    event_id TEXT PRIMARY KEY, contribution_id TEXT NOT NULL REFERENCES question_contributions(contribution_id) ON DELETE CASCADE,
    actor_id TEXT, action TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contrib_events ON contribution_events(contribution_id, created_at);
-- Approved exam questions from contributions; the seed file data/exam_items_v5.json stays untouched.
CREATE TABLE IF NOT EXISTS exam_bank_items (
    item_id TEXT PRIMARY KEY, contribution_id TEXT REFERENCES question_contributions(contribution_id), skill_code TEXT NOT NULL,
    tier INTEGER NOT NULL, status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RETIRED')), author_id TEXT, payload TEXT NOT NULL,
    approved_by TEXT NOT NULL, approved_at TEXT NOT NULL, retired_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_exam_bank_cell ON exam_bank_items(skill_code, tier, status);
"""

# Shared state for running several server processes on one database (2026-11-15).
RUNTIME_SCHEMA_VERSION = 1
RUNTIME_SCHEMA = """
-- A counter per scope (a user id, 'content' or 'reviews'); a process reloads its copy when the counter moved.
CREATE TABLE IF NOT EXISTS sync_revisions (scope TEXT PRIMARY KEY, revision INTEGER NOT NULL);
-- One holder per learner at a time across every process, so two requests never overwrite each other's changes.
CREATE TABLE IF NOT EXISTS user_locks (user_id TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL);
-- Leases for background work (a grading job, the periodic tick) so one process does it, not every process.
CREATE TABLE IF NOT EXISTS work_leases (lease_key TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL);
"""


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class Database:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=15)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0
        # Server processes starting together take turns on the schema and the migrations.
        with exclusive(self.path):
            if self.path != ":memory:":
                self._connection.execute("PRAGMA journal_mode=WAL")
                self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.executescript(SCHEMA)
            self.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            self._migrate()
            self._migrate_ai()
            self._migrate_roadmap()
            self._migrate_runtime()
            self._migrate_foreign_keys()
            self._migrate_contributions()
        # Checked on every write from here on. A parent row deleted takes its child rows with it (ON DELETE CASCADE).
        self._connection.execute("PRAGMA foreign_keys = ON")

    def startup_lock(self):
        """The same cross-process lock, for seeding data right after the schema is ready."""
        return exclusive(self.path)

    def _migrate_contributions(self) -> None:
        """Add the question-contribution tables. Add-only, nothing existing changes."""
        version = int(self.get_meta("contrib_schema_version") or 0)
        if version >= CONTRIB_SCHEMA_VERSION:
            return
        self._connection.executescript(CONTRIB_SCHEMA)
        # Version 2 (5.36): what the reviewer confirmed when approving. A new nullable column only.
        columns = {row["name"] for row in self.query("PRAGMA table_info(question_contributions)")}
        if "review_checklist" not in columns:
            self._connection.execute("ALTER TABLE question_contributions ADD COLUMN review_checklist TEXT")
        self.set_meta("contrib_schema_version", str(CONTRIB_SCHEMA_VERSION))

    def _migrate_runtime(self) -> None:
        """Add the tables used to share state between server processes. Add-only, nothing existing changes."""
        if int(self.get_meta("runtime_schema_version") or 0) >= RUNTIME_SCHEMA_VERSION:
            return
        self._connection.executescript(RUNTIME_SCHEMA)
        self.set_meta("runtime_schema_version", str(RUNTIME_SCHEMA_VERSION))

    def foreign_key_orphans(self) -> dict[str, int]:
        """Child rows that would break each planned foreign key (all zero before the migration may run)."""
        found = {}
        for table, clause in FOREIGN_KEYS.items():
            columns = [part.strip() for part in clause.split("(", 1)[1].split(")", 1)[0].split(",")]
            parent, keys = clause.split("REFERENCES ", 1)[1].split("(", 1)
            keys = [part.strip() for part in keys.split(")", 1)[0].split(",")]
            match = " AND ".join(f"p.{key} = c.{column}" for column, key in zip(columns, keys))
            found[table] = self.one(f"SELECT COUNT(*) AS n FROM {table} c WHERE NOT EXISTS (SELECT 1 FROM {parent.strip()} p WHERE {match})")["n"]
        return found

    def _migrate_foreign_keys(self) -> None:
        """Rebuild the child tables with foreign keys (SQLite cannot add a constraint to an existing table).

        Safe by construction: the file is backed up first; the copy keeps every row and its rowid; nothing runs
        unless no row would break a key; ``PRAGMA foreign_key_check`` must come back empty or the whole change is
        rolled back. A second process starting at the same moment waits on the write lock and then skips.
        """
        if int(self.get_meta("fk_schema_version") or 0) >= FK_SCHEMA_VERSION:
            return
        orphans = {table: count for table, count in self.foreign_key_orphans().items() if count}
        if orphans:
            # Never delete data to make a key fit: keep running without the keys and say why.
            self.set_meta("fk_migration_blocked", json.dumps(orphans))
            return
        self._backup(f"pre-fk{FK_SCHEMA_VERSION}")
        self._connection.execute("PRAGMA foreign_keys = OFF")
        try:
            with self.transaction():
                if int(self.get_meta("fk_schema_version") or 0) >= FK_SCHEMA_VERSION:
                    return
                for table, clause in FOREIGN_KEYS.items():
                    self._rebuild_with_key(table, clause)
                problems = self.query("PRAGMA foreign_key_check")
                if problems:
                    raise sqlite3.IntegrityError(f"foreign_key_check failed: {problems[:3]}")
                self.set_meta("fk_schema_version", str(FK_SCHEMA_VERSION))
                self.execute("DELETE FROM meta WHERE key = 'fk_migration_blocked'")
        finally:
            self._connection.execute("PRAGMA foreign_keys = ON")

    def _rebuild_with_key(self, table: str, clause: str) -> None:
        create = self.one("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))["sql"]
        if "FOREIGN KEY" in create.upper():
            return
        indexes = [row["sql"] for row in self.query("SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL", (table,))]
        columns = [row["name"] for row in self.query(f"PRAGMA table_info({table})")]
        body = create[create.index("(") + 1: create.rindex(")")].rstrip()
        self.execute(f"CREATE TABLE {table}__fk ({body}, {clause})")
        listed = ", ".join(columns)
        self.execute(f"INSERT INTO {table}__fk(rowid, {listed}) SELECT rowid, {listed} FROM {table}")
        before = self.one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        after = self.one(f"SELECT COUNT(*) AS n FROM {table}__fk")["n"]
        if before != after:
            raise sqlite3.IntegrityError(f"{table}: copied {after} of {before} rows")
        self.execute(f"DROP TABLE {table}")
        self.execute(f"ALTER TABLE {table}__fk RENAME TO {table}")
        for sql in indexes:
            self.execute(sql)

    def _backup(self, label: str) -> None:
        if self.path == ":memory:":
            return
        target = sqlite3.connect(f"{self.path}.{label}.bak")
        with target:
            self._connection.backup(target)
        target.close()

    def _migrate_ai(self) -> None:
        """Add the AI platform's tables, backing up first. No existing table is touched."""
        if int(self.get_meta("ai_schema_version") or 0) >= AI_SCHEMA_VERSION:
            return
        self._backup(f"pre-ai{AI_SCHEMA_VERSION}")
        self._connection.executescript(AI_SCHEMA)
        self.set_meta("ai_schema_version", str(AI_SCHEMA_VERSION))

    def _migrate_roadmap(self) -> None:
        """Add the Learning Roadmap 2.0 tables, backing up first. No existing table is touched."""
        if int(self.get_meta("roadmap_schema_version") or 0) >= ROADMAP_SCHEMA_VERSION:
            return
        self._backup(f"pre-roadmap{ROADMAP_SCHEMA_VERSION}")
        self._connection.executescript(ROADMAP_SCHEMA)
        self.set_meta("roadmap_schema_version", str(ROADMAP_SCHEMA_VERSION))

    def _migrate(self) -> None:
        """Add-only upgrades, backing up the file first. Old columns and rows are never touched."""
        version = int(self.get_meta("schema_version") or 1)
        if version >= SCHEMA_VERSION:
            return
        self._backup(f"pre-v{SCHEMA_VERSION}")
        with self.transaction():
            for table in ARCHIVABLE_TABLES:
                columns = {row["name"] for row in self.query(f"PRAGMA table_info({table})")}
                if "archived_by_run" not in columns:
                    self.execute(f"ALTER TABLE {table} ADD COLUMN archived_by_run TEXT")
            self.set_meta("schema_version", str(SCHEMA_VERSION))

    @contextmanager
    def transaction(self) -> Iterator["Database"]:
        """All-or-nothing unit of work. Nested blocks join the outer transaction."""
        with self._lock:
            outermost = self._depth == 0
            if outermost:
                self._connection.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self
            except BaseException:
                self._depth -= 1
                if outermost:
                    self._connection.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outermost:
                    self._connection.execute("COMMIT")

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._connection.execute(sql, tuple(parameters))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._connection.executemany(sql, [tuple(row) for row in rows])

    def query(self, sql: str, parameters: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, tuple(parameters)).fetchall()]

    def one(self, sql: str, parameters: Iterable[Any] = ()) -> Optional[dict]:
        with self._lock:
            row = self._connection.execute(sql, tuple(parameters)).fetchone()
        return dict(row) if row else None

    def get_meta(self, key: str) -> Optional[str]:
        row = self.one("SELECT value FROM meta WHERE key = ?", (key,))
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def clear(self) -> None:
        """Empty every table (used by the in-memory test database only)."""
        # FTS5 keeps its index in shadow tables that only the virtual table itself may change.
        tables = [row["name"] for row in self.query("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'knowledge_chunks_fts_%' AND name != 'meta'")]
        with self.transaction():
            # Every table is emptied, so the keys are checked once at the end instead of after each table.
            self.execute("PRAGMA defer_foreign_keys = ON")
            for table in tables:
                self.execute(f"DELETE FROM {table}")
            self.execute("DELETE FROM meta WHERE key NOT IN ('schema_version', 'ai_schema_version', 'roadmap_schema_version', 'runtime_schema_version', 'fk_schema_version', 'contrib_schema_version')")

    def purge_user(self, user_id: str) -> int:
        """Right to erasure: remove every row owned by a learner, including learner-imported JDs."""
        removed = 0
        with self.transaction():
            for attempt in self.query("SELECT attempt_id FROM exam_attempts WHERE user_id = ? UNION SELECT attempt_id FROM final_attempts WHERE user_id = ?", (user_id, user_id)):
                for table in ("exam_responses", "exam_events"):
                    removed += self.execute(f"DELETE FROM {table} WHERE attempt_id = ?", (attempt["attempt_id"],)).rowcount
            removed += self.execute("DELETE FROM ai_messages WHERE conversation_id IN (SELECT conversation_id FROM ai_conversations WHERE user_id = ?)", (user_id,)).rowcount
            submissions = [row["submission_id"] for row in self.query("SELECT submission_id FROM assessment_attempts WHERE user_id = ?", (user_id,))]
            for submission_id in submissions:
                for table in SUBMISSION_TABLES:
                    removed += self.execute(f"DELETE FROM {table} WHERE submission_id = ?", (submission_id,)).rowcount
            for jd in self.query("SELECT jd_id FROM job_descriptions WHERE owner_user_id = ?", (user_id,)):
                for table in ("jd_requirements", "jd_versions", "job_descriptions"):
                    removed += self.execute(f"DELETE FROM {table} WHERE jd_id = ?", (jd["jd_id"],)).rowcount
            for table, column in USER_TABLES:
                removed += self.execute(f"DELETE FROM {table} WHERE {column} = ?", (user_id,)).rowcount
            # Questions: unpublished drafts go; a published question stays in the bank without the author's name.
            removed += self.execute("DELETE FROM question_contributions WHERE author_id = ? AND published_item_id IS NULL", (user_id,)).rowcount
            self.execute("UPDATE question_contributions SET author_name = NULL WHERE author_id = ?", (user_id,))
            removed += self.execute("DELETE FROM contributors WHERE user_id = ?", (user_id,)).rowcount
        return removed

    def close(self) -> None:
        with self._lock:
            self._connection.close()
