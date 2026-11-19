# CareerAdapt AI — Final Audit Report

Date: 18/11/2026. Version before: **5.47.0**. Version after: **5.48.0**.

Backup taken before any change: sibling folder `CareerAdapt_AI_backup_truoc_kiem_dinh_cuoi_20261118` (source, data, configuration; `.venv` excluded). Both databases were also copied with SQLite's online backup API, opened read-only, to `data/careeradapt.sqlite3.consistent` and `data/accounts.sqlite3.consistent` inside that folder. Both copies pass `PRAGMA integrity_check`. The real databases were never written by this audit.

Every probe ran either on the test suite's temporary databases or on a local server (port 8765) that serves a **copy** of the data.

---

## 1. Executive summary

CareerAdapt AI already had a large, strict test suite (1289 tests) and two full audits this month: 15/11 (v5.32) and 17/11 (v5.46). This audit did not assume those reports were right. It re-established a baseline, then probed each scenario the brief requires through the real API and a real browser.

Most required behaviours were confirmed correct as they stand:
- blank and wrong answers score 0 at level 0;
- self-reported levels never count as verified;
- data cannot leak between accounts;
- malformed input is refused with 422;
- every page shows an error with a retry button when the server fails or the network drops;
- reset then retake does not carry old results over.

Two defects were found and fixed:

| # | Severity | Defect | Fixed |
|---|---|---|---|
| D-1 | **LOW** (consistency, defence in depth) | "Kiểm tra" on a practice exercise, and an expert's automatic check of a code question, ran code in the sandbox without the one-run-per-account slot that "Chạy thử" takes. At first this looked like a way to start many sandbox processes at once. A live measurement on the copy server showed that the per-learner request lock (5.34) already runs one account's requests one after another, and other users' requests stayed fast (2–27 ms) while a check ran. The gap only mattered where that lock is skipped: assistant routes, or a request longer than the 120-second lock lease. | Yes, with 5 new tests |
| D-2 | **MEDIUM** (UX, lost place) | When a session expired mid-task, or a learner opened a deep link while signed out, signing in always went to the dashboard. The page the learner was on was lost. | Yes, with 2 new browser tests |

Test results:
- Before: **1289 passed, 11 skipped, 0 failed**.
- After: **1296 passed, 11 skipped, 0 failed**.

The 11 skipped tests are BLOCKED by the environment: 10 need a live Gemini key in the test run, 1 needs Docker.

---

## 2. Initial project status

| Item | State at the start |
|---|---|
| Version | 5.47.0 (`backend/config.py`) |
| Git | Not a git repository. No team changes to protect through git; safety comes from the backup folder above. |
| Startup | `start.bat` / `python run.py` (README). A local server on a copy of the data started cleanly. |
| Test suite | 1289 passed, 11 skipped in 7 min 23 s (`.venv/Scripts/python -m pytest -q -p no:cacheprovider`) |
| Known open items (from the 17/11 report) | One exam question per skill × difficulty (needs experts); live Gemini and real Docker never run; browser focus events are client-reported |

## 3. Architecture overview

- **Backend:** FastAPI (`backend/main.py`) with routers in `backend/api/`.
  - Domain services sit in `backend/*.py`: `exam_service`, `career_process`, `learning_journey`, `lesson_checks`, `practice`, `final_assessment`, `contributions`, `targeting`, `jd_matching`, `insights`, `mistakes`, `assessment_reliability`, `assessment_policy`.
  - The deterministic engines sit in `backend/engine/`: the exam grader, rubric engine, the SQL and Python sandboxes, and JD parsing.
  - The AI layer is `backend/ai_service/`: gateway, guardrails, a tool registry that reads only the signed-in user's data, the task engine with rule-based fallbacks, and the knowledge base.
- **Data:** SQLite with WAL.
  - `data/careeradapt.sqlite3` holds learning data (50 tables).
  - `data/accounts.sqlite3` holds accounts and sessions.
  - Migrations are versioned and back up before changing anything. A schema-version table and foreign keys have been in place since v5.34.
