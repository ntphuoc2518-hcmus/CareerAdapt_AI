# CareerAdapt AI - UML Use-Case (MVP)

This folder contains the use-case diagram for **CareerAdapt AI, MVP: Data Analyst internship preparation**.

## Files

- `CareerAdaptAI_UseCase.pdf` - print/share-ready A3 landscape PDF.
- `CareerAdaptAI_UseCase.png` - high-resolution diagram image for reports or slides.
- `CareerAdaptAI_UseCase.svg` - vector image; zoom without losing clarity.
- `CareerAdaptAI_UseCase.puml` - editable PlantUML source.
- `USE_CASE_SPECIFICATIONS.md` - concise use-case specifications and exception cases.

## Modeling choices

- **Primary actor:** `Người học / Sinh viên`.
- **External system actor:** `Dịch vụ AI bên ngoài (LLM)`, used only to propose qualitative feedback with evidence.
- **No content reviewer/admin actor:** removed as requested.
- **MVP scope:** Data Analyst only. Backend, Frontend, Security and other career packs are future extensions, not actors or active MVP cases here.
- **Use-case count:** 12, matching the Week 02 exercise's suggested range of 8-12.
- **`<<include>>`:** submitting a task includes evaluating the submission; evaluation includes evidence-grounded qualitative feedback from the LLM as a supporting behavior. If AI fails, the submission remains pending/needs review rather than being discarded or assigned an invented score.
- **`<<extend>>`:** an in-app reminder conditionally extends progress tracking when an activity is upcoming or overdue.

## Scope boundaries

The diagram intentionally omits job search, CV creation, multi-career ranking, push/email notifications, and content-review workflows. The diagram describes **who interacts with which goals**, not UI screens, control flow, database tables, API endpoints, or the order of every step.

## PlantUML

Open `CareerAdaptAI_UseCase.puml` in a PlantUML extension or renderer to edit/regenerate the diagram. The supplied SVG/PNG/PDF use a fixed layout for readability; a PlantUML renderer may position some elements differently while preserving the use cases and relationships.
