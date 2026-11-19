"""Question contributions: experts write, the system checks, an administrator approves (5.35)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend import contributions as service
from backend.auth import AuthenticatedUser, get_current_user, require_admin_user

router = APIRouter(tags=["Question contributions"])


class ContributionRequest(BaseModel):
    bank: Literal["EXAM", "TEST"] = "EXAM"
    skill_code: str = Field(min_length=2, max_length=40)
    level: int = Field(ge=1, le=3)
    payload: dict[str, Any]


class DecisionRequest(BaseModel):
    decision: Literal["APPROVE", "REQUEST_CHANGES", "REJECT"]
    note: str = Field(default="", max_length=2000)
    # Reviewer checklist (5.36): every point must be true to approve.
    checklist: dict[str, bool] = Field(default_factory=dict)


class RetireRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class GrantRequest(BaseModel):
    email: Optional[str] = Field(default=None, max_length=254)
    user_id: Optional[str] = Field(default=None, max_length=64)
    note: str = Field(default="", max_length=300)


@router.get("/contributions/meta")
def contribution_meta(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Kỹ năng, loại tiêu chí, bộ dữ liệu và số câu hiện có ở từng ô, để chuyên gia biết cần viết câu nào."""
    service.require_contributor(current_user)
    from backend.engine.exam_grader import BANK, TIER_LABELS
    from backend.engine.sql_sandbox import load_dataset
    from backend.store import store

    datasets = {}
    for variant, name in BANK["datasets"].items():
        columns, rows = load_dataset(name)
        datasets[variant] = {"file": name, "columns": columns, "rows": [[row.get(column, "") for column in columns] for row in rows[:12]], "total_rows": len(rows)}
    exam_skills = sorted({item["skill_code"] for item in BANK["items"]})
    return {
        "skills": [{"skill_code": skill["skill_code"], "skill_name": skill["skill_name"], "in_exam": skill["skill_code"] in exam_skills} for skill in store.skills],
        "levels": TIER_LABELS, "datasets": datasets, "coverage": service.coverage(),
        "case_types": {answer: sorted(kinds) for answer, kinds in service.TYPES_BY_ANSWER.items()}, "case_fields": service.CASE_FIELDS,
        "workspaces": {answer: sorted(kinds) for answer, kinds in service.WORKSPACES_BY_ANSWER.items()},
        "gate_types": service.GATE_FIELDS, "weak_limit": service.WEAK_LIMIT,
    }


@router.get("/contributions/mine")
def my_contributions(current_user: AuthenticatedUser = Depends(get_current_user)):
    service.require_contributor(current_user)
    return service.mine(current_user)


@router.post("/contributions", status_code=status.HTTP_201_CREATED)
def create_contribution(body: ContributionRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    return service.create(current_user, body.bank, body.skill_code, body.level, body.payload)


@router.get("/contributions/{contribution_id}")
def read_contribution(contribution_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    service.require_contributor(current_user)
    return {**service.view(service.owned(contribution_id, current_user)), "is_mine": True}


@router.put("/contributions/{contribution_id}")
def update_contribution(contribution_id: str, body: ContributionRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    return service.update(current_user, contribution_id, body.skill_code, body.level, body.payload)


@router.post("/contributions/{contribution_id}/check")
def check_contribution(contribution_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Chạy kiểm tra tự động: cấu trúc, SQL trên 4 bộ dữ liệu, đáp án mẫu đạt 100, bài sai dưới 40 điểm, trùng lặp."""
    return service.run_check(current_user, contribution_id)


@router.post("/contributions/{contribution_id}/submit")
def submit_contribution(contribution_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    return service.submit(current_user, contribution_id)


@router.post("/contributions/{contribution_id}/withdraw")
def withdraw_contribution(contribution_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    service.require_contributor(current_user)
    return service.withdraw(current_user, contribution_id)


@router.delete("/contributions/{contribution_id}")
def delete_contribution(contribution_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    service.require_contributor(current_user)
    service.delete(current_user, contribution_id)
    return {"deleted": contribution_id}


# --- Administrators ---

@router.get("/admin/contributors")
def admin_list_contributors(admin: AuthenticatedUser = Depends(require_admin_user)):
    return service.list_contributors()


@router.post("/admin/contributors", status_code=status.HTTP_201_CREATED)
def admin_grant_contributor(body: GrantRequest, admin: AuthenticatedUser = Depends(require_admin_user)):
    """Cấp quyền đóng góp câu hỏi cho một tài khoản (theo email hoặc mã tài khoản)."""
    from backend import accounts

    account = None
    if body.email:
        account = accounts.find_account_by_email(body.email.strip())
    elif body.user_id:
        account = accounts.get_account_profile(body.user_id.strip())
    if not account:
        if body.user_id and not body.email:
            # Accounts that sign in another way (the local demo tokens) still have an id.
            return service.grant(body.user_id.strip(), None, None, admin, body.note)
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản với thông tin này.")
    return service.grant(account["id"], account.get("email"), account.get("full_name"), admin, body.note)


@router.delete("/admin/contributors/{user_id}")
def admin_revoke_contributor(user_id: str, admin: AuthenticatedUser = Depends(require_admin_user)):
    """Thu hồi quyền. Câu đã xuất bản vẫn ở trong ngân hàng; bản nháp vẫn còn nhưng người đó không sửa hay gửi được nữa."""
    if not service.revoke(user_id):
        raise HTTPException(status_code=404, detail="Tài khoản này chưa có quyền đóng góp.")
    return {"revoked": user_id}


@router.get("/admin/contributions")
def admin_list_contributions(status_filter: Optional[Literal["SUBMITTED", "CHANGES_REQUESTED", "APPROVED", "REJECTED", "RETIRED"]] = Query(default=None, alias="status"),
                             admin: AuthenticatedUser = Depends(require_admin_user)):
    return service.queue(status_filter)


@router.get("/admin/contributions/{contribution_id}")
def admin_read_contribution(contribution_id: str, admin: AuthenticatedUser = Depends(require_admin_user)):
    row = service._row(contribution_id)
    if row["status"] == "DRAFT":
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi đóng góp.")
    return service.view(row, for_reviewer=True)


@router.post("/admin/contributions/{contribution_id}/decision")
def admin_decide(contribution_id: str, body: DecisionRequest, admin: AuthenticatedUser = Depends(require_admin_user)):
    """Duyệt: kiểm tra tự động chạy lại rồi mới xuất bản. Yêu cầu sửa hoặc từ chối cần ghi lý do."""
    return service.decide(admin, contribution_id, body.decision, body.note, body.checklist)


@router.post("/admin/contributions/{contribution_id}/retire")
def admin_retire(contribution_id: str, body: RetireRequest, admin: AuthenticatedUser = Depends(require_admin_user)):
    return service.retire(admin, contribution_id, body.note)
