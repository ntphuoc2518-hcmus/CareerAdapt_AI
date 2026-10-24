BEGIN;

-- career_versions: a version of the career requirement set (e.g. Data Analyst v3.0)
CREATE TABLE career_versions (
    career_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    career_code       TEXT NOT NULL DEFAULT 'DATA_ANALYST',
    version_tag       TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft', 'published', 'deprecated')),
    source_references JSONB NOT NULL DEFAULT '[]'::jsonb,  -- O*NET, ESCO, notes
    published_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (career_code, version_tag)
);

-- job_postings: job ads collected by hand as reference sources (about 50 rows)
CREATE TABLE job_postings (
    job_posting_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    career_code    TEXT NOT NULL DEFAULT 'DATA_ANALYST',
    company_name   TEXT NOT NULL,
    job_title      TEXT NOT NULL,                 -- vi tri
    job_level      TEXT NOT NULL DEFAULT 'OTHER'  -- cap do
                   CHECK (job_level IN ('INTERN', 'FRESHER', 'JUNIOR', 'OTHER')),
    posting_url    TEXT NOT NULL UNIQUE,          -- link
    source_site    TEXT NOT NULL
                   CHECK (source_site IN ('TOPCV', 'ITVIEC', 'LINKEDIN', 'OTHER')),
    collected_on   DATE NOT NULL,                 -- ngay lay tin (ngay ban doc tin)
    salary_text    TEXT,                          -- luong, ghi dang chu, co the de trong
    jd_summary     TEXT,                          -- tom tat JD bang loi cua minh
    extracted_skills JSONB NOT NULL DEFAULT '[]'::jsonb, -- ky nang tin yeu cau
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- skill_requirements: target level, weight and core flag per skill and per version
CREATE TABLE skill_requirements (
    requirement_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    career_version_id UUID NOT NULL
                      REFERENCES career_versions (career_version_id) ON DELETE RESTRICT,
    skill_code        TEXT NOT NULL,
    target_level      SMALLINT NOT NULL CHECK (target_level BETWEEN 1 AND 3),
    weight            NUMERIC(4,3) NOT NULL CHECK (weight > 0 AND weight <= 1),
    is_core           BOOLEAN NOT NULL DEFAULT FALSE,
    rubric_definition JSONB NOT NULL DEFAULT '{}'::jsonb,  -- description of levels 0-3
    UNIQUE (career_version_id, skill_code)
);

-- Rule 1: a version can be published only if weights add up to exactly 1.0,
--         and a published version can never go back to draft.
CREATE FUNCTION check_publish_career_version() RETURNS trigger AS $$
DECLARE
    total NUMERIC;
    n     INTEGER;
BEGIN
    IF OLD.status IN ('published', 'deprecated') AND NEW.status = 'draft' THEN
        RAISE EXCEPTION 'A published version cannot go back to draft';
    END IF;
    IF NEW.status = 'published' AND OLD.status = 'draft' THEN
        SELECT COALESCE(SUM(weight), 0), COUNT(*) INTO total, n
        FROM skill_requirements
        WHERE career_version_id = NEW.career_version_id;
        IF n = 0 OR total <> 1 THEN
            RAISE EXCEPTION 'Cannot publish: weights sum to % (must be exactly 1.0)', total;
        END IF;
        NEW.published_at := COALESCE(NEW.published_at, now());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_career_versions_publish
BEFORE UPDATE OF status ON career_versions
FOR EACH ROW EXECUTE FUNCTION check_publish_career_version();

-- Rule 2: requirements of a published version are locked (no insert, update, delete).
CREATE FUNCTION lock_published_requirements() RETURNS trigger AS $$
DECLARE
    vid UUID;
    st  TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        vid := OLD.career_version_id;
    ELSE
        vid := NEW.career_version_id;
    END IF;
    SELECT status INTO st FROM career_versions WHERE career_version_id = vid;
    IF st IS NOT NULL AND st <> 'draft' THEN
        RAISE EXCEPTION 'Requirements of a published version cannot be changed';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_requirements_locked
BEFORE INSERT OR UPDATE OR DELETE ON skill_requirements
FOR EACH ROW EXECUTE FUNCTION lock_published_requirements();

COMMIT;