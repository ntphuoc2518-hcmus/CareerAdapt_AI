BEGIN;

INSERT INTO users (email, password_hash)
VALUES ('u1@test.local', 'x'), ('u2@test.local', 'x');

INSERT INTO career_versions (career_code, version_tag) VALUES ('DATA_ANALYST', 'test-v0');

INSERT INTO task_versions (career_version_id, task_code, variant_code, version_tag, title, duration_minutes, skill_codes)
SELECT career_version_id, 'DA01', 'A', 'tst', 'Test task', 35, ARRAY['SQL']
FROM career_versions WHERE version_tag = 'test-v0';

INSERT INTO submissions (user_id, task_version_id, mode, submitted_text, idempotency_key)
SELECT u.user_id, t.task_version_id, 'ASSESSMENT', 'SELECT 1;', 'key-1'
FROM users u, task_versions t
WHERE u.email = 'u1@test.local' AND t.version_tag = 'tst';

-- Test 1: same user, same key = blocked
DO $$
BEGIN
    INSERT INTO submissions (user_id, task_version_id, mode, submitted_text, idempotency_key)
    SELECT u.user_id, t.task_version_id, 'ASSESSMENT', 'SELECT 1;', 'key-1'
    FROM users u, task_versions t
    WHERE u.email = 'u1@test.local' AND t.version_tag = 'tst';
    RAISE EXCEPTION 'TEST FAILED: duplicate submission was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 1: duplicate submission was blocked';
END $$;

-- Test 2: another user can use the same key
INSERT INTO submissions (user_id, task_version_id, mode, submitted_text, idempotency_key)
SELECT u.user_id, t.task_version_id, 'PRACTICE', 'SELECT 2;', 'key-1'
FROM users u, task_versions t
WHERE u.email = 'u2@test.local' AND t.version_tag = 'tst';
DO $$ BEGIN RAISE NOTICE 'OK 2: another user can use the same key'; END $$;

-- Test 3: a wrong status jump is blocked
DO $$
BEGIN
    UPDATE submissions SET processing_status = 'COMPLETED'
    WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
    RAISE EXCEPTION 'TEST FAILED: wrong status jump was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 3: wrong status jump was blocked';
END $$;

-- Test 4: correct chain, including a retry
UPDATE submissions SET processing_status = 'PROCESSING'
 WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
UPDATE submissions SET processing_status = 'PENDING_RETRY'
 WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
UPDATE submissions SET processing_status = 'PROCESSING'
 WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
UPDATE submissions SET processing_status = 'COMPLETED'
 WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
SELECT processing_status AS status_after_chain FROM submissions
 WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');

-- Test 5: submitted content cannot be edited
DO $$
BEGIN
    UPDATE submissions SET submitted_text = 'changed'
    WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
    RAISE EXCEPTION 'TEST FAILED: editing a submission was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 5: editing a submission was blocked';
END $$;

-- Assessment for user 1
INSERT INTO assessments (submission_id, overall_status)
SELECT submission_id, 'COMPLETED' FROM submissions
WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');

-- Test 6: a second assessment for the same submission is blocked
DO $$
BEGIN
    INSERT INTO assessments (submission_id, overall_status)
    SELECT submission_id, 'COMPLETED' FROM submissions
    WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
    RAISE EXCEPTION 'TEST FAILED: second assessment was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 6: second assessment was blocked';
END $$;

-- Test 7: level without a quote is blocked
DO $$
BEGIN
    INSERT INTO criterion_scores (assessment_id, criterion_id, skill_code, score_level, evidence_quote, is_verified)
    SELECT assessment_id, 'C1', 'SQL', 2, NULL, TRUE FROM assessments;
    RAISE EXCEPTION 'TEST FAILED: level without quote was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 7: level without quote was blocked';
END $$;

