# Security test checklist / report template

Run tests only against `careeradapt_demo` when they connect to PostgreSQL.

- [ ] `python src/test_security.py` — known-name, email/phone redaction, evidence quote and ownership helper.
- [ ] `python src/test_file_storage.py` — UTF-8, NUL, invalid UTF-8, size, extension, traversal-safe generated names and test cleanup.
- [ ] `python src/test_data_access.py` — cross-user submission is hidden, denied attempt audited, no status change.
- [ ] `python src/test_export_user_data.py` — export includes all documented personal-data groups and uses owner-scoped query parameters.
- [ ] `python src/test_delete_account.py` — account lifecycle isolation and physical file cleanup.
- [ ] `python src/test_cleanup_job.py` — expired file cleanup retry behavior.
- [ ] Verify no test files remain in `secure_storage/` after tests.
- [ ] Confirm all application endpoints obtain identity from TV3's verified token/session, not request-supplied `user_id`.
- [ ] Confirm TV4 redacts PII before LLM calls and verifies evidence quotes.

## Results

| Date | Test | Result | Notes / issue ID |
|---|---|---|---|
| Pending | Security utilities | Not run in this package build | Fill in after local execution |
| Pending | File storage | Not run in this package build | Fill in after local execution |
| Pending | Data access integration | Requires local `careeradapt_demo` and DB credentials | Fill in after local execution |

Do not report tests as passed until they have been run in the target environment.
