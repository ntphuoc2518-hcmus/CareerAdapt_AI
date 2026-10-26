BEGIN;

-- roadmap_versions: one personal study plan. A new plan = a new row (old ones are kept).
CREATE TABLE roadmap_versions (
    roadmap_version_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    career_version_id       UUID NOT NULL
                            REFERENCES career_versions (career_version_id) ON DELETE RESTRICT,
    based_on_assessment_ids UUID[] NOT NULL DEFAULT '{}',   -- results this plan is based on
    weekly_hours_budget     NUMERIC(5,1) NOT NULL
                            CHECK (weekly_hours_budget > 0 AND weekly_hours_budget <= 168),
    total_weeks             INTEGER NOT NULL CHECK (total_weeks BETWEEN 1 AND 104),
    status                  TEXT NOT NULL DEFAULT 'ACTIVE'
                            CHECK (status IN ('ACTIVE', 'SUPERSEDED', 'ARCHIVED')),
    unscheduled_activities  JSONB NOT NULL DEFAULT '[]'::jsonb,  -- activities left out + reason
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- each user can have only ONE active plan
CREATE UNIQUE INDEX roadmap_one_active_per_user
    ON roadmap_versions (user_id) WHERE status = 'ACTIVE';
CREATE INDEX roadmap_versions_user_idx ON roadmap_versions (user_id, created_at DESC);

-- Rule: a plan never changes; only its status moves forward.
CREATE FUNCTION guard_roadmap_versions() RETURNS trigger AS $$
BEGIN
    IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status') THEN
        RAISE EXCEPTION 'Content of a roadmap version cannot be changed';
    END IF;
    IF NEW.status <> OLD.status THEN
        IF NOT (
            (OLD.status = 'ACTIVE'     AND NEW.status IN ('SUPERSEDED', 'ARCHIVED')) OR
            (OLD.status = 'SUPERSEDED' AND NEW.status = 'ARCHIVED')
        ) THEN
            RAISE EXCEPTION 'Roadmap status change % -> % is not allowed', OLD.status, NEW.status;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_roadmap_versions_guard
BEFORE UPDATE ON roadmap_versions
FOR EACH ROW EXECUTE FUNCTION guard_roadmap_versions();

-- learning_activities: the activities placed into the weeks of one plan
CREATE TABLE learning_activities (
    learning_activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    roadmap_version_id   UUID NOT NULL
                         REFERENCES roadmap_versions (roadmap_version_id) ON DELETE CASCADE,
    catalog_activity_id  UUID NOT NULL
                         REFERENCES activity_catalog (activity_id) ON DELETE RESTRICT,
    title                TEXT NOT NULL,
    skill_code           TEXT NOT NULL,
    week_number          INTEGER NOT NULL CHECK (week_number >= 1),
    estimated_hours      NUMERIC(4,1) NOT NULL CHECK (estimated_hours > 0),
    required_output      TEXT NOT NULL,
    due_date             DATE,
    current_status       TEXT NOT NULL DEFAULT 'NOT_STARTED'
                         CHECK (current_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'OVERDUE')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (roadmap_version_id, catalog_activity_id)
);

CREATE INDEX learning_activities_roadmap_idx
    ON learning_activities (roadmap_version_id, week_number);

-- progress_records: history of status changes of an activity
CREATE TABLE progress_records (
    progress_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learning_activity_id    UUID NOT NULL
                            REFERENCES learning_activities (learning_activity_id) ON DELETE CASCADE,
    old_status              TEXT NOT NULL
                            CHECK (old_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'OVERDUE')),
    new_status              TEXT NOT NULL
                            CHECK (new_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'OVERDUE')),
    actual_duration_minutes INTEGER CHECK (actual_duration_minutes >= 0),
    output_note             TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (old_status <> new_status)
);

CREATE INDEX progress_records_activity_idx
    ON progress_records (learning_activity_id, created_at);

-- Rules for activities:
--  * only in an ACTIVE plan, inside the plan length, and never above the weekly hour budget
--  * content never changes, only the status (along allowed steps)
CREATE FUNCTION guard_learning_activities() RETURNS trigger AS $$
DECLARE
    v_status TEXT;
    v_budget NUMERIC;
    v_weeks  INTEGER;
    v_used   NUMERIC;
