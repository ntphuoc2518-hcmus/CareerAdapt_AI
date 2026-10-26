BEGIN;

-- helper functions that live only during this test
CREATE FUNCTION pg_temp.uid(p_email TEXT) RETURNS UUID AS $$
    SELECT user_id FROM users WHERE email = p_email
$$ LANGUAGE sql;

CREATE FUNCTION pg_temp.act(p_title TEXT) RETURNS UUID AS $$
    SELECT learning_activity_id FROM learning_activities WHERE title = p_title LIMIT 1
$$ LANGUAGE sql;

CREATE FUNCTION pg_temp.add_act(p_rv UUID, p_code TEXT, p_week INT, p_hours NUMERIC)
RETURNS void AS $$
    INSERT INTO learning_activities
        (roadmap_version_id, catalog_activity_id, title, skill_code, week_number, estimated_hours, required_output)
    SELECT p_rv, c.activity_id, c.title, c.skill_code, p_week, p_hours, c.required_output
    FROM activity_catalog c WHERE c.activity_code = p_code
$$ LANGUAGE sql;

-- setup
INSERT INTO users (email, password_hash)
VALUES ('u1@test.local', 'x'), ('u2@test.local', 'x');

INSERT INTO career_versions (career_code, version_tag) VALUES ('DATA_ANALYST', 'test-v0');

INSERT INTO activity_catalog (career_version_id, activity_code, title, skill_code, estimated_hours, required_output)
SELECT cv.career_version_id, a.code, a.code, 'SQL', 1, 'Output'
FROM career_versions cv, (VALUES ('T-A1'), ('T-A2'), ('T-A3'), ('T-A4')) AS a(code)
WHERE cv.version_tag = 'test-v0';

-- first roadmap for user 1: 4 hours per week, 8 weeks
INSERT INTO roadmap_versions (user_id, career_version_id, weekly_hours_budget, total_weeks)
SELECT pg_temp.uid('u1@test.local'), career_version_id, 4, 8
FROM career_versions WHERE version_tag = 'test-v0';

-- Test 1: a second ACTIVE roadmap for the same user is blocked
DO $$
BEGIN
    INSERT INTO roadmap_versions (user_id, career_version_id, weekly_hours_budget, total_weeks)
    SELECT pg_temp.uid('u1@test.local'), career_version_id, 4, 8
    FROM career_versions WHERE version_tag = 'test-v0';
    RAISE EXCEPTION 'TEST FAILED: second active roadmap was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 1: second active roadmap was blocked';
END $$;

-- week 1: 3 + 1 = 4 hours (exactly the budget)
SELECT pg_temp.add_act((SELECT roadmap_version_id FROM roadmap_versions
                        WHERE user_id = pg_temp.uid('u1@test.local')), 'T-A1', 1, 3);
SELECT pg_temp.add_act((SELECT roadmap_version_id FROM roadmap_versions
                        WHERE user_id = pg_temp.uid('u1@test.local')), 'T-A2', 1, 1);

-- Test 2: one more hour in week 1 goes over the budget
DO $$
BEGIN
    PERFORM pg_temp.add_act((SELECT roadmap_version_id FROM roadmap_versions
                             WHERE user_id = pg_temp.uid('u1@test.local')), 'T-A3', 1, 1);
    RAISE EXCEPTION 'TEST FAILED: week over budget was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 2: week over budget was blocked';
END $$;

-- Test 3: week 9 is beyond the 8 weeks of the roadmap
DO $$
BEGIN
    PERFORM pg_temp.add_act((SELECT roadmap_version_id FROM roadmap_versions
                             WHERE user_id = pg_temp.uid('u1@test.local')), 'T-A3', 9, 1);
    RAISE EXCEPTION 'TEST FAILED: week beyond roadmap length was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 3: week beyond roadmap length was blocked';
END $$;

-- a valid one in week 2
SELECT pg_temp.add_act((SELECT roadmap_version_id FROM roadmap_versions
                        WHERE user_id = pg_temp.uid('u1@test.local')), 'T-A3', 2, 2);

-- expected: week 1 = 4.0 hours, week 2 = 2.0 hours
SELECT week_number, SUM(estimated_hours) AS hours
FROM learning_activities WHERE title LIKE 'T-A%'
GROUP BY week_number ORDER BY week_number;

-- Test 4: the content of an activity cannot be edited
DO $$
BEGIN
    UPDATE learning_activities SET title = 'changed' WHERE title = 'T-A1';
    RAISE EXCEPTION 'TEST FAILED: editing an activity was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 4: editing an activity was blocked';