-- Test 8: level 2 with an unverified quote is blocked
DO $$
BEGIN
    INSERT INTO criterion_scores (assessment_id, criterion_id, skill_code, score_level, evidence_quote, is_verified)
    SELECT assessment_id, 'C1', 'SQL', 2, 'SELECT 1', FALSE FROM assessments;
    RAISE EXCEPTION 'TEST FAILED: level 2 with unverified quote was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 8: level 2 with unverified quote was blocked';
END $$;

-- Test 9: a quote of 26 words is blocked
DO $$
BEGIN
    INSERT INTO criterion_scores (assessment_id, criterion_id, skill_code, score_level, evidence_quote, is_verified)
    SELECT assessment_id, 'C1', 'SQL', 1, repeat('word ', 26), TRUE FROM assessments;
    RAISE EXCEPTION 'TEST FAILED: 26-word quote was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 9: 26-word quote was blocked';
END $$;

-- Valid rows: verified level 2, unverified level 1, inconclusive (no level)
INSERT INTO criterion_scores (assessment_id, criterion_id, skill_code, score_level, evidence_quote, is_verified)
SELECT assessment_id, 'C1', 'SQL', 2, 'SELECT 1', TRUE FROM assessments;
INSERT INTO criterion_scores (assessment_id, criterion_id, skill_code, score_level, evidence_quote, is_verified)
SELECT assessment_id, 'C2', 'SQL', 1, 'SELECT 1', FALSE FROM assessments;
INSERT INTO criterion_scores (assessment_id, criterion_id, skill_code)
SELECT assessment_id, 'C3', 'DATA_QUALITY' FROM assessments;
DO $$ BEGIN RAISE NOTICE 'OK 10: valid scores were accepted'; END $$;

-- Test 11: a file with a bad type is blocked
DO $$
BEGIN
    INSERT INTO submission_files (submission_id, stored_path, original_name, file_type, size_bytes, sha256)
    SELECT submission_id, 'store/aaa.exe', 'run.exe', 'EXE', 100, repeat('a', 64)
    FROM submissions WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
    RAISE EXCEPTION 'TEST FAILED: bad file type was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 11: bad file type was blocked';
END $$;

-- Test 12: a short checksum is blocked
DO $$
BEGIN
    INSERT INTO submission_files (submission_id, stored_path, original_name, file_type, size_bytes, sha256)
    SELECT submission_id, 'store/bbb.csv', 'data.csv', 'CSV', 100, 'abc'
    FROM submissions WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
    RAISE EXCEPTION 'TEST FAILED: short checksum was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 12: short checksum was blocked';
END $$;

-- A valid file: expiry should be 90 days after upload
INSERT INTO submission_files (submission_id, stored_path, original_name, file_type, size_bytes, sha256)
SELECT submission_id, 'store/ccc.csv', 'data.csv', 'CSV', 100, repeat('a', 64)
FROM submissions WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
SELECT (expires_at::date - uploaded_at::date) AS days_until_expiry FROM submission_files;

-- Test 13: AI run attempt numbers cannot repeat
INSERT INTO ai_runs (submission_id, attempt_no, status)
SELECT submission_id, 1, 'TIMEOUT' FROM submissions
WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
DO $$
BEGIN
    INSERT INTO ai_runs (submission_id, attempt_no, status)
    SELECT submission_id, 1, 'SUCCESS' FROM submissions
    WHERE user_id = (SELECT user_id FROM users WHERE email = 'u1@test.local');
    RAISE EXCEPTION 'TEST FAILED: repeated attempt number was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 13: repeated attempt number was blocked';
END $$;

-- Test 14: deleting user 1 removes only user 1's data
DELETE FROM users WHERE email = 'u1@test.local';
SELECT
    (SELECT count(*) FROM submissions)       AS submissions_left,
    (SELECT count(*) FROM assessments)       AS assessments_left,
    (SELECT count(*) FROM criterion_scores)  AS scores_left,
    (SELECT count(*) FROM submission_files)  AS files_left,
    (SELECT count(*) FROM ai_runs)           AS ai_runs_left;

ROLLBACK;