- **Frontend:** vanilla ES modules, a hash router (`frontend/js/main.js`) and one stylesheet system. The login page has its own strict CSP.
- **Integrated flow:**
  1. Account and profile.
  2. Declared skills (never verified).
  3. Target JD: the library, or an import whose extracted requirements carry source excerpts.
  4. Entry exam: SQL and Python run in the sandbox; written answers are graded by rubric with critical gates.
  5. Verified levels, then Skill Gap, then a DAG roadmap of weekly lessons.
  6. Study timer, lesson completion check (post-learning reassessment), spaced reviews and practice (never evidence).
  7. Final assessment, then updated verified levels, ranking and reports.

## 4. Modules and features inspected

| Area | How it was checked |
|---|---|
| Authentication, sessions, data isolation | Existing suite plus probes. Another account's lesson, activity, conversation, test attempt and assessment each return **404**. Login is rate-limited (429). Every non-public route needs a session (an existing test enumerates them). |
| Skill assessment | API probes with blank, wrong, partly right (SQL only), all-correct, and **another dataset's correct numbers** |
| JD analysis | Import probes: empty, spaces only, over 30,000 characters, HTML/script, nonsense text. Source links are rendered through `safeUrl`. |
| Skill Gap | Reset followed by a blank retake; gap fields checked against verified evidence |
| Learning plan and reassessment | Code reading of `lesson_checks.py`; existing tests cover the full flow (pass, fail, retry wait, evidence recorded once) |
| Practical environments | Code paths of run, check and grade for exam, practice, final assessment and expert checks (this found D-1) |
| AI | Task engine fallbacks; the assistant on the copy server without a model (rule-based answers say so) |
| Frontend | Real Edge, 36 page views at 1360 px and 375 px (learner and admin): console errors, 5xx responses, horizontal overflow, broken images, error boxes, in-app links that match no route, unlabeled buttons. Every page was also tested with the API returning 500 and with the network cut. Session expiry was checked as well. |
| Static checks | Every `data-act` button has a handler (72 actions). No user text is inserted into HTML unescaped in the common patterns. |
| Performance | 19 main GET endpoints timed on the copy data |

## 5. Problems discovered

| ID | Severity | Area | Finding |
|---|---|---|---|
| D-1 | LOW | Practical environments / stability | Practice "Kiểm tra" and the expert check skipped the code-run slot; the per-learner request lock limited the effect (see section 6) |
| D-2 | MEDIUM | Frontend / UX | Signing in after an expired session or a deep link lost the page (see section 6) |
| O-1 | INFO | Assessment | An answer that copies another dataset's figures into the manager email still earns 70% of that question's points (structure, recommendation, limitation). This is not a defect: the figures case fails, the skill level is capped at 1 instead of 2, and the reliability table marks it. Recorded so the team can decide whether wrong figures should be a critical gate. |
| O-2 | LOW | Dependencies | `StarletteDeprecationWarning`: the test client asks for `httpx2`. Not changed, because the team rule is not to swap libraries on our own. |

All other probes passed (section 15).

## 6. Root cause analysis

**D-1.**
- What already existed:
  - `exam_service.run_question_code` (the "Chạy thử" button) protects the server with `_claim_run`: an in-process set, a 1-second pause, and a cross-process lease `code-run:<user>`.
  - Since 17/11 the background grader also takes leases.
- Where the slot was missing:
  - `practice.check` called `evaluate_question` directly. That function executes the learner's SQL or Python once per test case.
  - `contributions.run_check` and `submit` call `validate`, which runs the reference answers on all four datasets. They did the same.
- Why it was missed: the protection lived inside one function instead of around "execute user code". A new caller did not inherit it.
- Actual exposure, measured on the copy server:
  - Four parallel checks from one account finished one after another (0.31 s, 0.62 s, …). The learner lock in `learner_sync_middleware` serialises one account's API requests across processes.
  - A public request sent during a 1-second check answered in 2–27 ms, so the server was not blocked.
  - The missing slot therefore mattered only where that lock does not apply: lock-free assistant routes, or a request outlasting the 120-second lease.

