# CareerAdapt ERD (core data and ownership paths)

```mermaid
erDiagram
    USERS ||--o| PROFILES : owns
    USERS ||--o{ SUBMISSIONS : submits
    TASK_VERSIONS ||--o{ SUBMISSIONS : assigned
    SUBMISSIONS ||--o{ SUBMISSION_FILES : attaches
    SUBMISSIONS ||--o| ASSESSMENTS : receives
    ASSESSMENTS ||--o{ CRITERION_SCORES : contains
    USERS ||--o{ ROADMAP_VERSIONS : owns
    ROADMAP_VERSIONS ||--o{ LEARNING_ACTIVITIES : contains
    LEARNING_ACTIVITIES ||--o{ PROGRESS_RECORDS : history
    LEARNING_ACTIVITIES ||--o{ CHECKLIST_ITEMS : checklist
    USERS ||--o{ CHECKLIST_ITEMS : owns
    USERS ||--o{ REMINDERS : receives
    USERS ||--o{ AUDIT_LOGS : actor
```

Use `db/migrations/001_users_profiles.sql` through `007_retention.sql` as the source of truth for column types, constraints and triggers. This diagram highlights personal-data ownership paths; it is not a complete depiction of all content/catalog tables.