BEGIN
    SELECT status, weekly_hours_budget, total_weeks
      INTO v_status, v_budget, v_weeks
      FROM roadmap_versions
     WHERE roadmap_version_id = NEW.roadmap_version_id;

    IF TG_OP = 'INSERT' THEN
        IF v_status <> 'ACTIVE' THEN
            RAISE EXCEPTION 'Cannot add activities to a roadmap that is not ACTIVE';
        END IF;
        IF NEW.week_number > v_weeks THEN
            RAISE EXCEPTION 'Week % is beyond the roadmap length (% weeks)', NEW.week_number, v_weeks;
        END IF;
        SELECT COALESCE(SUM(estimated_hours), 0) INTO v_used
          FROM learning_activities
         WHERE roadmap_version_id = NEW.roadmap_version_id
           AND week_number = NEW.week_number;
        IF v_used + NEW.estimated_hours > v_budget THEN
            RAISE EXCEPTION 'Week % would have % hours, more than the budget of % hours',
                NEW.week_number, v_used + NEW.estimated_hours, v_budget;
        END IF;
        RETURN NEW;
    END IF;

    IF (to_jsonb(NEW) - 'current_status' - 'updated_at')
       IS DISTINCT FROM (to_jsonb(OLD) - 'current_status' - 'updated_at') THEN
        RAISE EXCEPTION 'Content of a roadmap activity cannot be changed';
    END IF;
    IF NEW.current_status <> OLD.current_status THEN
        IF v_status <> 'ACTIVE' THEN
            RAISE EXCEPTION 'Activities of an old roadmap cannot be updated';
        END IF;
        IF NOT (
            (OLD.current_status = 'NOT_STARTED' AND NEW.current_status IN ('IN_PROGRESS', 'COMPLETED', 'OVERDUE')) OR
            (OLD.current_status = 'IN_PROGRESS' AND NEW.current_status IN ('COMPLETED', 'OVERDUE')) OR
            (OLD.current_status = 'OVERDUE'     AND NEW.current_status IN ('IN_PROGRESS', 'COMPLETED')) OR
            (OLD.current_status = 'COMPLETED'   AND NEW.current_status = 'IN_PROGRESS')
        ) THEN
            RAISE EXCEPTION 'Activity status change % -> % is not allowed',
                OLD.current_status, NEW.current_status;
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_learning_activities_guard
BEFORE INSERT OR UPDATE ON learning_activities
FOR EACH ROW EXECUTE FUNCTION guard_learning_activities();

-- every status change is written to progress_records automatically
CREATE FUNCTION log_activity_status_change() RETURNS trigger AS $$
BEGIN
    INSERT INTO progress_records (learning_activity_id, old_status, new_status)
    VALUES (NEW.learning_activity_id, OLD.current_status, NEW.current_status);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_learning_activities_log
AFTER UPDATE ON learning_activities
FOR EACH ROW WHEN (OLD.current_status IS DISTINCT FROM NEW.current_status)
EXECUTE FUNCTION log_activity_status_change();

-- history rows: only duration and note can be added later, nothing else changes
CREATE FUNCTION guard_progress_records() RETURNS trigger AS $$
BEGIN
    IF (to_jsonb(NEW) - 'actual_duration_minutes' - 'output_note')
       IS DISTINCT FROM (to_jsonb(OLD) - 'actual_duration_minutes' - 'output_note') THEN
        RAISE EXCEPTION 'Progress history cannot be changed (only duration and note)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_progress_records_guard
BEFORE UPDATE ON progress_records
FOR EACH ROW EXECUTE FUNCTION guard_progress_records();

-- Shared rule: the user_id on a row must be the owner of the activity it points to
CREATE FUNCTION check_activity_owner() RETURNS trigger AS $$
DECLARE
    v_owner UUID;
