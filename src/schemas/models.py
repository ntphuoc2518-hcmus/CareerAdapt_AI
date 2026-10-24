"""Pydantic v2 Models and Schemas for CareerAdapt AI API Contract (TV3).

Standardizes request/response contracts for F01 to F10.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, EmailStr


# ==========================================
# Common & Standard Error Schemas
# ==========================================
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class APIErrorResponse(BaseModel):
    error: ErrorDetail


# ==========================================
# Authentication & Identity
# ==========================================
class LoginRequest(BaseModel):
    email_or_token: str = Field(description="Email đăng nhập hoặc mã demo token")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str



# ==========================================
# F01: Hồ sơ và mục tiêu nghề nghiệp
# ==========================================
class SelfReportedSkillInput(BaseModel):
    skill_id: str
    claimed_level: int = Field(ge=0, le=3, description="Mức tự khai 0-3 (chỉ để tham khảo)")


class ProfileCreateRequest(BaseModel):
    target_career_id: str = "DATA_ANALYST"
    weekly_hours_budget: float = Field(default=10.0, gt=0, le=60, description="Số giờ học mỗi tuần")
    target_timeline_weeks: int = Field(default=8, ge=1, le=52, description="Thời hạn mục tiêu (tuần)")
    self_reported_skills: list[SelfReportedSkillInput] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    target_career_id: str
    weekly_hours_budget: float
    target_timeline_weeks: int
    self_reported_skills: list[dict]
    created_at: datetime
    updated_at: datetime


# ==========================================
# F02: Khung kỹ năng và Danh mục bài thử
# ==========================================
class SkillRequirementItem(BaseModel):
    skill_id: str
    skill_name: str
    category: str
    target_level: int
    weight: float
    is_core: bool
    source_reference: str


class TaskCatalogItem(BaseModel):
    task_id: str
    task_version_id: str
    title: str
    duration_minutes: int
    difficulty: str
    targeted_skills: list[str]
    description: str


class CareerCatalogResponse(BaseModel):
    career_id: str
    career_name: str
    version: str
    skills: list[SkillRequirementItem]
    tasks: list[TaskCatalogItem]


# ==========================================
# F03: Nộp bài thử & Upload
# ==========================================
class SubmissionCreateRequest(BaseModel):
    task_version_id: str
    submission_text: Optional[str] = None
    mode: str = Field(default="ASSESSMENT", description="PRACTICE hoặc ASSESSMENT")
    idempotency_key: Optional[str] = None


class SubmissionResponse(BaseModel):
    submission_id: uuid.UUID
    user_id: uuid.UUID
    task_version_id: str
    mode: str
    processing_status: str
    submitted_at: datetime
    file_metadata: Optional[dict] = None
    message: str


class SubmissionStatusResponse(BaseModel):
    submission_id: uuid.UUID
    processing_status: str
    submitted_at: datetime
    retry_count: int = 0
    assessment_id: Optional[uuid.UUID] = None


# ==========================================
# F04: Chấm & Phản hồi có bằng chứng
# ==========================================
class CriterionScoreItem(BaseModel):
    criterion_id: str
    criterion_name: str
    level: int = Field(ge=0, le=3)
    evidence_quote: str
    rationale: str
    has_valid_evidence: bool = True


class AssessmentResponse(BaseModel):
    assessment_id: uuid.UUID
    submission_id: uuid.UUID
    overall_level: int
    status: str  # ACCEPTED, NEEDS_REVIEW, RETRYABLE_ERROR
    scores: list[CriterionScoreItem]
    assessed_at: datetime
    model_version: str


# ==========================================
# F05: Gap / Coverage / Readiness
# ==========================================
class SkillGapItem(BaseModel):
    skill_id: str
    skill_name: str
    target_level: int
    evaluated_level: Optional[int]
    is_core: bool
    gap: int
    attainment: float
    priority: float
    status: str  # EVALUATED, UNEVALUATED


class EvaluationResponse(BaseModel):
    user_id: uuid.UUID
    coverage: float
    is_readiness_eligible: bool
    readiness_score: Optional[float]
    readiness_level: Optional[str]
    missing_core_skills: list[str]
    skills_analysis: list[SkillGapItem]


# ==========================================
# F06: Lập lịch Roadmap (DAG)
# ==========================================
class RoadmapActivityItem(BaseModel):
    activity_id: str
    title: str
    skill_id: str
    week_number: int
    allocated_hours: float
    prerequisites_met: list[str]
    status: str = "NOT_STARTED"


class UnscheduledActivityItem(BaseModel):
    activity_id: str
    title: str
    reason: str


class RoadmapGenerateRequest(BaseModel):
    weekly_hours_budget: Optional[float] = Field(default=None, gt=0, le=60, description="Tùy chọn ghi đè số giờ/tuần")
    target_timeline_weeks: Optional[int] = Field(default=None, ge=1, le=52, description="Tùy chọn ghi đè số tuần tối đa")


class RoadmapResponse(BaseModel):
    roadmap_version_id: uuid.UUID
    user_id: uuid.UUID
    total_weeks: int
    weekly_hours_budget: float
    total_hours: float
    schedule: list[RoadmapActivityItem]
    unscheduled: list[UnscheduledActivityItem]
    generated_at: datetime


# ==========================================
# F07: Theo dõi tiến độ
# ==========================================
class ProgressUpdateRequest(BaseModel):
    activity_id: str
    new_status: str = Field(description="NOT_STARTED, IN_PROGRESS, COMPLETED")
    hours_spent: float = 0.0


class ProgressRecordItem(BaseModel):
    activity_id: str
    status: str
    completed_at: Optional[datetime] = None
    hours_spent: float = 0.0


class ProgressResponse(BaseModel):
    user_id: uuid.UUID
    completed_count: int
    total_count: int
    percentage: float
    records: list[ProgressRecordItem]


class ProgressHistoryItem(BaseModel):
    activity_id: str
    previous_status: Optional[str] = None
    new_status: str
    hours_spent: float = 0.0
    timestamp: datetime


class ProgressHistoryResponse(BaseModel):
    user_id: uuid.UUID
    total_events: int
    history: list[ProgressHistoryItem]



# ==========================================
# F08: Đánh giá lại & So sánh
# ==========================================
class AssessmentComparisonItem(BaseModel):
    criterion_id: str
    criterion_name: str
    previous_level: int
    current_level: int
    delta: int


class ReassessmentCompareResponse(BaseModel):
    task_id: str
    is_comparable: bool
    reason: Optional[str] = None
    previous_assessment_id: uuid.UUID
    current_assessment_id: uuid.UUID
    comparison: list[AssessmentComparisonItem]


# ==========================================
# F09: Quản trị nội dung
# ==========================================
class ContentPublishRequest(BaseModel):
    content_type: str  # SKILL, TASK, ACTIVITY, RUBRIC
    content_id: str
    version: str
    comment: Optional[str] = None


class ContentPublishResponse(BaseModel):
    content_type: str
    content_id: str
    version: str
    status: str  # DRAFT, APPROVED, PUBLISHED
    published_by: str
    published_at: datetime


# ==========================================
# F10: Nhắc nhở trong ứng dụng
# ==========================================
class ReminderCreateRequest(BaseModel):
    reminder_type: str = Field(default="ACTIVITY_DUE", description="INACTIVITY, ACTIVITY_DUE, MILESTONE")
    message: str
    target_id: Optional[str] = None


class ReminderItem(BaseModel):
    reminder_id: uuid.UUID
    reminder_type: str
    message: str
    target_id: Optional[str]
    is_read: bool
    created_at: datetime


class ReminderListResponse(BaseModel):
    unread_count: int
    reminders: list[ReminderItem]
