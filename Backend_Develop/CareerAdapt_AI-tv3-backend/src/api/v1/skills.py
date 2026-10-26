"""F02: Skills Framework & Task Catalog Endpoints (TV3 / F02)."""
from fastapi import APIRouter
from schemas.models import CareerCatalogResponse, SkillRequirementItem, TaskCatalogItem
from services.store import store

router = APIRouter(prefix="/catalog", tags=["F02 - Career Catalog & Skills"])


@router.get("", response_model=CareerCatalogResponse)
def get_career_catalog():
    """Return the official published skill framework and task catalog for Data Analyst."""
    return CareerCatalogResponse(
        career_id=store.career_code,
        career_name="Data Analyst (Chuẩn bị thực tập)",
        version=store.version_tag,
        skills=list(store.skills.values()),
        tasks=list(store.tasks.values())
    )


@router.get("/skills", response_model=list[SkillRequirementItem])
def get_skill_framework():
    """List all skill requirements with weights, core indicators and O*NET/ESCO references."""
    return list(store.skills.values())


@router.get("/tasks", response_model=list[TaskCatalogItem])
def get_tasks_catalog():
    """List available evaluation tasks (DA01A, DA02A, DA03A)."""
    return list(store.tasks.values())