END $$;

-- status chain for T-A1: NOT_STARTED -> IN_PROGRESS -> COMPLETED
UPDATE learning_activities SET current_status = 'IN_PROGRESS' WHERE title = 'T-A1';
UPDATE learning_activities SET current_status = 'COMPLETED' WHERE title = 'T-A1';

-- Test 5: COMPLETED -> NOT_STARTED is not allowed
DO $$
BEGIN
    UPDATE learning_activities SET current_status = 'NOT_STARTED' WHERE title = 'T-A1';
    RAISE EXCEPTION 'TEST FAILED: wrong status step was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 5: wrong status step was blocked';
END $$;

-- expected: 2 history rows were written automatically
SELECT count(*) AS progress_rows FROM progress_records
WHERE learning_activity_id = pg_temp.act('T-A1');

-- Test 6: history cannot be edited
DO $$
BEGIN
    UPDATE progress_records SET new_status = 'NOT_STARTED'
    WHERE learning_activity_id = pg_temp.act('T-A1');
    RAISE EXCEPTION 'TEST FAILED: editing history was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 6: editing history was blocked';
END $$;

-- Test 7: duration and note can be added
UPDATE progress_records SET actual_duration_minutes = 30, output_note = 'T-note'
WHERE learning_activity_id = pg_temp.act('T-A1');
DO $$ BEGIN RAISE NOTICE 'OK 7: duration and note were added'; END $$;

-- checklist: 3 items, 2 ticked
INSERT INTO checklist_items (user_id, learning_activity_id, content, is_done)
VALUES (pg_temp.uid('u1@test.local'), pg_temp.act('T-A1'), 'T-item 1', TRUE),
       (pg_temp.uid('u1@test.local'), pg_temp.act('T-A1'), 'T-item 2', TRUE),
       (pg_temp.uid('u1@test.local'), pg_temp.act('T-A1'), 'T-item 3', FALSE);

-- expected: done_with_date = 2 (the date was filled automatically)
SELECT count(*) AS done_with_date FROM checklist_items
WHERE content LIKE 'T-item%' AND is_done AND done_at IS NOT NULL;

-- expected: total_items = 3, done_items = 2
SELECT total_items, done_items FROM checklist_progress
WHERE learning_activity_id = pg_temp.act('T-A1');

-- untick one item: its date must disappear (expected: items_with_date = 1)
UPDATE checklist_items SET is_done = FALSE WHERE content = 'T-item 1';
SELECT count(*) AS items_with_date FROM checklist_items
WHERE content LIKE 'T-item%' AND done_at IS NOT NULL;

-- Test 8: user 2 cannot add a checklist item to user 1's activity
DO $$
BEGIN
    INSERT INTO checklist_items (user_id, learning_activity_id, content)
    VALUES (pg_temp.uid('u2@test.local'), pg_temp.act('T-A1'), 'T-item x');
    RAISE EXCEPTION 'TEST FAILED: checklist of another user was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 8: checklist of another user was blocked';
END $$;

-- reminders
INSERT INTO reminders (user_id, learning_activity_id, reminder_type, deduplication_key)
VALUES (pg_temp.uid('u1@test.local'), pg_temp.act('T-A1'), 'OVERDUE', 'k1');

-- Test 9: the same event cannot create a second reminder
DO $$
BEGIN
    INSERT INTO reminders (user_id, learning_activity_id, reminder_type, deduplication_key)
    VALUES (pg_temp.uid('u1@test.local'), pg_temp.act('T-A1'), 'OVERDUE', 'k1');
    RAISE EXCEPTION 'TEST FAILED: duplicate reminder was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 9: duplicate reminder was blocked';
END $$;

-- Test 10: another user may use the same key
INSERT INTO reminders (user_id, reminder_type, deduplication_key)
VALUES (pg_temp.uid('u2@test.local'), 'SCHEDULE_MISMATCH', 'k1');
DO $$ BEGIN RAISE NOTICE 'OK 10: same key for another user was accepted'; END $$;

-- Test 11: a reminder for someone else's activity is blocked
DO $$
BEGIN
    INSERT INTO reminders (user_id, learning_activity_id, reminder_type, deduplication_key)
    VALUES (pg_temp.uid('u2@test.local'), pg_temp.act('T-A1'), 'OVERDUE', 'k2');
    RAISE EXCEPTION 'TEST FAILED: reminder for another user activity was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 11: reminder for another user activity was blocked';
END $$;