BEGIN
    IF NEW.learning_activity_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT rv.user_id INTO v_owner
      FROM learning_activities la
      JOIN roadmap_versions rv ON rv.roadmap_version_id = la.roadmap_version_id
     WHERE la.learning_activity_id = NEW.learning_activity_id;
    IF v_owner IS DISTINCT FROM NEW.user_id THEN
        RAISE EXCEPTION 'user_id does not match the owner of the activity';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- checklist_items: daily to-do items (any number per activity)
CREATE TABLE checklist_items (
    checklist_item_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    learning_activity_id UUID NOT NULL
                         REFERENCES learning_activities (learning_activity_id) ON DELETE CASCADE,
    content              TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    due_date             DATE,
    sort_order           INTEGER NOT NULL DEFAULT 0,
    source               TEXT NOT NULL DEFAULT 'SYSTEM' CHECK (source IN ('SYSTEM', 'USER')),
    is_done              BOOLEAN NOT NULL DEFAULT FALSE,
    done_at              TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (is_done = (done_at IS NOT NULL))
);

CREATE INDEX checklist_items_user_due_idx ON checklist_items (user_id, due_date);
CREATE INDEX checklist_items_activity_idx ON checklist_items (learning_activity_id, sort_order);

CREATE FUNCTION set_checklist_done_at() RETURNS trigger AS $$
BEGIN
    IF NEW.is_done AND NEW.done_at IS NULL THEN
        NEW.done_at := now();
    ELSIF NOT NEW.is_done THEN
        NEW.done_at := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_checklist_done_at
BEFORE INSERT OR UPDATE ON checklist_items
FOR EACH ROW EXECUTE FUNCTION set_checklist_done_at();

CREATE TRIGGER trg_checklist_owner
BEFORE INSERT OR UPDATE OF user_id, learning_activity_id ON checklist_items
FOR EACH ROW EXECUTE FUNCTION check_activity_owner();

-- for the progress bar: how many items done out of how many
CREATE VIEW checklist_progress AS
SELECT learning_activity_id,
       user_id,
       count(*)                       AS total_items,
       count(*) FILTER (WHERE is_done) AS done_items
FROM checklist_items
GROUP BY learning_activity_id, user_id;

-- reminders: in-app reminders only; the same event never creates two rows
CREATE TABLE reminders (
    reminder_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    learning_activity_id UUID REFERENCES learning_activities (learning_activity_id) ON DELETE CASCADE,
    reminder_type        TEXT NOT NULL
                         CHECK (reminder_type IN ('UPCOMING_DUE', 'OVERDUE', 'SCHEDULE_MISMATCH')),
    message              TEXT,
    deduplication_key    TEXT NOT NULL,
    is_viewed            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, deduplication_key)
);

CREATE INDEX reminders_user_idx ON reminders (user_id, is_viewed, created_at DESC);

CREATE TRIGGER trg_reminders_owner
BEFORE INSERT OR UPDATE OF user_id, learning_activity_id ON reminders
FOR EACH ROW EXECUTE FUNCTION check_activity_owner();

-- audit_logs: security log (who tried to touch what). Never store submission text here.
CREATE TABLE audit_logs (
    audit_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES users (user_id) ON DELETE SET NULL,
    action        TEXT NOT NULL CHECK (length(btrim(action)) > 0),
    target_type   TEXT NOT NULL,
    target_id     TEXT,
    outcome       TEXT NOT NULL DEFAULT 'DENIED' CHECK (outcome IN ('ALLOWED', 'DENIED', 'ERROR')),
    client_ip     INET,
    details       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX audit_logs_created_idx ON audit_logs (created_at DESC);
CREATE INDEX audit_logs_actor_idx ON audit_logs (actor_user_id);

CREATE FUNCTION protect_audit_logs() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Audit log cannot be deleted';
    END IF;
    -- only actor_user_id may change (it becomes NULL when a user is deleted)
    IF (to_jsonb(NEW) - 'actor_user_id') IS DISTINCT FROM (to_jsonb(OLD) - 'actor_user_id') THEN
        RAISE EXCEPTION 'Audit log cannot be edited';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_logs_protect
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION protect_audit_logs();

COMMIT;