BEGIN;

-- task_versions: practice tasks DA01-DA03 (variant A/B), versioned
CREATE TABLE task_versions (
    task_version_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    career_version_id    UUID NOT NULL
                         REFERENCES career_versions (career_version_id) ON DELETE RESTRICT,
    task_code            TEXT NOT NULL CHECK (task_code IN ('DA01', 'DA02', 'DA03')),
    variant_code         TEXT NOT NULL DEFAULT 'A' CHECK (variant_code IN ('A', 'B')),
    version_tag          TEXT NOT NULL,
    title                TEXT NOT NULL,
    duration_minutes     INTEGER NOT NULL CHECK (duration_minutes > 0),
    skill_codes          TEXT[] NOT NULL CHECK (cardinality(skill_codes) > 0),
    input_dataset_ref    TEXT,                      -- path or hash of the fake input data
    reference_output_ref TEXT,                      -- path or hash of the reference answer
    deterministic_rules  JSONB NOT NULL DEFAULT '{}'::jsonb,  -- automatic checks
    rubric               JSONB NOT NULL DEFAULT '{}'::jsonb,  -- levels 0-3 per criterion
    status               TEXT NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft', 'published', 'deprecated')),
    is_active            BOOLEAN NOT NULL DEFAULT FALSE,      -- allowed to be taken
    published_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (task_code, variant_code, version_tag),
    CHECK (NOT is_active OR status = 'published')
);

CREATE FUNCTION guard_task_versions() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN
            RAISE EXCEPTION 'A published task version cannot be deleted';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status = 'draft' THEN
        IF NEW.status = 'published' THEN
            IF NEW.input_dataset_ref IS NULL OR NEW.reference_output_ref IS NULL
               OR NEW.rubric = '{}'::jsonb OR NEW.deterministic_rules = '{}'::jsonb THEN
                RAISE EXCEPTION 'Cannot publish: need dataset, reference output, rubric and deterministic rules';
            END IF;
            NEW.published_at := COALESCE(NEW.published_at, now());
        END IF;
    ELSE
        IF NEW.status = 'draft' THEN
            RAISE EXCEPTION 'A published task version cannot go back to draft';
        END IF;
        IF (to_jsonb(NEW) - 'status' - 'is_active' - 'published_at')
           IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'is_active' - 'published_at') THEN
            RAISE EXCEPTION 'Content of a published task version cannot be changed';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_task_versions_guard
BEFORE UPDATE OR DELETE ON task_versions
FOR EACH ROW EXECUTE FUNCTION guard_task_versions();

-- Generic rule for published rows: only status (and approved_by) may change.
CREATE FUNCTION lock_published_row() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN
            RAISE EXCEPTION 'A published row cannot be deleted';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status <> 'draft' THEN
        IF NEW.status = 'draft' THEN
            RAISE EXCEPTION 'A published row cannot go back to draft';
        END IF;
        IF (to_jsonb(NEW) - 'status' - 'approved_by')
           IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'approved_by') THEN
            RAISE EXCEPTION 'Content of a published row cannot be changed';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- activity_catalog: approved learning activities the scheduler can pick from
CREATE TABLE activity_catalog (
    activity_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    career_version_id UUID NOT NULL
                      REFERENCES career_versions (career_version_id) ON DELETE RESTRICT,
    activity_code     TEXT NOT NULL,
    title             TEXT NOT NULL,
    skill_code        TEXT NOT NULL,
    estimated_hours   NUMERIC(4,1) NOT NULL CHECK (estimated_hours > 0),
    required_output   TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft', 'published', 'deprecated')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (career_version_id, activity_code)
);

CREATE TRIGGER trg_activity_catalog_lock
BEFORE UPDATE OR DELETE ON activity_catalog
FOR EACH ROW EXECUTE FUNCTION lock_published_row();

-- activity_prerequisites: "activity_id needs prerequisite_activity_id first"
CREATE TABLE activity_prerequisites (
    activity_id              UUID NOT NULL
                             REFERENCES activity_catalog (activity_id) ON DELETE CASCADE,
    prerequisite_activity_id UUID NOT NULL
                             REFERENCES activity_catalog (activity_id) ON DELETE CASCADE,
    PRIMARY KEY (activity_id, prerequisite_activity_id),
    CHECK (activity_id <> prerequisite_activity_id)
);

CREATE FUNCTION guard_activity_prerequisites() RETURNS trigger AS $$
DECLARE
    aid UUID;
    st  TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        aid := OLD.activity_id;
    ELSE
        aid := NEW.activity_id;
    END IF;
    SELECT status INTO st FROM activity_catalog WHERE activity_id = aid;
    IF st IS NOT NULL AND st <> 'draft' THEN
        RAISE EXCEPTION 'Prerequisites of a published activity cannot be changed';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    -- cycle check: follow the prerequisites of the new prerequisite;
    -- if we come back to this activity, the new link would create a loop
    IF EXISTS (
        WITH RECURSIVE reach(id) AS (
            SELECT NEW.prerequisite_activity_id
            UNION
            SELECT ap.prerequisite_activity_id
            FROM activity_prerequisites ap
            JOIN reach r ON ap.activity_id = r.id
        )
        SELECT 1 FROM reach WHERE id = NEW.activity_id
    ) THEN
        RAISE EXCEPTION 'Prerequisite cycle detected: this link would create a loop';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_activity_prerequisites_guard
BEFORE INSERT OR UPDATE OR DELETE ON activity_prerequisites
FOR EACH ROW EXECUTE FUNCTION guard_activity_prerequisites();

-- learning_resources: third-party courses/links, approved by a reviewer
CREATE TABLE learning_resources (
    resource_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    provider        TEXT NOT NULL,
    resource_url    TEXT NOT NULL UNIQUE,
    skill_code      TEXT NOT NULL,
    estimated_hours NUMERIC(5,1) CHECK (estimated_hours > 0),
    approved_by     UUID REFERENCES users (user_id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'published', 'deprecated')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_learning_resources_lock
BEFORE UPDATE OR DELETE ON learning_resources
FOR EACH ROW EXECUTE FUNCTION lock_published_row();

-- activity_resources: which courses/links go with which activity
CREATE TABLE activity_resources (
    activity_id UUID NOT NULL
                REFERENCES activity_catalog (activity_id) ON DELETE CASCADE,
    resource_id UUID NOT NULL
                REFERENCES learning_resources (resource_id) ON DELETE CASCADE,
    PRIMARY KEY (activity_id, resource_id)
);

-- content_reviews: history of review decisions (append only)
CREATE TABLE content_reviews (
    review_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_type TEXT NOT NULL
                 CHECK (content_type IN ('career_version', 'task_version', 'activity', 'resource')),
    content_id   UUID NOT NULL,
    reviewer_id  UUID REFERENCES users (user_id) ON DELETE SET NULL,
    decision     TEXT NOT NULL
                 CHECK (decision IN ('submitted', 'approved', 'rejected', 'published')),
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX content_reviews_content_idx ON content_reviews (content_type, content_id);

CREATE FUNCTION protect_content_reviews() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Review history cannot be deleted';
    END IF;
    -- only reviewer_id may change (it is set to NULL when a user is deleted)
    IF (to_jsonb(NEW) - 'reviewer_id') IS DISTINCT FROM (to_jsonb(OLD) - 'reviewer_id') THEN
        RAISE EXCEPTION 'Review history cannot be edited';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_content_reviews_protect
BEFORE UPDATE OR DELETE ON content_reviews
FOR EACH ROW EXECUTE FUNCTION protect_content_reviews();

COMMIT;