-- change of plan: old roadmap becomes SUPERSEDED, a new ACTIVE one is created
CREATE TEMP TABLE old_rv AS
SELECT roadmap_version_id FROM roadmap_versions
WHERE user_id = pg_temp.uid('u1@test.local');

UPDATE roadmap_versions SET status = 'SUPERSEDED'
WHERE roadmap_version_id IN (SELECT roadmap_version_id FROM old_rv);

INSERT INTO roadmap_versions (user_id, career_version_id, weekly_hours_budget, total_weeks)
SELECT pg_temp.uid('u1@test.local'), career_version_id, 6, 6
FROM career_versions WHERE version_tag = 'test-v0';

-- expected: ACTIVE = 1, SUPERSEDED = 1
SELECT status, count(*) FROM roadmap_versions
WHERE user_id = pg_temp.uid('u1@test.local') GROUP BY status ORDER BY status;

-- Test 12: an activity of the old roadmap cannot change status any more
DO $$
BEGIN
    UPDATE learning_activities SET current_status = 'IN_PROGRESS' WHERE title = 'T-A2';
    RAISE EXCEPTION 'TEST FAILED: updating an old roadmap activity was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 12: updating an old roadmap activity was blocked';
END $$;

-- Test 13: no new activity can be added to the old roadmap
DO $$
BEGIN
    PERFORM pg_temp.add_act((SELECT roadmap_version_id FROM old_rv), 'T-A4', 3, 1);
    RAISE EXCEPTION 'TEST FAILED: adding to an old roadmap was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 13: adding to an old roadmap was blocked';
END $$;

-- Test 14: adding to the new ACTIVE roadmap works
SELECT pg_temp.add_act((SELECT roadmap_version_id FROM roadmap_versions
                        WHERE user_id = pg_temp.uid('u1@test.local') AND status = 'ACTIVE'),
                       'T-A4', 1, 1);
DO $$ BEGIN RAISE NOTICE 'OK 14: adding to the active roadmap worked'; END $$;

-- Test 15: the content of an old roadmap cannot be edited
DO $$
BEGIN
    UPDATE roadmap_versions SET weekly_hours_budget = 40
    WHERE roadmap_version_id IN (SELECT roadmap_version_id FROM old_rv);
    RAISE EXCEPTION 'TEST FAILED: editing a roadmap was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 15: editing a roadmap was blocked';
END $$;

-- Test 16: SUPERSEDED cannot go back to ACTIVE
DO $$
BEGIN
    UPDATE roadmap_versions SET status = 'ACTIVE'
    WHERE roadmap_version_id IN (SELECT roadmap_version_id FROM old_rv);
    RAISE EXCEPTION 'TEST FAILED: reverting a roadmap was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 16: reverting a roadmap was blocked';
END $$;

-- audit log
INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, outcome, details)
VALUES (pg_temp.uid('u1@test.local'), 'READ_SUBMISSION', 'submission', 'abc', 'DENIED', '{"t":"T"}');

-- Test 17: audit log cannot be edited
DO $$
BEGIN
    UPDATE audit_logs SET action = 'changed' WHERE details->>'t' = 'T';
    RAISE EXCEPTION 'TEST FAILED: editing the audit log was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 17: editing the audit log was blocked';
END $$;

-- Test 18: audit log cannot be deleted
DO $$
BEGIN
    DELETE FROM audit_logs WHERE details->>'t' = 'T';
    RAISE EXCEPTION 'TEST FAILED: deleting the audit log was allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'TEST FAILED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK 18: deleting the audit log was blocked';
END $$;

-- delete user 1: everything of user 1 goes, the audit row stays (without the user)
DELETE FROM users WHERE email = 'u1@test.local';

-- expected: 0, 0, 0, 0, 1, 1
SELECT
    (SELECT count(*) FROM roadmap_versions
      WHERE career_version_id IN (SELECT career_version_id FROM career_versions
                                  WHERE version_tag = 'test-v0'))       AS roadmaps_left,
    (SELECT count(*) FROM learning_activities WHERE title LIKE 'T-A%')  AS activities_left,
    (SELECT count(*) FROM checklist_items WHERE content LIKE 'T-item%') AS checklist_left,
    (SELECT count(*) FROM progress_records WHERE output_note = 'T-note') AS progress_left,
    (SELECT count(*) FROM reminders WHERE deduplication_key = 'k1')     AS reminders_left,
    (SELECT count(*) FROM audit_logs
      WHERE details->>'t' = 'T' AND actor_user_id IS NULL)              AS audit_kept;

ROLLBACK;