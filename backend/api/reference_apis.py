"""Standardized Reference REST APIs (8 Core Endpoints) for CareerAdapt AI v1.0.

Specifies:
1. GET /careers
2. PUT /me/profile
3. GET /careers/data-analyst/requirements
4. POST /submissions
5. GET /assessments/{id}
6. POST /roadmaps
7. PATCH /activities/{id}/progress
8. GET /me/history
Plus GDPR:
- GET /me/export
- DELETE /me/data, DELETE /me/profile
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.auth import AuthenticatedUser, get_current_user
from backend.store import store
from backend.api.profiles import (
    ProfileUpdateRequest, ProfileResponse, update_profile, get_profile,
    get_user_history, get_skill_history, get_activity_log, get_skill_progress, get_assessment_reliability, get_assessment_policy, export_user_data, delete_user_data, run_profile_diagnostics
)
from backend.api.submissions import (
    SubmissionRequest, SubmissionResponse, extract_answer_file, get_assessment, get_task, list_tasks, my_assessments, regrade_submission, submit_task
)
from backend.api.roadmaps import (
    ProgressUpdateRequest, generate_roadmap_endpoint, get_current_roadmap, get_gap, get_roadmap_history, progress_history, update_activity_progress
)

router = APIRouter(tags=["8 Reference APIs (RFC Contract)"])


# 1. GET /careers
@router.get("/careers")
def list_careers():
    """1. Lấy danh sách các nghề nghiệp mục tiêu và trạng thái phiên bản."""
    return [
        {
            "career_code": store.career_metadata["career_code"],
            "career_title": store.career_metadata["career_title"],
            "status": "PUBLISHED",
            "version_tag": store.career_metadata["version_tag"],
            "target_stage": store.career_metadata["target_stage"],
            "source_references": [
                {"source": "ACM/IEEE Data Science Curricula 2021", "status": "Aligned"},
                {"source": "DAMA-DMBOK2 Data Management Body of Knowledge", "status": "Aligned"},
                {"source": "O*NET 15-2051.01 Data Analysts", "status": "Aligned"}
            ],
            "published_at": store.career_metadata["published_at"]
        }
    ]


# 2. PUT /me/profile (delegates to profile module)
router.add_api_route("/me/profile", update_profile, methods=["PUT"], response_model=ProfileResponse)
router.add_api_route("/me/profile", get_profile, methods=["GET"])
router.add_api_route("/me/diagnostics", run_profile_diagnostics, methods=["GET"], operation_id="get_profile_diagnostics")
router.add_api_route("/me/diagnostics", run_profile_diagnostics, methods=["POST"], operation_id="run_profile_diagnostics")
router.add_api_route("/me/gap", get_gap, methods=["GET"])


# 3. GET /careers/data-analyst/requirements
@router.get("/careers/data-analyst/requirements")
def get_career_requirements():
    """3. Lấy khung chuẩn năng lực nghề Data Analyst (v1.0) kèm trọng số và rubric."""
    # The framework is the weighted skills; a skill with weight 0 is optional and measured only when a JD asks for it.
    framework = [s for s in store.skills if float(s.get("weight", 0)) > 0]
    total_weight = sum(s["weight"] for s in framework)
    return {
        "career_code": store.career_metadata["career_code"],
        "career_title": store.career_metadata["career_title"],
        "version_tag": store.career_metadata["version_tag"],
        "total_weight": round(total_weight, 4),
        "skills": framework,
        "optional_skills": [s for s in store.skills if float(s.get("weight", 0)) <= 0],
        "tasks_catalog": [{key: value for key, value in task.items() if key != "reference_values"} for task in store.tasks]
    }


@router.get("/careers/data-analyst/profiles")
def list_data_analyst_job_profiles():
    """Danh sách hồ sơ yêu cầu Data Analyst theo thị trường/doanh nghiệp và nguồn tham chiếu."""
    return store.job_profiles


# 4. POST /submissions
router.add_api_route("/submissions", submit_task, methods=["POST"], response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/submissions/extract-answer", extract_answer_file, methods=["POST"])
router.add_api_route("/submissions/{id}/grade", regrade_submission, methods=["POST"])
router.add_api_route("/tasks", list_tasks, methods=["GET"])
router.add_api_route("/tasks/{task_id}", get_task, methods=["GET"])
router.add_api_route("/me/assessments", my_assessments, methods=["GET"])


# 5. GET /assessments/{id}
router.add_api_route("/assessments/{id}", get_assessment, methods=["GET"])


# 6. POST /roadmaps
router.add_api_route("/roadmaps", generate_roadmap_endpoint, methods=["POST"])
router.add_api_route("/me/roadmap", get_current_roadmap, methods=["GET"])
router.add_api_route("/me/roadmaps/history", get_roadmap_history, methods=["GET"])
router.add_api_route("/me/progress-history", progress_history, methods=["GET"])


# 7. PATCH /activities/{id}/progress
router.add_api_route("/activities/{id}/progress", update_activity_progress, methods=["PATCH"])


# 8. GET /me/history
router.add_api_route("/me/history", get_user_history, methods=["GET"])
router.add_api_route("/me/skill-history", get_skill_history, methods=["GET"])
router.add_api_route("/me/activity-log", get_activity_log, methods=["GET"])
router.add_api_route("/me/skill-progress", get_skill_progress, methods=["GET"])
router.add_api_route("/me/assessment-reliability", get_assessment_reliability, methods=["GET"])
router.add_api_route("/me/assessment-policy", get_assessment_policy, methods=["GET"])


# GDPR Endpoints
router.add_api_route("/me/export", export_user_data, methods=["GET"])
router.add_api_route("/me/data", delete_user_data, methods=["DELETE"], status_code=status.HTTP_200_OK)
