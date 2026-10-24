"""Assessment Orchestrator & Evaluation Pipeline (TV3 / F04).

Coordinates deterministic checks, evidence verification, and AI adapter scoring.
Implements the fail-safe state machine: ACCEPTED, NEEDS_REVIEW, RETRYABLE_ERROR.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from schemas.models import CriterionScoreItem, AssessmentResponse
from security_utils import verify_evidence_quote, redact_pii


class AssessmentOrchestrator:
    """Orchestrates submission evaluation with strict evidence validation."""

    def __init__(self, model_version: str = "mock-llm-rubric-v3.0"):
        self.model_version = model_version

    def evaluate_submission(
        self,
        submission_id: uuid.UUID,
        task_id: str,
        submission_text: str,
        simulate_timeout: bool = False
    ) -> AssessmentResponse:
        """Run the end-to-end evaluation pipeline."""
        now = datetime.now(timezone.utc)

        # 1. Check for timeout / network failure simulation (Fail-safe rule)
        if simulate_timeout:
            return AssessmentResponse(
                assessment_id=uuid.uuid4(),
                submission_id=submission_id,
                overall_level=0,
                status="RETRYABLE_ERROR",
                scores=[],
                assessed_at=now,
                model_version=self.model_version
            )

        # 2. PII Redaction before AI processing
        safe_text = redact_pii(submission_text)

        # 3. Generate candidate assessment criteria based on task
        candidate_scores: list[dict] = []
        
        if "DA01" in task_id:
            # DA01: SQL & Data Quality
            has_sql_evidence = "select" in safe_text.lower() or "group by" in safe_text.lower() or "where" in safe_text.lower()
            has_dq_evidence = "null" in safe_text.lower() or "clean" in safe_text.lower() or "filter" in safe_text.lower()

            sql_quote = "SELECT" if "select" in safe_text.lower() else ""
            dq_quote = "WHERE" if "where" in safe_text.lower() else ""

            candidate_scores = [
                {
                    "criterion_id": "CRIT_SQL_SYNTAX",
                    "criterion_name": "Cú pháp và logic truy vấn SQL",
                    "level": 2 if has_sql_evidence else 1,
                    "evidence_quote": sql_quote if sql_quote else "Không tìm thấy truy vấn SQL đầy đủ",
                    "rationale": "Thí sinh sử dụng đúng các mệnh đề SQL cơ bản." if has_sql_evidence else "Chưa thấy câu lệnh lọc và nhóm đầy đủ."
                },
                {
                    "criterion_id": "CRIT_DATA_CLEANING",
                    "criterion_name": "Lọc và xử lý chất lượng dữ liệu",
                    "level": 2 if has_dq_evidence else 0,
                    "evidence_quote": dq_quote if dq_quote else "Chưa có bằng chứng lọc dòng",
                    "rationale": "Có mệnh đề lọc bỏ bản ghi không hợp lệ." if has_dq_evidence else "Chưa loại bỏ dữ liệu bất thường."
                }
            ]
        elif "DA02" in task_id:
            # DA02: Python & Data Viz
            has_py = "import pandas" in safe_text.lower() or "pd." in safe_text.lower() or "df" in safe_text.lower()
            has_viz = "plot" in safe_text.lower() or "plt." in safe_text.lower() or "chart" in safe_text.lower()

            candidate_scores = [
                {
                    "criterion_id": "CRIT_PY_PANDAS",
                    "criterion_name": "Thao tác dữ liệu với Python Pandas",
                    "level": 2 if has_py else 1,
                    "evidence_quote": "pandas" if "pandas" in safe_text.lower() else "",
                    "rationale": "Đọc và xử lý cấu trúc bảng dữ liệu hợp lệ."
                },
                {
                    "criterion_id": "CRIT_VIZ_QUALITY",
                    "criterion_name": "Tính trực quan và đầy đủ nhãn biểu đồ",
                    "level": 2 if has_viz else 1,
                    "evidence_quote": "plot" if "plot" in safe_text.lower() else "",
                    "rationale": "Biểu đồ có nhãn trục và tiêu đề rõ ràng."
                }
            ]
        else:
            # DA03: Written explanation / Reporting
            candidate_scores = [
                {
                    "criterion_id": "CRIT_REPORT_INSIGHT",
                    "criterion_name": "Trích dẫn số liệu và đúc kết insight",
                    "level": 2,
                    "evidence_quote": safe_text[:30].strip() if len(safe_text) >= 30 else safe_text.strip(),
                    "rationale": "Báo cáo có trích dẫn số liệu đối chiếu và kết luận kinh doanh."
                }
            ]

        # 4. Strict evidence validation using verify_evidence_quote
        verified_scores: list[CriterionScoreItem] = []
        needs_review = False

        for c in candidate_scores:
            quote = c["evidence_quote"]
            is_valid_evidence = False
            
            if quote:
                # Must match exact substring in submission
                is_valid_evidence = verify_evidence_quote(submission_text, quote)
            
            if not is_valid_evidence:
                needs_review = True

            verified_scores.append(CriterionScoreItem(
                criterion_id=c["criterion_id"],
                criterion_name=c["criterion_name"],
                level=c["level"],
                evidence_quote=quote if is_valid_evidence else "[BẰNG CHỨNG KHÔNG HỢP LỆ HOẶC KHÔNG TỒN TẠI]",
                rationale=c["rationale"],
                has_valid_evidence=is_valid_evidence
            ))

        # Overall level: average of criteria
        levels = [s.level for s in verified_scores]
        overall_level = round(sum(levels) / len(levels)) if levels else 0

        final_status = "NEEDS_REVIEW" if needs_review else "ACCEPTED"

        return AssessmentResponse(
            assessment_id=uuid.uuid4(),
            submission_id=submission_id,
            overall_level=overall_level,
            status=final_status,
            scores=verified_scores,
            assessed_at=now,
            model_version=self.model_version
        )


orchestrator = AssessmentOrchestrator()
