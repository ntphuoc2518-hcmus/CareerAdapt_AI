# CareerAdapt — Steps 12–18 patch

This is a **patch bundle**, not a replacement for the entire project. It contains code files to copy into the existing repository and new documentation. Apply it to the project that already has Steps 7–11; do not replace the whole repository with the original ZIP.

## Apply on Windows PowerShell

From `D:\mtr_code\CareerAdapt-Data`:

1. Back up these files first: `src\file_storage_service.py`, `src\security_utils.py`, `src\test_file_storage.py`, `src\test_security.py`, `src\user_data_lifecycle.py`.
2. Extract this ZIP into the project root and allow the listed files to merge/overwrite. The archive paths are relative to the project root (`src\...`, `docs\...`, `.env.example`, `README.md`, `requirements.txt`).
3. Open `.env` and add `MAX_FILE_SIZE_MB=5` if absent. Do not replace your `.env` with `.env.example`; keep your actual credentials private.
4. Confirm the database has the migrations through `007_retention.sql` and the demo database exists. Do not run tests against `careeradapt`.
5. Run the unit tests first, then the integration suite below.

## Run tests

```powershell
$env:DB_NAME = "careeradapt_demo"
python src\test_security.py
python src\test_file_storage.py
python src\test_data_access.py
python src\test_export_user_data.py
python src\test_delete_account.py
python src\test_cleanup_job.py
```

Or run the orchestrator:

```powershell
$env:DB_NAME = "careeradapt_demo"
python src\test_security_scenarios.py
```

The integration test in `test_data_access.py` creates two temporary users and one temporary submission in an uncommitted transaction, then rolls back. It requires a seeded row in `task_versions`. The orchestrator forces `DB_NAME=careeradapt_demo` for every child process. Do not change it to `careeradapt`.

## What this patch covers

- Step 12: owner-scoped submission queries, hidden not-found response for cross-user access, `DENIED` audit logging, and owner-authorized file reads.
- Steps 13–14: UTF-8-only file validation, NUL/size/extension checks, safe generated names, storage-root containment, directory creation, and tests that clean up created files.
- Step 15: expands data export to profile, submissions/file metadata, assessments/scores/evidence, roadmaps, activities, progress, checklist and reminders.
- Step 16: adds optional exact known-name redaction to existing email/phone redaction.
- Step 17: a test orchestrator runs security, storage, cross-user, account-deletion and cleanup tests against the demo DB.
- Step 18: ERD, data dictionary, permissions matrix, retention/log policy, threat notes, participant notice, checklist and handover docs.

## Important integration notes

- `authenticated_user_id` in `data_access.py` must come from TV3's verified server-side identity/token. This patch does not implement authentication middleware or a web endpoint.
- File reads should go through `read_owned_submission_file`; do not expose `read_stored_file` directly to clients.
- TV4 should call `redact_pii(text, known_name=profile_display_name)` before any LLM call and verify evidence quotes.
- The three resources with `published` status and `approved_by=NULL` remain a content-owner review item; do not disable database triggers to change them.
- The test scripts are supplied but **have not been run against your local Windows project/database**. Treat them as unverified until you run them.
