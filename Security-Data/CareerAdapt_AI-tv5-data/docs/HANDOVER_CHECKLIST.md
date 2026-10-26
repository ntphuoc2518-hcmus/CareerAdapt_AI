# TV5 handover checklist — Steps 12–18

- [ ] Review `src/data_access.py` with TV3; connect `authenticated_user_id` to verified identity middleware.
- [ ] Confirm no endpoint trusts `X-User-Id` or request-body `user_id`.
- [ ] Review file read authorization and private storage path with TV3.
- [ ] Confirm TV4 calls `redact_pii(text, known_name=profile_name)` before LLM processing and calls `verify_evidence_quote` for evidence.
- [ ] Send demo scenarios and test outcomes to TV6.
- [ ] Ask TV1 to approve rubric and O*NET/ESCO mappings.
- [ ] Ask content owner/TV1 to review the three published resources whose `approved_by` is NULL.
- [ ] Confirm whether backup retention of 30 days is approved; until then mark it pending.
- [ ] Confirm participant notice and 90-day file retention wording with project owner.
- [ ] Record local test results; do not claim unrun tests passed.
- [ ] Review README, requirements and migration order before handing over.
