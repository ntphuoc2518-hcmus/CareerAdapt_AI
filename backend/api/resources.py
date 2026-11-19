"""Approved learning resource catalog (F19) and its administration."""
from __future__ import annotations

from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.auth import AuthenticatedUser, get_current_user, require_admin_user
from backend.catalog import get_resource, list_resources, save_resource_version, update_resource_state
from backend.clock import utcnow
from backend.engine.link_checker import check_url
from backend.store import store

router = APIRouter(tags=["F19 - Learning Resources"])
admin_router = APIRouter(prefix="/admin", tags=["F19 - Learning Resources Admin"])

LINK_CHECK_INTERVAL_DAYS = 30


@router.get("/learning-resources")
def learner_resources(
    skill_id: Optional[str] = Query(default=None),
    level: Optional[int] = Query(default=None, ge=1, le=3),
    provider: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Chỉ trả học liệu đã duyệt, đã kiểm tra link và không bị tạm ẩn."""
    items = list_resources(store.db, approved_only=True)
    if skill_id:
        items = [item for item in items if skill_id in item.get("skill_ids", [])]
    if level:
        items = [item for item in items if int(item.get("level", 1)) == level]
    if provider:
        items = [item for item in items if item.get("provider") == provider]
    if language:
        items = [item for item in items if item.get("language") == language]
    if q:
        needle = q.casefold()
        items = [item for item in items if needle in f"{item.get('title')} {item.get('provider')} {item.get('learning_outcome')}".casefold()]
    every = list_resources(store.db, approved_only=True)
    return {
        "items": items, "total": len(items),
        "filters": {"providers": sorted({item["provider"] for item in every}), "languages": sorted({item["language"] for item in every}), "skills": sorted({code for item in every for code in item.get("skill_ids", [])})},
    }


class ResourceRequest(BaseModel):
    resource_id: Optional[str] = Field(default=None, max_length=60)
    title: str = Field(min_length=3, max_length=200)
    provider: str = Field(min_length=2, max_length=120)
    resource_type: Literal["COURSE", "LECTURE", "EXERCISE", "OFFICIAL_DOC", "ARTICLE", "INTERNAL_GUIDE"]
    url: str = Field(min_length=8, max_length=500)
    language: str = Field(default="en", max_length=10)
    cost_access: str = Field(default="", max_length=120)
    skill_ids: list[str] = Field(min_length=1, max_length=5)
    level: int = Field(default=1, ge=1, le=3)
    prerequisites: list[str] = Field(default_factory=list, max_length=10)
    estimated_minutes: int = Field(gt=0, le=20000)
    learning_outcome: str = Field(min_length=5, max_length=400)
    source_note: str = Field(default="", max_length=600)


def _validate(body: ResourceRequest) -> None:
    if not body.url.lower().startswith(("https://", "http://", "/guides/")):
        raise HTTPException(status_code=422, detail="URL học liệu phải bắt đầu bằng http:// hoặc https://.")
    unknown = set(body.skill_ids) - {skill["skill_code"] for skill in store.skills}
    if unknown:
        raise HTTPException(status_code=422, detail=f"Kỹ năng không có trong danh mục: {', '.join(sorted(unknown))}.")


@admin_router.get("/resources")
def admin_resources(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    return list_resources(store.db, approved_only=False)


@admin_router.post("/resources", status_code=status.HTTP_201_CREATED)
def admin_create_resource(body: ResourceRequest, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Tài nguyên mới luôn bắt đầu ở trạng thái nháp, chưa kiểm tra link."""
    _validate(body)
    import uuid
    resource_id = (body.resource_id or f"RES_{uuid.uuid4().hex[:8].upper()}").strip().upper()
    if get_resource(store.db, resource_id):
        raise HTTPException(status_code=409, detail="Mã học liệu đã tồn tại.")
    return save_resource_version(store.db, {**body.model_dump(), "resource_id": resource_id, "status": "DRAFT", "link_status": "UNCHECKED", "duration_source": "Ước tính của nhóm"})


@admin_router.put("/resources/{resource_id}")
def admin_update_resource(resource_id: str, body: ResourceRequest, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Sửa nội dung tạo phiên bản mới, về nháp và phải kiểm tra lại; roadmap cũ vẫn giữ bản đã dùng."""
    _validate(body)
    if not get_resource(store.db, resource_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy học liệu.")
    return save_resource_version(store.db, {**body.model_dump(), "resource_id": resource_id, "status": "DRAFT", "link_status": "UNCHECKED", "duration_source": "Ước tính của nhóm"})


def run_link_check(resource: dict) -> dict:
    """Update a resource from a real check. A dead link is hidden automatically, history stays."""
    result = check_url(resource["url"])
    now = utcnow()
    fields = {"link_status": result["link_status"], "last_checked_at": now.isoformat(), "next_review_at": (now + timedelta(days=LINK_CHECK_INTERVAL_DAYS)).isoformat()}
    if result["link_status"] == "BROKEN" and resource["status"] == "APPROVED":
        fields["status"] = "HIDDEN"
    return {**result, "resource": update_resource_state(store.db, resource["resource_id"], **fields)}


@admin_router.post("/resources/{resource_id}/check-link")
def admin_check_link(resource_id: str, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    resource = get_resource(store.db, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Không tìm thấy học liệu.")
    return run_link_check(resource)


@admin_router.post("/resources/{resource_id}/review")
def admin_review_resource(resource_id: str, decision: Literal["APPROVED", "HIDDEN", "DRAFT"] = Query(...), admin_user: AuthenticatedUser = Depends(require_admin_user)):
    resource = get_resource(store.db, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Không tìm thấy học liệu.")
    if decision == "APPROVED" and (resource["link_status"] not in {"OK", "UNKNOWN"} or not resource.get("last_checked_at")):
        raise HTTPException(status_code=409, detail="Hãy kiểm tra link thành công trước khi duyệt học liệu.")
    return update_resource_state(store.db, resource_id, status=decision, reviewer_id=admin_user.email)
