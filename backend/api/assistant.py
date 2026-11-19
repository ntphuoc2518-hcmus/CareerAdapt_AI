"""CareerAdapt AI Assistant API. Mounted only under /api/v1, so the CSRF middleware always applies."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from backend import i18n
from backend.ai_service import assistant, gateway, guardrails, knowledge, task_engine
from backend.auth import AuthenticatedUser, get_current_user, require_admin_user
from backend.store import store

router = APIRouter(prefix="/assistant", tags=["Trợ lý CareerAdapt AI"])
i18n_router = APIRouter(tags=["Ngôn ngữ"])


@i18n_router.get("/i18n/private-catalog")
def private_catalog(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Bản dịch đề thi cho trang quản trị. Không phục vụ học viên vì chứa nội dung đề."""
    return i18n.catalog()


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    page: str = Field(default="other", max_length=40)


class TaskBody(BaseModel):
    conversation_id: Optional[str] = Field(default=None, max_length=40)


class DocumentBody(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=200000)
    source_url: Optional[str] = Field(default=None, max_length=500)


class DecisionBody(BaseModel):
    status: Literal["APPROVED", "REJECTED", "RETIRED"]


@router.get("/status")
def assistant_status(current_user: AuthenticatedUser = Depends(get_current_user)):
    return {**assistant.status_view(current_user), "tasks": task_engine.catalog()}


@router.get("/conversations")
def list_conversations(current_user: AuthenticatedUser = Depends(get_current_user)):
    return assistant.list_conversations(current_user.user_id)


@router.post("/conversations", status_code=201)
def create_conversation(current_user: AuthenticatedUser = Depends(get_current_user)):
    return assistant.public_conversation(assistant.create_conversation(current_user.user_id))


@router.get("/conversations/{conversation_id}")
def read_conversation(conversation_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    return assistant.messages_of(current_user.user_id, conversation_id)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    assistant.delete_conversation(current_user.user_id, conversation_id)
    return {"message": "Đã xóa hội thoại."}


@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, body: MessageBody, current_user: AuthenticatedUser = Depends(get_current_user)):
    return assistant.send(current_user, conversation_id, body.content.strip(), body.page)


@router.post("/conversations/{conversation_id}/messages/image")
async def send_message_with_image(conversation_id: str, content: str = Form(min_length=1, max_length=4000), page: str = Form(default="other", max_length=40),
                                  image: UploadFile = File(...), current_user: AuthenticatedUser = Depends(get_current_user)):
    """Câu hỏi kèm một ảnh. Ảnh được kiểm tra, làm sạch và chỉ gửi cho dịch vụ AI; máy chủ không lưu ảnh."""
    from backend.avatar import CHAT_IMAGE_MAX_BYTES, AvatarError, process_chat_image

    data = await image.read(CHAT_IMAGE_MAX_BYTES + 1)
    try:
        picture = process_chat_image(data)
    except AvatarError as error:
        raise HTTPException(status_code=413 if len(data) > CHAT_IMAGE_MAX_BYTES else 422, detail=str(error)) from None
    return assistant.send(current_user, conversation_id, content.strip(), page, picture)


@router.post("/tasks/{task}")
def run_task(task: str, body: TaskBody = TaskBody(), current_user: AuthenticatedUser = Depends(get_current_user)):
    """Giải thích kết quả do backend tính. AI lỗi thì trả về giải thích theo quy tắc."""
    return task_engine.run(current_user, task, body.conversation_id)


@router.get("/knowledge/search")
def search_knowledge(q: str = Query(min_length=2, max_length=300), current_user: AuthenticatedUser = Depends(get_current_user)):
    guardrails.require_open(current_user.user_id)
    return [assistant.citation_view(source) for source in knowledge.retrieve(store.db, q, user_id=current_user.user_id)]


@router.get("/admin/knowledge")
def admin_documents(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    return knowledge.list_documents(store.db)


@router.post("/admin/knowledge", status_code=201)
def admin_add_document(body: DocumentBody, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    """Tài liệu mới luôn ở trạng thái nháp, chỉ truy xuất được sau khi duyệt."""
    try:
        return knowledge.add_uploaded_document(store.db, body.title.strip(), body.body, str(admin_user.user_id), body.source_url)
    except knowledge.KnowledgeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.post("/admin/knowledge/{document_id}/decision")
def admin_decide(document_id: str, body: DecisionBody, admin_user: AuthenticatedUser = Depends(require_admin_user)):
    try:
        result = knowledge.decide(store.db, document_id, body.status, str(admin_user.user_id))
    except knowledge.KnowledgeError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    return result


@router.post("/admin/knowledge/embed")
def admin_embed(admin_user: AuthenticatedUser = Depends(require_admin_user)):
    if not gateway.is_available():
        raise HTTPException(status_code=409, detail="Chưa cấu hình dịch vụ AI nên chưa tạo được vector. Tìm kiếm từ khóa vẫn hoạt động.")
    try:
        return {"embedded": knowledge.embed_pending(store.db, limit=500)}
    except gateway.GatewayError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None


@router.get("/admin/usage")
def admin_usage(days: int = Query(default=7, ge=1, le=90), admin_user: AuthenticatedUser = Depends(require_admin_user)):
    return guardrails.usage_report(days)
