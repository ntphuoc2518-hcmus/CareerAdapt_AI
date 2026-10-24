BEGIN;

INSERT INTO career_versions (career_code, version_tag) VALUES ('DATA_ANALYST', 'test-v0');

INSERT INTO skill_requirements (career_version_id, skill_code, target_level, weight, is_core)
SELECT cv.career_version_id, s.code, s.lvl, s.w, s.core
FROM career_versions cv,
     (VALUES ('SQL', 2, 0.30, true),
             ('PYTHON', 1, 0.15, false),
             ('DATA_QUALITY', 2, 0.20, true),
             ('DATA_VIZ', 2, 0.20, false),
             ('WRITTEN_EXPLANATION', 2, 0.15, false)) AS s(code, lvl, w, core)
WHERE cv.version_tag = 'test-v0';

-- Test 1: wrong weights must block publishing
DO $$
BEGIN
    UPDATE skill_requirements SET weight = 0.5
    WHERE skill_code = 'PYTHON'
      AND career_version_id IN (SELECT career_version_id FROM career_versions WHERE version_tag = 'test-v0');
    UPDATE career_versions SET status = 'published' WHERE version_tag = 'test-v0';
    RAISE EXCEPTION 'TEST FAILED: publishing with wrong weights was allowed';
EXCEPTION WHEN raise_exception THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 1: publishing with wrong weights was blocked';
END $$;

-- Correct weights: publishing must work
UPDATE career_versions SET status = 'published' WHERE version_tag = 'test-v0';
SELECT version_tag, status, published_at IS NOT NULL AS has_published_date
FROM career_versions WHERE version_tag = 'test-v0';

-- Test 2: editing after publish must be blocked
DO $$
BEGIN
    UPDATE skill_requirements SET weight = 0.9
    WHERE skill_code = 'SQL'
      AND career_version_id IN (SELECT career_version_id FROM career_versions WHERE version_tag = 'test-v0');
    RAISE EXCEPTION 'TEST FAILED: editing a published version was allowed';
EXCEPTION WHEN raise_exception THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 2: editing a published version was blocked';
END $$;

ROLLBACK;