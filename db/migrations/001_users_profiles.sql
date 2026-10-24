BEGIN;

CREATE TABLE users (
    user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'learner'
                  CHECK (role IN ('learner', 'reviewer', 'admin')),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX users_email_lower_uq ON users (lower(email));

CREATE TABLE profiles (
    user_id                UUID PRIMARY KEY
                           REFERENCES users (user_id) ON DELETE CASCADE,
    display_name           TEXT,
    major                  TEXT,
    career_goal            TEXT NOT NULL DEFAULT 'DATA_ANALYST'
                           CHECK (career_goal = 'DATA_ANALYST'),
    weekly_available_hours NUMERIC(5,1)
                           CHECK (weekly_available_hours > 0 AND weekly_available_hours <= 168),
    target_deadline        DATE,
    self_reported_skills   JSONB NOT NULL DEFAULT '[]'::jsonb,
    reminder_preferences   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;