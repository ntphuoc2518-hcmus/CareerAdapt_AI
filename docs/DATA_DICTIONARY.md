# Data dictionary overview

The SQL migrations are authoritative for exact columns and constraints.

| Table | Purpose | Personal-data ownership path |
|---|---|---|
| `users` | Account and authentication metadata | `user_id` |
| `profiles` | Display name, major, career goal, skills and preferences | `user_id` |
| `submissions` | Learner submissions and processing state | `submissions.user_id` |
| `submission_files` | Metadata for private uploaded files | Join through `submission_id` to `submissions.user_id` |
| `assessments` | Deterministic assessment result | Join through `submission_id` to `submissions.user_id` |
| `criterion_scores` | Rubric scores, evidence quotes and rationale | Join through `assessment_id` → `submissions.user_id` |
| `roadmap_versions` | Personal roadmap versions | `user_id` |
| `learning_activities` | Activities scheduled into a roadmap | Join through `roadmap_version_id` → `roadmap_versions.user_id` |
| `progress_records` | Activity progress history and notes | Join through `learning_activity_id` → roadmap owner |
| `checklist_items` | User checklist | `user_id` and activity-owner trigger |
| `reminders` | In-app reminders | `user_id` and activity-owner trigger |
| `audit_logs` | Security events; no submission body | `actor_user_id` may become NULL on account deletion |

## Key constraints

- `submissions` enforces unique `(user_id, idempotency_key)`.
- `submission_files` records SHA-256, size and expiry; stored bytes live outside PostgreSQL.
- `criterion_scores` limits evidence quotes to 25 words and constrains unverified scores.
- Roadmap/activity and published-content triggers restrict mutation. Do not bypass these guards for tests or seed cleanup.
