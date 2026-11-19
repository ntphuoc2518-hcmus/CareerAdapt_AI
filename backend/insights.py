"""What surrounds an exam result: how the levels are defined, where the learner ranks, what the market pays
and which sources the result rests on. Everything is read from stored results and reviewed reference data."""
from __future__ import annotations

import json
import math
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Optional

from backend import accounts, catalog
from backend.avatar import thumbnail_data_uri
from backend.clock import utcnow
from backend.database import dumps
from backend.engine.exam_grader import BANK_VERSION, PASS_THRESHOLD
from backend.levels import LEVELS, MAX_LEVEL
from backend.store import store
from backend.targeting import resolve_target

SALARY_FILE = Path(__file__).resolve().parents[1] / "data" / "salary_reference_v1.json"
SALARY_KEY = "salary_reference"
VISIBLE_FIELD = "show_on_leaderboard"
# Below this many ranked learners a "top N%" says nothing, so only the position is shown.
MIN_COHORT = 5
BOARD_SIZE = 10
ANONYMOUS = "Học viên ẩn danh"


def salary_reference() -> Optional[dict]:
    """The administrator's version if one was saved, otherwise the reviewed file. None when neither has figures."""
    row = store.db.one("SELECT payload FROM content_state WHERE key = ?", (SALARY_KEY,))
    data = json.loads(row["payload"]) if row else json.loads(SALARY_FILE.read_text(encoding="utf-8"))
    bands = [band for band in data.get("bands", []) if band.get("value")]
    if not bands or not (data.get("source") or {}).get("url"):
        return None
    low, high = bands[0]["value"], bands[-1]["value"]
    growth = round((high - low) / low * 100) if len(bands) > 1 and low > 0 and high > low else None
    return {**data, "bands": bands, "growth_percent": growth}


def save_salary_reference(data: dict) -> dict:
    store.db.execute(
        "INSERT INTO content_state(key, payload, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
        (SALARY_KEY, dumps(data), utcnow().isoformat()),
    )
    return salary_reference() or data


def level_guide() -> dict:
    skills = [{"skill_code": skill["skill_code"], "skill_name": skill["skill_name"], "levels": skill.get("rubric_summary", {})} for skill in store.skills]
    return {"scale": list(LEVELS), "skills": skills}


BASES = ("exam", "current")


def framework_skills() -> list[str]:
    """The career's weighted skills: the same set for every learner, so current levels compare fairly."""
    return [skill["skill_code"] for skill in store.skills if float(skill.get("weight", 0)) > 0]


def _population(career_code: str) -> list[dict]:
    """Everyone with a graded Career Adapt exam of this career: their latest exam and their levels now."""
    rows = store.db.query(
        "SELECT a.user_id, a.submitted_at, f.final_score, f.final_level, f.payload FROM exam_attempts a "
        "JOIN career_runs r ON r.run_id = a.run_id JOIN final_assessments f ON f.submission_id = a.submission_id "
        "WHERE a.status = 'GRADED' AND r.career_code = ? ORDER BY a.submitted_at DESC", (career_code,))
    skills = framework_skills()
    found: dict[str, dict] = {}
    for row in rows:
        if row["user_id"] in found:
            continue
        per_skill = json.loads(row["payload"]).get("per_skill_results", {})
        assessed = (store.profiles.get(uuid.UUID(row["user_id"])) or {}).get("assessed_skills") or {}
        found[row["user_id"]] = {
            "user_id": row["user_id"], "score": round(float(row["final_score"] or 0), 1), "exam_overall": int(row["final_level"] or 0),
            "exam_levels": {code: int(item.get("level", 0)) for code, item in per_skill.items()},
            # Verified levels now: the exam, passed lesson checks and the final assessment. A skill never measured counts as 0.
            "current_levels": {code: int((assessed.get(code) or {}).get("level") or 0) for code in skills},
        }
    return list(found.values())


