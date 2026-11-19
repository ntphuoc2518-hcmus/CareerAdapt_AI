# CareerAdapt AI - Use-Case Specifications (MVP)

**Scope:** Data Analyst at internship-preparation level. These specifications follow the user-goal/use-case idea from CSC10014 Week 02. They are not a sequence diagram: the use cases describe goals, while detailed ordering belongs in the main-flow specification of each use case.

## Actors

| Actor | Role |
|---|---|
| **Người học / Sinh viên** | Sets a learning goal, completes practical tasks, reads evidence-based feedback, builds a learning roadmap and tracks progress. |
| **Dịch vụ AI bên ngoài (LLM)** | Supplies structured qualitative comments and evidence excerpts when requested by the system. It does not own the final score, change the rubric or change career requirements. |

No content-reviewer actor is included.

## Use cases

| ID | Use case | Actor / trigger | Main output and acceptance focus | Alternative / error handling |
|---|---|---|---|---|
| **UC-01** | Quản lý hồ sơ và mục tiêu học tập | Người học edits profile or pastes a job description | Saves Data Analyst goal, self-declared skills, study hours per week and target deadline. The learner may use a reference benchmark or review and apply a keyword-derived skill standard from a pasted JD. Self-reported skill stays separate from assessed evidence; the original JD text is not persisted. | Reject invalid values; explain the field that must be corrected. If no known skills are found in a JD, ask for the requirements section rather than silently using a default profile. |
| **UC-02** | Xem khung kỹ năng và chọn bài thử | Người học opens the skill framework | Shows the Data Analyst skills, target level, task duration, required output and support policy before starting. | Skills without a valid assessment are shown as “chưa đánh giá”, not level 0. |
| **UC-03** | Làm và nộp bài thực hành | Người học starts a task and submits the output | Saves the submission and its task/version, mode (practice or assessment) and declared tools/support. Submission must be traceable and not processed twice. | Unsupported file or missing output receives a concrete error and a resubmission option; do not infer a low ability level. |
| **UC-04** | Đánh giá bài nộp theo rubric | Triggered by UC-03 | Runs deterministic checks where possible and combines their results with the structured AI feedback process; returns per-criterion status, not an unsupported whole-career claim. | If AI times out or the checks and AI disagree, keep the submission and mark it pending/needs review; do not create duplicate assessments. |
| **UC-05** | Nhận xét định tính có dẫn bằng chứng | Dịch vụ AI bên ngoài (LLM), called within UC-04 | Returns structured criterion ID, proposed level, excerpt copied from the submission, and rationale. The server validates structure and checks that evidence exists in the submission. | Missing/invalid evidence or malformed output becomes “chưa kết luận” / “cần kiểm tra”; AI cannot overwrite final deterministic scores or rubric versions. |
| **UC-06** | Xem kết quả đánh giá và bằng chứng | Người học opens a completed or review-pending result | Shows level by criterion, cited evidence, explanation, validation/review status, task version and rubric version. | If the review is pending, display that status and next action instead of presenting an unsupported final result. |
| **UC-07** | Xem khoảng cách kỹ năng (gap, coverage) | Người học views their skill gap | Shows target versus evidenced level, gap, weights, evidence coverage and skills not yet measured for the selected benchmark, including a learner-approved custom JD benchmark. Skills absent from a custom JD are marked out of scope. Any overall readiness figure must include coverage/version context. | If coverage is below 80% or a core skill lacks evidence, show partial results and missing assessments; do not show an overall readiness score. |
| **UC-08** | Tạo lộ trình học cá nhân | Người học provides available hours and planning horizon | Produces a weekly roadmap ordered by gap/priority, prerequisites, estimated time and available study hours. Total scheduled time must not exceed the user's declared capacity. | Invalid prerequisite cycles block roadmap generation; activities that do not fit are shown with reasons and options to extend the plan or reduce the target. |
| **UC-09** | Theo dõi tiến độ học | Người học opens or updates a roadmap activity | Shows activity state, due status and update time; records progress and optional actual time/output. | Marking an activity complete does not automatically raise a skill level. If available hours or deadlines change, create a new roadmap version and preserve history. |
| **UC-10** | Đánh giá lại năng lực | Người học submits an approved comparable task variant | Records a new assessment and compares with earlier evidence only when skill scope, rubric and versions are compatible. | If variants are not proven equivalent or scopes differ, do not claim direct progress; explain why the results are not comparable. |
| **UC-11** | Xem lịch sử đánh giá và lộ trình | Người học opens history | Lists prior assessments, evidence/version references, roadmap versions and recorded changes. Previous versions remain accessible. | A new roadmap or rubric version must not overwrite historical results. |
| **UC-12** | Nhận nhắc nhở trong ứng dụng | Condition: an activity is upcoming or overdue while progress is shown | Shows the next activity or a due/overdue reminder inside the application; this extends UC-09 conditionally. | Avoid duplicate reminders; no push/email notifications are included in the MVP. |

## Relationships shown in the diagram

1. **UC-03 `<<include>>` UC-04:** submission initiates the system's evaluation process. If processing is interrupted, the submission remains stored with a non-final status.
2. **UC-04 `<<include>>` UC-05:** the standard assessment process requests evidence-grounded qualitative feedback from the LLM. The final system result remains subject to server-side validation and rules.
3. **UC-12 `<<extend>>` UC-09:** in-app reminders appear only when the condition applies (an activity is upcoming or overdue).

## Acceptance tests to derive next

- Submit a valid task and verify exactly one submission and evaluation record are created.
- Submit an invalid file and verify a specific resubmission message is shown, not a level-0 assessment.
- Simulate an LLM timeout or feedback without a valid evidence excerpt; verify the result becomes pending/needs review and existing submission data is retained.
- Test `coverage = 79%`, `coverage = 80%`, missing core-skill evidence, and “no evidence yet”; overall readiness must be hidden whenever the stated release conditions are not met.
- Provide fewer study hours than the roadmap requires; verify the scheduled total does not exceed capacity and all unplaced activities include reasons.
- Test an overdue activity; verify one in-app reminder appears without push/email delivery.
- Reassess using incompatible task/rubric versions; verify the system does not present the scores as a direct progress comparison.