**D-2.**
- On a 401, `core.js` redirected to `/login` without recording where the learner was.
- After a successful login, `login.js` always went to `/app`.
- The server's redirect from `/app#/…` to `/login` keeps the fragment, but nothing read it.

## 7. Bugs fixed

**D-1:**
- The slot became a context manager, `exam_service.code_run_slot(user_id, gap=True)`. Every path that executes a person's code on request now takes it:
  - "Chạy thử" in the exam, the final assessment and practice (unchanged behaviour, including the 1-second pause);
  - practice "Kiểm tra" for SQL and Python exercises;
  - an expert's check and submit of an EXAM-bank question.
- Written practice answers and multiple-choice questions run no code and take no slot.
- A graded check uses `gap=False`: checks one after another are allowed because each one is bounded by its own run, but two at the same time are refused with 429. The slot is always released in `finally`.

**D-2:**
- `core.js` saves the current in-app fragment in `sessionStorage` before redirecting on a 401.
- `login.js` returns to that fragment, or to the fragment of a link opened while signed out, after a successful sign-in.
- Only fragments matching `^#/[A-Za-z0-9_\-/]{0,200}$` are accepted, so there is no open redirect: a query, a colon or `#//other.host` is ignored and the learner lands on the dashboard.

## 8. Files modified

| File | Change | Purpose | Effect on other modules |
|---|---|---|---|
| `backend/exam_service.py` | `code_run_slot` context manager; `_claim_run(user_id, gap)`; `run_question_code` uses the slot | D-1 | Same behaviour for "Chạy thử" |
| `backend/practice.py` | `check` takes the slot for SQL and Python exercises | D-1 | 429 while another run of the same account is going |
| `backend/contributions.py` | `_validate_as(user, row)` takes the slot for EXAM-bank check and submit | D-1 | The admin approval re-check is unchanged (it runs as the admin, one request at a time) |
| `frontend/js/core.js` | Saves the page on 401 | D-2 | – |
| `frontend/js/login.js` | `returnHash()` after sign-in | D-2 | Reset links (`#reset=…`) are unaffected |
| `tests/test_audit_2026_11_18.py` | **New**, 5 tests | Protect D-1 | – |
| `tests/test_ui_e2e.py` | 2 new browser tests | Protect D-2 | – |
| `backend/config.py`, `frontend/index.html`, `frontend/login.html` | Version 5.48.0 and `?v=` cache keys | Browsers load the new scripts | – |
| `README.md`, `UPGRADE_REPORT.md` | Version and change notes | Documentation | – |

No database schema change, no migration, no data change.

## 9. Features improved

- **Code execution consistency:** every feature that runs a person's code takes the same one-run slot, in addition to the request lock (D-1).
- **Session continuity:** signing in again returns to the page in use (D-2).

## 10. New features implemented

None this round. The brief asks to prioritise correctness, stability and security. The 17/11 audit already added the reliability table, the "actual mistakes" panel and the assessment policy, and 18/11 added the AI advisor strip in the Career Adapt Plan (5.47). The remaining high-value features need decisions the code cannot make (section 21).

## 11. UI/UX improvements

- D-2 (return after sign-in).
- Verified, with no change needed:
  - all 36 page views had no console errors, no 5xx, no page-level horizontal overflow and no broken images;
  - no in-app link points to a missing route;
  - the 375 px tables and the admin tab bar scroll inside their own containers by design;
  - with the API failing or the network cut, all 12 learner pages replace the loader with "Không tải được dữ liệu" and a "Thử lại" button.

## 12. Security improvements

- D-1 makes every on-request code execution take the same slot. It does not rely only on the request lock, which some routes skip.
- D-2 was built with an allow-list pattern so that it cannot become an open redirect (tested with `#//evil.example/x`).
- Re-verified:
  - cross-account reads (404);
  - CSRF origin and token checks on state-changing requests (403 without them; seen directly in this audit);
  - login rate limiting;
  - JD import size limit;
  - escaped rendering of imported JD text.

