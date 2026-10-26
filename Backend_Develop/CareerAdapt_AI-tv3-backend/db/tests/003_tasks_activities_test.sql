BEGIN;

INSERT INTO career_versions (career_code, version_tag) VALUES ('DATA_ANALYST', 'test-v0');

INSERT INTO task_versions (career_version_id, task_code, variant_code, version_tag, title, duration_minutes, skill_codes)
SELECT career_version_id, 'DA01', 'A', 't1', 'Test task', 35, ARRAY['SQL', 'DATA_QUALITY']
FROM career_versions WHERE version_tag = 'test-v0';

-- Test 1: a task without rubric/dataset cannot be published
DO $$
BEGIN
    UPDATE task_versions SET status = 'published' WHERE version_tag = 't1';
    RAISE EXCEPTION 'TEST FAILED: publishing an incomplete task was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 1: publishing an incomplete task was blocked';
END $$;

-- Fill in the missing parts, then publish
UPDATE task_versions
SET input_dataset_ref = 'datasets/da01a.csv',
    reference_output_ref = 'datasets/da01a_ref.csv',
    rubric = '{"levels": "0-3"}',
    deterministic_rules = '{"check": "revenue"}'
WHERE version_tag = 't1';

UPDATE task_versions SET status = 'published', is_active = TRUE WHERE version_tag = 't1';

SELECT task_code, status, is_active, published_at IS NOT NULL AS has_published_date
FROM task_versions WHERE version_tag = 't1';

-- Test 2: editing a published task must be blocked
DO $$
BEGIN
    UPDATE task_versions SET title = 'Changed title' WHERE version_tag = 't1';
    RAISE EXCEPTION 'TEST FAILED: editing a published task was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 2: editing a published task was blocked';
END $$;

-- Activities: A2 needs A1, A3 needs A2
INSERT INTO activity_catalog (career_version_id, activity_code, title, skill_code, estimated_hours, required_output)
SELECT cv.career_version_id, a.code, 'Activity ' || a.code, 'SQL', 4, 'Output'
FROM career_versions cv, (VALUES ('A1'), ('A2'), ('A3')) AS a(code)
WHERE cv.version_tag = 'test-v0';

INSERT INTO activity_prerequisites (activity_id, prerequisite_activity_id)
SELECT x.activity_id, y.activity_id FROM activity_catalog x, activity_catalog y
WHERE x.activity_code = 'A2' AND y.activity_code = 'A1';

INSERT INTO activity_prerequisites (activity_id, prerequisite_activity_id)
SELECT x.activity_id, y.activity_id FROM activity_catalog x, activity_catalog y
WHERE x.activity_code = 'A3' AND y.activity_code = 'A2';

-- Test 3: A1 needs A3 would make a loop (A1 -> A3 -> A2 -> A1)
DO $$
BEGIN
    INSERT INTO activity_prerequisites (activity_id, prerequisite_activity_id)
    SELECT x.activity_id, y.activity_id FROM activity_catalog x, activity_catalog y
    WHERE x.activity_code = 'A1' AND y.activity_code = 'A3';
    RAISE EXCEPTION 'TEST FAILED: a prerequisite cycle was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 3: a prerequisite cycle was blocked';
END $$;

-- Test 4: an activity cannot need itself
DO $$
BEGIN
    INSERT INTO activity_prerequisites (activity_id, prerequisite_activity_id)
    SELECT activity_id, activity_id FROM activity_catalog WHERE activity_code = 'A1';
    RAISE EXCEPTION 'TEST FAILED: a self prerequisite was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 4: a self prerequisite was blocked';
END $$;

-- Test 5: a published activity cannot be edited
UPDATE activity_catalog SET status = 'published' WHERE activity_code = 'A1';

DO $$
BEGIN
    UPDATE activity_catalog SET title = 'Changed title' WHERE activity_code = 'A1';
    RAISE EXCEPTION 'TEST FAILED: editing a published activity was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 5: editing a published activity was blocked';
END $$;

-- Test 6 and 7: review history is append only
INSERT INTO content_reviews (content_type, content_id, decision, notes)
VALUES ('task_version', gen_random_uuid(), 'approved', 'ok');

DO $$
BEGIN
    UPDATE content_reviews SET notes = 'changed';
    RAISE EXCEPTION 'TEST FAILED: editing review history was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 6: editing review history was blocked';
END $$;

DO $$
BEGIN
    DELETE FROM content_reviews;
    RAISE EXCEPTION 'TEST FAILED: deleting review history was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 7: deleting review history was blocked';
END $$;

ROLLBACK;