def _ranked(population: list[dict], basis: str, skill: Optional[str]) -> list[dict]:
    entries = []
    for person in population:
        levels = person["exam_levels"] if basis == "exam" else person["current_levels"]
        if skill:
            points, maximum = int(levels.get(skill, 0)), MAX_LEVEL
        else:
            points, maximum = sum(levels.values()), MAX_LEVEL * len(levels)
        overall = person["exam_overall"] if basis == "exam" else (points // max(len(levels), 1) if not skill else points)
        entries.append({**person, "level_points": points, "max_points": maximum, "overall_level": min(int(overall), MAX_LEVEL), "levels": levels})
    entries.sort(key=lambda item: (-item["level_points"], -item["score"]))
    for entry in entries:
        entry["rank"] = 1 + sum(1 for other in entries if (other["level_points"], other["score"]) > (entry["level_points"], entry["score"]))
    return entries


@lru_cache(maxsize=512)
def _thumbnail(user_id: str, version: int) -> Optional[str]:
    """Cached per picture version, so a changed picture is never served from the cache."""
    stored = accounts.get_avatar(user_id)
    return thumbnail_data_uri(stored[0]) if stored else None


def _shown_avatar(user_id: str, is_me: bool) -> Optional[str]:
    """The learner's own picture always; someone else's only if they chose to show their name on the board."""
    if not is_me and not (store.profiles.get(uuid.UUID(user_id)) or {}).get(VISIBLE_FIELD):
        return None
    version = accounts.avatar_version(user_id)
    return _thumbnail(user_id, version) if version else None


def _shown_name(user_id: str) -> str:
    profile = store.profiles.get(uuid.UUID(user_id)) or {}
    if not profile.get(VISIBLE_FIELD):
        return ANONYMOUS
    account = accounts.get_account_profile(user_id)
    return (account or {}).get("full_name") or ANONYMOUS


def ranking(user_id: uuid.UUID, career_code: str = "DATA_ANALYST", basis: str = "exam", skill: Optional[str] = None) -> dict:
    """The leaderboard as this learner may see it: other people are anonymous unless they chose to show their name.

    ``basis`` "exam" ranks the entry exam; "current" ranks verified levels now, so learning moves the learner up.
    ``skill`` ranks one skill only. Group figures are aggregates and appear only with enough learners.
    """
    if basis not in BASES:
        raise ValueError("Cách xếp hạng không hợp lệ.")
    population = _population(career_code)
    skills = framework_skills()
    if skill and skill not in skills:
        raise ValueError("Kỹ năng không có trong khung xếp hạng.")
    entries = _ranked(population, basis, skill)
    mine = next((item for item in entries if item["user_id"] == str(user_id)), None)
    total = len(entries)

    def view(entry: dict) -> dict:
        is_me = entry is mine
        return {"rank": entry["rank"], "name": "Bạn" if is_me else _shown_name(entry["user_id"]), "is_me": is_me, "avatar": _shown_avatar(entry["user_id"], is_me), "overall_level": entry["overall_level"],
                "level_points": entry["level_points"], "max_points": entry["max_points"], "score": entry["score"]}

    board = [view(entry) for entry in entries[:BOARD_SIZE]]
    if mine and mine not in entries[:BOARD_SIZE]:
        board.append(view(mine))
    enough = total >= MIN_COHORT
    rank_change = None
    if mine and basis == "current":
        # Positions gained since the entry exam, on the same ranking (all skills or the chosen one).
        before = next(item for item in _ranked(population, "exam", skill) if item["user_id"] == str(user_id))
        rank_change = before["rank"] - mine["rank"]
    cohort, distribution = [], []
    if mine and enough:
        for code in skills:
            values = [int(item["levels"].get(code, 0)) for item in entries]
            own = int(mine["levels"].get(code, 0))
            cohort.append({"skill_code": code, "mine": own, "average": round(sum(values) / len(values), 2),
                           "at_or_below_percent": round(100 * sum(1 for value in values if value <= own) / len(values))})
        distribution = [{"level": level, "count": sum(1 for item in entries if item["overall_level"] == level)} for level in range(MAX_LEVEL + 1)]
    rules = {
        "exam": "Xếp theo tổng mức đã xác thực ở bài kiểm tra Career Adapt gần nhất, rồi đến điểm bài kiểm tra.",
        "current": "Xếp theo tổng mức đã xác thực hiện tại (bài kiểm tra đầu vào, bài kiểm tra hoàn thành và bài đánh giá tổng hợp), rồi đến điểm bài kiểm tra đầu vào.",
    }
    return {
        "basis": basis, "skill": skill, "skills": skills, "rank_change": rank_change, "cohort": cohort, "distribution": distribution,
        "my_levels": mine["levels"] if mine else None,
        "total": total, "min_cohort": MIN_COHORT, "enough": enough, "board": board,
        "me": view(mine) if mine else None,
        "top_percent": max(1, math.ceil(mine["rank"] / total * 100)) if mine and enough else None,
        "visible": bool((store.profiles.get(user_id) or {}).get(VISIBLE_FIELD)),
        "rule": rules[basis] + (" Chỉ tính một kỹ năng đã chọn." if skill else "") + " Mỗi người tính bài kiểm tra Career Adapt gần nhất đã chấm.",
    }


def set_visible(user_id: uuid.UUID, visible: bool) -> bool:
    profile = store.get_or_create_profile(user_id)
    profile[VISIBLE_FIELD] = bool(visible)
    store.persist_user_runtime(user_id)
    return profile[VISIBLE_FIELD]


def basis(user_id: uuid.UUID) -> list[dict]:
    """What a result rests on, so each part of it can be traced to a source."""
    target = resolve_target(store.get_or_create_profile(user_id))
    frameworks = sorted({skill["source_reference"] for skill in store.skills if skill.get("source_reference")})
    jd_sources = []
    if target.get("jd_id") and target.get("jd_version"):
        row = store.db.one("SELECT payload, source_url FROM jd_versions WHERE jd_id = ? AND jd_version = ?", (target["jd_id"], target["jd_version"]))
        if row:
            jd_sources = [{"label": item.get("label") or item["url"], "url": item["url"]} for item in json.loads(row["payload"]).get("sources") or [] if item.get("url")]
            if not jd_sources and row["source_url"]:
                jd_sources = [{"label": row["source_url"], "url": row["source_url"]}]
    own_jd = target.get("source_type") == "JD_USER"
    resources = catalog.list_resources(store.db)
    items = [
        {"title": "Khung kỹ năng", "detail": f"{len(store.skills)} kỹ năng và tiêu chí từng mức được xây dựng theo: {'; '.join(frameworks)}." if frameworks else f"{len(store.skills)} kỹ năng có tiêu chí cho từng mức.", "links": []},
        {"title": "Mức JD yêu cầu", "detail": f"Lấy từ mục tiêu của bạn: {target['name']}." + (" JD do bạn tự nhập, hệ thống chỉ đối chiếu với khung kỹ năng." if own_jd else ""), "links": jd_sources},
        {"title": "Điểm và mức đã xác thực", "detail": f"Máy chủ chấm bằng test case và rubric cố định của ngân hàng đề {BANK_VERSION}; ngưỡng đạt {PASS_THRESHOLD:g}/100. AI chỉ viết nhận xét, không tạo và không đổi điểm.", "links": []},
        {"title": "Học liệu trong lộ trình", "detail": f"{len(resources)} học liệu đã được duyệt và kiểm tra đường dẫn trước khi đưa vào lộ trình.", "links": []},
    ]
    salary = salary_reference()
    if salary:
        source = salary["source"]
        items.append({"title": "Lương tham khảo", "detail": f"{salary['statistic']} theo {source['label']}, kiểm tra ngày {source.get('checked_at', '')}.", "links": [{"label": source["label"], "url": source["url"]}]})
    return items


def overview(user_id: uuid.UUID, rank_basis: str = "exam", skill: Optional[str] = None) -> dict:
    return {"levels": level_guide(), "ranking": ranking(user_id, basis=rank_basis, skill=skill), "salary": salary_reference(), "basis": basis(user_id)}