## 13. Performance improvements

No change was needed. On the copy data, the slowest of 19 main endpoints were:
- `/me/export` (605 KB): 46 ms;
- `/career-process/insights`: 42 ms.

Every other endpoint answered in 6–29 ms, measured as the minimum of three calls.

## 14. Tests executed

- **Full suite**, before and after.
- **New and targeted tests:** `tests/test_audit_2026_11_18.py` and the new browser tests in `tests/test_ui_e2e.py`.
- **Live checks on the restarted copy server (new code):**
  - the app starts and reports 5.48.0;
  - four parallel practice checks from one account;
  - public-request latency during a check.
- **API probes** (temporary test database):
  - blank exam, wrong exam, SQL-only, all-correct and other-dataset answers;
  - a save kept after re-opening the exam;
  - cross-account reads;
  - five JD import edge cases;
  - malformed JSON on five write endpoints;
  - goal change without confirmation;
  - reset followed by a blank retake.
- **Real-browser scripts** (Edge, copy server):
  - page sweep at 1360 px and 375 px for learner and admin;
  - API-500 and offline sweeps;
  - session expiry and deep link;
  - unsafe fragment.

## 15. Test results before and after

| Run | Passed | Failed | Skipped (BLOCKED) |
|---|---|---|---|
| Before (5.47.0) | 1289 | 0 | 11 |
| After (5.48.0) | 1296 | 0 | 11 |

The first full run after the changes had one failure, in a new browser test written here. After clearing the cookies, a background refresh sometimes reached the sign-in page before the test's click did, so the click waited on a page that had already gone. The test now waits for the sign-in form whichever request comes first. It passed three times in a row and in the final full run. No product test changed its expectations.

Required scenarios:

| # | Scenario | Result | Evidence |
|---|---|---|---|
| 1 | Brand-new user | PASS | The new account in the browser test signs in and lands on the right page; the dashboard shows the start of the process |
| 2 | Existing user with history | PASS | Copy learner: 36 page views, no errors |
| 3 | Invalid input | PASS | Malformed JSON gives 422 on 5 endpoints; JD empty, spaces only or over 30,000 characters gives 422 |
| 4 | Empty answers | PASS | Score 0, every skill level 0, not passed |
| 5 | Completely wrong answers | PASS | Score 0, level 0 |
| 6 | Repeated assessment | PASS | After reset, a blank retake gives level 0; earlier results do not carry over |
| 7 | Completing learning activities | PASS | Existing tests (`test_learning_roadmap_2.py`, `test_learning_tasks.py`) |
| 8 | Passing and failing post-learning checks | PASS | Existing tests: a pass records evidence once; a fail needs review, waits and keeps the history |
| 9 | Changing the target JD | PASS | A change without confirmation is refused (422); confirm and cancel are covered by the existing 17/11 tests |
| 10 | External AI failure | PASS | Existing tests (timeouts, invented numbers dropped); the copy server without AI answers with rule-based text and says so |
| 11 | Network interruption | PASS | Offline sweep: every page shows an error and "Thử lại" |
| 12 | Logging out during a workflow | PASS (fixed by D-2) | Session expiry returns to the same page after sign-in |
| 13 | Accessing other accounts' data | PASS | 404 on 5 resource types |
| 14 | Missing or inconsistent records | PASS | Existing integrity, foreign-key and migration tests; the integrity check of both database snapshots is ok |
| 15 | Unexpected server responses | PASS | API-500 sweep on 12 pages |

## 16. Newly added test cases

`tests/test_audit_2026_11_18.py`:
1. A practice check waits for a run already going (429, nothing stored), then succeeds.
2. A practice check releases the slot, and checks one after another are allowed.
3. A written practice answer needs no slot.
4. "Chạy thử" keeps its pause and shares the slot.
5. An expert check and submit of a code question take the slot; the check passes once the slot is free.

`tests/test_ui_e2e.py`:

6. Signing in again returns to the page the learner was on: a deep link while signed out, and a session that ends mid-task.
7. A fragment that is not an app page is ignored after signing in.

## 17. Remaining issues

- One exam question per skill × difficulty. The contribution workflow (5.35) is ready; it needs expert authors and reviewers, not AI-written questions.
- Deterministic grading of free text cannot judge reasoning written in varied, plausible sentences. Such answers are labelled "checked by key phrases" in the reliability table.
- Exam focus-loss events are reported by the browser and cannot be enforced server-side.
- O-1: deciding whether wrong figures in a report should be a critical gate is a product decision.
- O-2: the Starlette test-client deprecation warning.

## 18. External dependencies and API limitations

| Dependency | Status |
|---|---|
| Gemini (AI explanations, assistant, JD summary) | BLOCKED in tests: the 10 live tests skip without a key in the test environment. The product works without it (rule-based fallback, labelled). |
| Docker sandbox mode | BLOCKED: Docker is not installed. The default process sandbox is tested. |
| SMTP (password reset mail) | NOT TESTED against a real mail server |
| Microphone (assistant voice input) | NOT TESTED with a real microphone |

## 19. Known technical risks

- SQLite with several worker processes relies on the leases and revisions added in 5.34. A busy multi-user deployment should move to a server database.
- The process sandbox depends on the host operating system's limits. Docker mode is stronger but has not been verified here.
- The user's own server on port 8000 runs the code it started with; it needs a restart to serve 5.48.0. There is no schema change.

## 20. Final system quality assessment

| Module | Initial status | Work performed | Final status |
|---|---|---|---|
| Authentication | Working, well tested | Probes: isolation, rate limit, CSRF; sign-in return (D-2) | PASS |
| User Profile | Working | Covered by the page sweep and existing tests | PASS |
| Skill Assessment | Accurate in all probes | Blank, wrong, partial and other-dataset probes; O-1 recorded | PASS |
| JD Analysis | Working | Five import edge cases, safe links | PASS |
| Skill Gap Analysis | Derived from verified evidence only | Reset and retake probe | PASS |
| Learning Plan | Working, reassessment separate from completion | Code review and existing tests | PASS |
| Practical Environments | Working; defect D-1 (LOW) | One run slot for every code execution; parallel load measured live | PASS (fixed) |
| AI System | Working with fallback; live model not testable here | Fallback checked on the copy server | PASS (live Gemini BLOCKED) |
| Database | Consistent | Read-only snapshots, integrity ok, no schema change | PASS |
| Frontend/UI/UX | **Defect D-2** | 36-view sweep, failure sweeps, return after sign-in | PASS (fixed) |
| Security | Good | D-1 closed, open redirect avoided, isolation re-checked | PASS |
| Automated Testing | 1289 passed | +7 tests | PASS: 1296 passed, 0 failed, 11 BLOCKED |
| Performance | Fast (≤ 66 ms) | Timed 19 endpoints | PASS |

Overall: within the scope that can be tested here, the product behaves correctly end to end. The two defects found are fixed and covered by tests. What remains needs people or infrastructure: expert questions, a live AI key, Docker, SMTP and a microphone.

## 21. Recommended future improvements

1. Have experts add 2–3 reviewed questions per skill × difficulty through the contribution workflow.
2. Run `tests/test_ai_live.py` with a real key, once the team agrees to send test data to Gemini.
3. Verify the Docker sandbox on a machine with Docker.
4. Decide on O-1 (a critical gate for wrong figures in written reports).
5. A shareable, verifiable skill profile (needs a privacy decision), and practice interviews (practice only, never evidence).

### Most important changes for review

- `backend/exam_service.py`: `code_run_slot`, used by every on-request code execution.
- `backend/practice.py` and `backend/contributions.py`: checks take the slot.
- `frontend/js/core.js` and `frontend/js/login.js`: return to the same page after signing in, allow-listed fragments only.
- `tests/test_audit_2026_11_18.py` and two tests in `tests/test_ui_e2e.py`.
