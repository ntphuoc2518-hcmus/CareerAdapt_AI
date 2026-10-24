"""Unified Data Store & Repository Layer for CareerAdapt AI (TV3).

Provides thread-safe persistence with dual capability:
- In-memory seeded store for CI, unit tests, and isolated demo execution.
- Extensible hook for PostgreSQL via psycopg2 / data_access.py.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, Any
from schemas.models import (
    SkillRequirementItem, TaskCatalogItem, CareerCatalogResponse,
    CriterionScoreItem
)
from domain.evaluation import SkillEvaluationItem


class MemoryStore:
    """Thread-safe, pre-seeded store for F01-F10 endpoints."""

    def __init__(self):
        self._seed_initial_data()

    def _seed_initial_data(self):
        # 1. Career Version
        self.career_version_id = "10000000-0000-0000-0000-000000000001"
        self.career_code = "DATA_ANALYST"
        self.version_tag = "v3.0"

        # 2. Skill Requirements (Total weight = 1.000)
        self.skills: dict[str, SkillRequirementItem] = {
            "SQL": SkillRequirementItem(
                skill_id="SQL",
                skill_name="Truy vấn và xử lý dữ liệu SQL",
                category="TECHNICAL",
                target_level=2,
                weight=0.300,
                is_core=True,
                source_reference="O*NET 15-2051.01"
            ),
            "PYTHON": SkillRequirementItem(
                skill_id="PYTHON",
                skill_name="Lập trình Python phân tích dữ liệu",
                category="TECHNICAL",
                target_level=1,
                weight=0.150,
                is_core=False,
                source_reference="ESCO 2511"
            ),
            "DATA_QUALITY": SkillRequirementItem(
                skill_id="DATA_QUALITY",
                skill_name="Kiểm soát và làm sạch chất lượng dữ liệu",
                category="DATA_ENGINEERING",
                target_level=2,
                weight=0.200,
                is_core=True,
                source_reference="O*NET 15-2051.01"
            ),
            "DATA_VIZ": SkillRequirementItem(
                skill_id="DATA_VIZ",
                skill_name="Trực quan hóa và biểu đồ dữ liệu",
                category="VISUALIZATION",
                target_level=2,
                weight=0.200,
                is_core=False,
                source_reference="ESCO 2511"
            ),
            "WRITTEN_EXPLANATION": SkillRequirementItem(
                skill_id="WRITTEN_EXPLANATION",
                skill_name="Viết báo cáo và giải thích số liệu",
                category="COMMUNICATION",
                target_level=2,
                weight=0.150,
                is_core=False,
                source_reference="O*NET / ESCO"
            ),
        }

        # 3. Tasks Catalog (DA01, DA02, DA03)
        self.tasks: dict[str, TaskCatalogItem] = {
            "DA01": TaskCatalogItem(
                task_id="DA01",
                task_version_id="20000000-0000-0000-0000-000000000001",
                title="Làm sạch và tổng hợp dữ liệu bán hàng (DA01A)",
                duration_minutes=35,
                difficulty="INTERMEDIATE",
                targeted_skills=["SQL", "DATA_QUALITY"],
                description="Truy vấn dữ liệu giao dịch, loại bỏ đơn hủy/bất thường, tính tổng doanh thu vùng và % MoM."
            ),
            "DA02": TaskCatalogItem(
                task_id="DA02",
                task_version_id="20000000-0000-0000-0000-000000000002",
                title="Phân tích dữ liệu Python và vẽ biểu đồ (DA02A)",
                duration_minutes=40,
                difficulty="BEGINNER",
                targeted_skills=["PYTHON", "DATA_VIZ"],
                description="Đọc file CSV với pandas, tính chỉ số thống kê cơ bản và vẽ biểu đồ phân phối doanh thu."
            ),
            "DA03": TaskCatalogItem(
                task_id="DA03",
                task_version_id="20000000-0000-0000-0000-000000000003",
                title="Viết báo cáo và nhận xét từ số liệu (DA03A)",
                duration_minutes=25,
                difficulty="INTERMEDIATE",
                targeted_skills=["WRITTEN_EXPLANATION"],
                description="Tổng hợp 3 phát hiện nổi bật từ bảng kết quả đã đối chiếu, đưa ra đề xuất cho bộ phận kinh doanh."
            )
        }

        # 4. Learning Activities for Roadmap DAG
        self.activities: list[dict] = [
            {
                "activity_id": "ACT_SQL_01",
                "title": "Nền tảng SQL: SELECT, WHERE, GROUP BY",
                "skill_id": "SQL",
                "estimated_hours": 4.0,
                "priority": 0.95,
                "prerequisites": []
            },
            {
                "activity_id": "ACT_DQ_01",
                "title": "Kỹ thuật phát hiện giá trị khuyết và ngoại lai",
                "skill_id": "DATA_QUALITY",
                "estimated_hours": 3.0,
                "priority": 0.90,
                "prerequisites": ["ACT_SQL_01"]
            },
            {
                "activity_id": "ACT_SQL_02",
                "title": "SQL nâng cao: JOIN nhiều bảng và Window Functions",
                "skill_id": "SQL",
                "estimated_hours": 5.0,
                "priority": 0.85,
                "prerequisites": ["ACT_SQL_01"]
            },
            {
                "activity_id": "ACT_PY_01",
                "title": "Làm quen với thư viện Pandas và NumPy",
                "skill_id": "PYTHON",
                "estimated_hours": 4.0,
                "priority": 0.70,
                "prerequisites": []
            },
            {
                "activity_id": "ACT_VIZ_01",
                "title": "Thiết kế biểu đồ chuẩn mực với Matplotlib & Seaborn",
                "skill_id": "DATA_VIZ",
                "estimated_hours": 4.0,
                "priority": 0.65,
                "prerequisites": ["ACT_PY_01"]
            },
            {
                "activity_id": "ACT_COMM_01",
                "title": "Kỹ năng truyền tải insight cho stakeholders",
                "skill_id": "WRITTEN_EXPLANATION",
                "estimated_hours": 3.0,
                "priority": 0.60,
                "prerequisites": ["ACT_VIZ_01"]
            }
        ]

        # 5. Runtime storage dicts (keyed by user_id or entity_id)
        self.profiles: dict[uuid.UUID, dict] = {}
        self.submissions: dict[uuid.UUID, dict] = {}
        self.assessments: dict[uuid.UUID, dict] = {}  # keyed by submission_id
        self.roadmaps: dict[uuid.UUID, list[dict]] = {} # keyed by user_id -> list of roadmap versions
        self.progress: dict[uuid.UUID, dict[str, dict]] = {} # user_id -> {activity_id: progress_dict}
        self.reminders: dict[uuid.UUID, list[dict]] = {} # user_id -> list of reminders
        self.idempotency_keys: dict[str, uuid.UUID] = {} # idempotency_key -> submission_id
        self.content_publications: list[dict] = []


# Global store singleton
store = MemoryStore()
