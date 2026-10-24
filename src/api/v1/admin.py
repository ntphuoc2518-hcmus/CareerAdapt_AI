"""F09: Content Governance & Versioning Endpoints (TV3 / F09)."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, require_admin_user
from schemas.models import ContentPublishRequest, ContentPublishResponse
from services.store import store

router = APIRouter(prefix="/admin", tags=["F09 - Content Admin"])


@router.post("/content/publish", response_model=ContentPublishResponse)
def publish_content(
    body: ContentPublishRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user)
):
    """Publish a versioned content item (Skill, Task, Activity, Rubric).
    
    Principle: Content published and in active use cannot be overwritten directly.
    """
    now = datetime.now(timezone.utc)

    # Check for existing publication with same ID and version
    for pub in store.content_publications:
        if pub["content_type"] == body.content_type and pub["content_id"] == body.content_id and pub["version"] == body.version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Phiên bản '{body.version}' của nội dung '{body.content_id}' đã được phát hành trước đó, không được ghi đè trực tiếp."
            )

    pub_record = {
        "content_type": body.content_type,
        "content_id": body.content_id,
        "version": body.version,
        "status": "PUBLISHED",
        "published_by": admin_user.email,
        "published_at": now,
        "comment": body.comment
    }
    store.content_publications.append(pub_record)

    return ContentPublishResponse(
        content_type=body.content_type,
        content_id=body.content_id,
        version=body.version,
        status="PUBLISHED",
        published_by=admin_user.email,
        published_at=now
    )


@router.get("/content/publications", response_model=list[ContentPublishResponse])
def list_content_publications(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """List all officially published content versions."""
    return [ContentPublishResponse(**p) for p in store.content_publications]
