"""AI Tool Registry: the complete list of what a model may ask the backend to do.

All tools are read-only. A model can only pick a name from this list and fill the declared
arguments; there is no tool that writes, runs SQL or takes an account id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from backend.ai_service import career_context as ctx
from backend.ai_service.career_context import ToolContext
from backend.ai_service.gateway import check_schema
from backend.ai_service.security import scrub_identity

logger = logging.getLogger("careeradapt.ai")
NO_ARGUMENTS = {"type": "object", "properties": {}, "additionalProperties": False}
SKILL_CODES = ["SQL", "DATA_QUALITY", "PYTHON", "DATA_VIZ", "WRITTEN_COMM", "STATISTICS"]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Callable[..., dict]
    parameters: dict


TOOLS = {tool.name: tool for tool in (
    Tool("get_my_profile", "Ngành học, quỹ giờ, thời hạn, bước quy trình và kỹ năng tự khai (không phải bằng chứng) của người dùng hiện tại.", ctx.get_my_profile, NO_ARGUMENTS),
    Tool("get_my_current_jd", "JD và mục tiêu đang dùng: yêu cầu kỹ năng, mức, trọng số, yêu cầu chưa có bài đo.", ctx.get_my_current_jd, NO_ARGUMENTS),
    Tool("get_my_assessment_summary", "Kết quả bài kiểm tra đã chấm: điểm, trình độ xác thực, kết quả từng câu và kỹ năng.", ctx.get_my_assessment_summary, NO_ARGUMENTS),
    Tool("get_my_verified_skills", "Các kỹ năng đã được xác thực bằng bài đánh giá.", ctx.get_my_verified_skills, NO_ARGUMENTS),
    Tool("get_my_skill_gap", "Skill Gap, Coverage và Readiness do hệ thống tính.", ctx.get_my_skill_gap, NO_ARGUMENTS),
    Tool("get_my_roadmap", "Lộ trình theo tuần, tổng giờ, việc tiếp theo.", ctx.get_my_roadmap, NO_ARGUMENTS),
    Tool("get_my_learning_progress", "Tiến độ học phần, lịch ôn và mini-test.", ctx.get_my_learning_progress, NO_ARGUMENTS),
    Tool("search_approved_learning_resources", "Tìm học liệu đã duyệt theo từ khóa hoặc kỹ năng.", ctx.search_approved_learning_resources, {
        "type": "object", "properties": {"query": {"type": "string", "maxLength": 200}, "skill_code": {"type": "string", "enum": SKILL_CODES}}, "additionalProperties": False}),
    Tool("get_my_career_journey_summary", "Tóm tắt toàn bộ hành trình Career Adapt của người dùng hiện tại.", ctx.get_my_career_journey_summary, NO_ARGUMENTS),
)}


def declarations() -> list[dict]:
    return [{"name": tool.name, "description": tool.description, "parameters": tool.parameters} for tool in TOOLS.values()]


def _scrub(value: Any, identifiers: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return scrub_identity(value, *identifiers)
    if isinstance(value, list):
        return [_scrub(item, identifiers) for item in value]
    if isinstance(value, dict):
        return {key: _scrub(item, identifiers) for key, item in value.items()}
    return value


def execute(name: str, arguments: Any, context: ToolContext, identifiers: tuple[str, ...] = ()) -> dict:
    """Run one call. A bad call becomes an error result, so the model can recover and nothing runs."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"data": {"error": "UNKNOWN_TOOL"}}
    problem = check_schema(arguments if arguments is not None else {}, tool.parameters)
    if problem:
        return {"data": {"error": "INVALID_ARGUMENTS"}}
    try:
        result = tool.handler(context, **(arguments or {}))
    except Exception:
        logger.exception("Tool %s failed", name)
        return {"data": {"error": "TOOL_FAILED"}}
    return {"data": _scrub(result["data"], identifiers), "card": result.get("card")}
