# Permissions matrix (MVP proposal; align with TV3 auth)

| Resource | Learner | Reviewer/admin | Enforcement requirement |
|---|---|---|---|
| Own profile | Read/update own | Only if a documented admin/review workflow requires it | Verified identity + `user_id` predicate |
| Own submissions/files | Read own; create own | Only if explicitly authorized by workflow | Owner-scoped query; authorize before file read |
| Other user's submissions/files | Deny | Deny by default | Same not-found response; `DENIED` audit event |
| Assessment/criterion evidence | Read own result | Reviewer access only through approved role policy | Join through submission owner or verified reviewer permission |
| Own roadmap/checklist/progress/reminders | Read/update according to workflow | No default access | Join through roadmap owner or explicit `user_id` |
| Audit logs | No direct access by default | Restricted operational access | Never store submission body or secrets |
| Content catalog and rubric | Read published content | Draft/review/publish according to assigned role | Preserve database triggers and review history |

This is a proposed MVP matrix, not proof that all application endpoints enforce it. TV3 must bind `authenticated_user_id` to a verified token/session and apply role checks at every endpoint.
