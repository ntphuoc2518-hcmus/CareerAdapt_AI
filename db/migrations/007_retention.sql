BEGIN;

-- Return expired file records without marking them deleted.
-- Python must delete the physical file first, then set deleted_at.
-- Row locks prevent two cleanup workers from processing the same row concurrently.
CREATE OR REPLACE FUNCTION purge_expired_submission_files()
RETURNS TABLE (purged_file_id UUID, purged_path TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT sf.file_id, sf.stored_path
    FROM submission_files AS sf
    WHERE sf.expires_at <= now()
      AND sf.deleted_at IS NULL
    ORDER BY sf.expires_at, sf.file_id
    FOR UPDATE OF sf SKIP LOCKED;
END;
$$ LANGUAGE plpgsql;

COMMIT;
