BEGIN;

-- submissions: what the learner handed in (the original is kept as it was)
CREATE TABLE submissions (
    submission_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    task_version_id   UUID NOT NULL REFERENCES task_versions (task_version_id) ON DELETE RESTRICT,
    mode              TEXT NOT NULL CHECK (mode IN ('PRACTICE', 'ASSESSMENT')),
    submitted_text    TEXT,
    declared_tools    JSONB NOT NULL DEFAULT '[]'::jsonb,   -- tools the learner says they used
    idempotency_key   TEXT NOT NULL,                        -- stops double submit
    processing_status TEXT NOT NULL DEFAULT 'SUBMITTED'
                      CHECK (processing_status IN
                        ('SUBMITTED', 'PROCESSING', 'PENDING_RETRY', 'NEEDS_REVIEW', 'COMPLETED')),
    retry_count       INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    submitted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key)
);

CREATE INDEX submissions_user_idx ON submissions (user_id, submitted_at DESC);

-- Rule: content never changes after submitting; status may only follow allowed steps.
CREATE FUNCTION guard_submissions() RETURNS trigger AS $$
BEGIN
    IF (to_jsonb(NEW) - 'processing_status' - 'retry_count' - 'updated_at')
       IS DISTINCT FROM (to_jsonb(OLD) - 'processing_status' - 'retry_count' - 'updated_at') THEN
        RAISE EXCEPTION 'Content of a submission cannot be changed';
    END IF;
    IF NEW.processing_status <> OLD.processing_status THEN
        IF NOT (
            (OLD.processing_status = 'SUBMITTED'     AND NEW.processing_status = 'PROCESSING') OR
            (OLD.processing_status = 'PROCESSING'    AND NEW.processing_status IN ('PENDING_RETRY', 'NEEDS_REVIEW', 'COMPLETED')) OR
            (OLD.processing_status = 'PENDING_RETRY' AND NEW.processing_status IN ('PROCESSING', 'NEEDS_REVIEW')) OR
            (OLD.processing_status = 'NEEDS_REVIEW'  AND NEW.processing_status = 'COMPLETED')
        ) THEN
            RAISE EXCEPTION 'Status change % -> % is not allowed',
                OLD.processing_status, NEW.processing_status;
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_submissions_guard
BEFORE UPDATE ON submissions
FOR EACH ROW EXECUTE FUNCTION guard_submissions();

-- submission_files: info about uploaded files (the file itself is kept outside the database)
CREATE TABLE submission_files (
    file_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL REFERENCES submissions (submission_id) ON DELETE CASCADE,
    stored_path   TEXT NOT NULL UNIQUE,      -- random name, outside the public web folder
    original_name TEXT NOT NULL,
    file_type     TEXT NOT NULL CHECK (file_type IN ('TXT', 'CSV', 'SQL')),
    mime_type     TEXT,
    size_bytes    BIGINT NOT NULL CHECK (size_bytes > 0),
    sha256        TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '90 days'),
    deleted_at    TIMESTAMPTZ,
    UNIQUE (submission_id, sha256),
    CHECK (expires_at > uploaded_at)
);

CREATE INDEX submission_files_expiry_idx ON submission_files (expires_at)
    WHERE deleted_at IS NULL;

-- assessments: one result per submission (a second one is blocked)
CREATE TABLE assessments (
    assessment_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id         UUID NOT NULL UNIQUE
                          REFERENCES submissions (submission_id) ON DELETE CASCADE,
    deterministic_results JSONB NOT NULL DEFAULT '{}'::jsonb,  -- automatic checks by code
    overall_status        TEXT NOT NULL
                          CHECK (overall_status IN ('COMPLETED', 'NEEDS_REVIEW', 'INCONCLUSIVE')),
    flags                 JSONB NOT NULL DEFAULT '{}'::jsonb,  -- e.g. evidence_fabricated
    evaluated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- criterion_scores: one row per rubric criterion, with evidence
-- score_level NULL means "inconclusive" (never 0 by default)
CREATE TABLE criterion_scores (
    score_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id  UUID NOT NULL REFERENCES assessments (assessment_id) ON DELETE CASCADE,
    criterion_id   TEXT NOT NULL,
    skill_code     TEXT NOT NULL,
    score_level    SMALLINT CHECK (score_level BETWEEN 0 AND 3),
    evidence_quote TEXT,
    rationale      TEXT,
    is_verified    BOOLEAN NOT NULL DEFAULT FALSE,  -- quote really appears in the submission
    flags          JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (assessment_id, criterion_id),
    -- a level needs a quote
    CHECK (score_level IS NULL OR COALESCE(length(btrim(evidence_quote)), 0) > 0),
    -- a quote that was not verified can give at most level 1
    CHECK (is_verified OR score_level IS NULL OR score_level <= 1),
    -- a quote is at most 25 words
    CHECK (evidence_quote IS NULL
           OR cardinality(regexp_split_to_array(btrim(evidence_quote), '\s+')) <= 25)
);

-- ai_runs: one row per call to the AI service (also retries). No submission text is stored here.
CREATE TABLE ai_runs (
    run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id  UUID NOT NULL REFERENCES submissions (submission_id) ON DELETE CASCADE,
    attempt_no     INTEGER NOT NULL CHECK (attempt_no >= 1),
    provider       TEXT,
    model_name     TEXT,
    prompt_version TEXT,
    status         TEXT NOT NULL
                   CHECK (status IN ('SUCCESS', 'TIMEOUT', 'ERROR', 'INVALID_OUTPUT')),
    latency_ms     INTEGER CHECK (latency_ms >= 0),
    error_code     TEXT,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    UNIQUE (submission_id, attempt_no)
);

COMMIT;