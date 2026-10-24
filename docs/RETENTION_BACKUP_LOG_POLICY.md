# Retention, backup and logging policy

- Submission file expiry defaults to 90 days through the `submission_files.expires_at` column and `007_retention.sql` cleanup workflow.
- Cleanup must remove physical bytes before setting `deleted_at`; failed physical deletions remain eligible for retry.
- Account deletion should preserve audit history while the actor reference is nulled by the foreign key policy.
- Audit logs contain action, target type/ID, outcome and minimal structured details; never store raw submissions, passwords, tokens or unnecessary PII.
- Backups: **maximum 30-day retention is proposed and pending team confirmation**. Until approved, document the actual storage provider, retention, encryption and restore test procedure rather than asserting this proposal is active.
- Restore testing should use an isolated non-production database. Never test restore/drop operations against `careeradapt`.
