"""Objective test engine: form assembly, item scoring, level estimation and evaluation.

Pure functions only (no store access) so every rule can be unit tested:
- assemble_form: stratified random sampling by skill x level matrix, option shuffling
- score_item: exact / partial credit for single, multiple, numeric and ordering items
- score_attempt: difficulty-weighted skill scores, Wilson confidence interval, level ladder
- build_evaluation: band, pass decision, strengths, weaknesses, topic gaps, recommendations
- item_analysis: classical test theory statistics (p-value, point-biserial discrimination)
"""
from __future__ import annotations

import math
import random
from typing import Any, Optional

LEVEL_MASTERY_THRESHOLD = 0.6   # share of credit needed at a level to certify it
RAPID_RESPONSE_SECONDS = 5      # faster answers are flagged as possible guessing
FOCUS_LOSS_WARNING = 3

BANDS = [
    (80, "PROFICIENT", "Vững vàng", "Nắm chắc kiến thức nền tảng và một phần nội dung nâng cao."),
    (60, "MEETS", "Đạt chuẩn thực tập", "Đủ nền tảng cho vị trí Data Analyst thực tập; còn một số điểm cần củng cố."),
    (40, "DEVELOPING", "Đang phát triển", "Hiểu một phần kiến thức; cần học thêm trước khi ứng tuyển."),
    (0, "FOUNDATION", "Cần xây nền tảng", "Nên bắt đầu từ các học phần cơ bản trong lộ trình."),
]


# ---------------------------------------------------------------------------
# Form assembly
# ---------------------------------------------------------------------------

def public_item(item: dict, option_order: Optional[list[str]] = None) -> dict:
    """Strip answer key and explanation; apply the attempt's option order."""
    view = {key: item[key] for key in ("item_id", "skill_code", "level", "type", "stem", "topic") if key in item}
    for key in ("code", "unit"):
        if item.get(key):
            view[key] = item[key]
    if item.get("options"):
        by_id = {option["id"]: option for option in item["options"]}
        order = option_order or [option["id"] for option in item["options"]]
        view["options"] = [by_id[option_id] for option_id in order if option_id in by_id]
    return view


def assemble_form(blueprint: dict, items: list[dict], seed: Optional[int] = None) -> list[dict]:
    """Draw items per (skill, level) cell without replacement and shuffle presentation.

    Returns a list of {"item_id", "option_order"}. Raises ValueError when the bank
    cannot satisfy the blueprint so a broken form is never delivered.
    """
    rng = random.Random(seed)
    active = [item for item in items if item.get("status", "ACTIVE") == "ACTIVE"]
    form: list[dict] = []
    for skill_code, per_level in blueprint["matrix"].items():
        for level_key, count in per_level.items():
            pool = [item for item in active if item["skill_code"] == skill_code and int(item["level"]) == int(level_key)]
            if len(pool) < count:
                raise ValueError(f"Ngân hàng câu hỏi thiếu {skill_code} mức {level_key}: cần {count}, có {len(pool)}.")
            for item in rng.sample(pool, count):
                order = [option["id"] for option in item.get("options", [])]
                rng.shuffle(order)
                form.append({"item_id": item["item_id"], "option_order": order})
    rng.shuffle(form)
    return form


# ---------------------------------------------------------------------------
# Item scoring
# ---------------------------------------------------------------------------

def _to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace("%", "")
    if not text:
        return None
    # Accept Vietnamese formatting ("270.000", "-14,29") and English ("270,000", "1,170,000.50").
    if "," in text and "." in text:
        decimal_comma = text.rfind(",") > text.rfind(".")
        text = text.replace(".", "").replace(",", ".") if decimal_comma else text.replace(",", "")
    elif "," in text:
        whole, _, fraction = text.rpartition(",")
        thousands = text.count(",") > 1 or (len(fraction) == 3 and whole.lstrip("-") not in ("", "0"))
        text = text.replace(",", "") if thousands else text.replace(",", ".")
    elif text.count(".") >= 1:
        whole, _, fraction = text.rpartition(".")
        # "270.000" and "1.170.000" are thousands separators; "2.33" is a decimal.
        if text.count(".") > 1 or (len(fraction) == 3 and whole.lstrip("-") not in ("", "0")):
            text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def score_item(item: dict, response: Any) -> float:
    """Return credit in [0, 1]. Unanswered items score 0."""
    if response is None or response == "" or response == []:
        return 0.0
    kind = item["type"]
    key = item["answer"]
    if kind == "single":
        return 1.0 if response == key else 0.0
    if kind == "multiple":
        if not isinstance(response, list):
            return 0.0
        chosen = set(response)
        correct = set(key)
        # Right picks earn credit, wrong picks cancel it: guessing "all" never pays.
        credit = (len(chosen & correct) - len(chosen - correct)) / len(correct)
        return round(max(0.0, min(1.0, credit)), 4)
    if kind == "numeric":
        value = _to_number(response)
        if value is None:
            return 0.0
        return 1.0 if abs(value - float(key)) <= float(item.get("tolerance", 0)) + 1e-9 else 0.0
    if kind == "ordering":
        if not isinstance(response, list) or sorted(response) != sorted(key):
            return 0.0
        if response == key:
            return 1.0
        # Partial credit: share of item pairs kept in the correct relative order.
        position = {item_id: index for index, item_id in enumerate(response)}
        pairs = [(a, b) for i, a in enumerate(key) for b in key[i + 1:]]
        concordant = sum(1 for a, b in pairs if position[a] < position[b])
        credit = concordant / len(pairs)
        # Below chance-level ordering earns nothing.
        return round(max(0.0, (credit - 0.5) / 0.5), 4)
    return 0.0


# ---------------------------------------------------------------------------
# Attempt scoring
# ---------------------------------------------------------------------------

def wilson_interval(successes: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4))


def estimate_level(level_credit: dict[int, tuple[float, int]]) -> tuple[int, int]:
    """Highest consecutive level whose credit ratio meets the mastery threshold.

    Returns (estimated_level, highest_level_tested). A level that was not tested
    stops the ladder: the test cannot certify what it did not measure.
    """
    estimated = 0
    highest_tested = max(level_credit) if level_credit else 0
    for level in (1, 2, 3):
        if level not in level_credit:
            break
        earned, count = level_credit[level]
        if count and earned / count >= LEVEL_MASTERY_THRESHOLD:
            estimated = level
        else:
            break
    return estimated, highest_tested


def score_attempt(form_items: list[dict], responses: dict[str, dict], skills: list[dict], difficulty_points: dict) -> dict:
    """Score every item and aggregate per skill and overall."""
    skill_meta = {skill["skill_code"]: skill for skill in skills}
    item_results = []
    per_skill: dict[str, dict] = {}
    for item in form_items:
        response = (responses.get(item["item_id"]) or {}).get("value")
        credit = score_item(item, response)
        points = float(difficulty_points.get(str(item["level"]), item["level"]))
        item_results.append({
            "item_id": item["item_id"],
            "skill_code": item["skill_code"],
            "level": item["level"],
            "topic": item.get("topic"),
            "answered": response not in (None, "", []),
            "credit": credit,
            "points_possible": points,
            "points_earned": round(credit * points, 4),
            "time_spent_seconds": (responses.get(item["item_id"]) or {}).get("time_spent_seconds", 0),
        })
        bucket = per_skill.setdefault(item["skill_code"], {"earned": 0.0, "possible": 0.0, "credit_sum": 0.0, "count": 0, "levels": {}})
        bucket["earned"] += credit * points
        bucket["possible"] += points
        bucket["credit_sum"] += credit
        bucket["count"] += 1
        earned, count = bucket["levels"].get(item["level"], (0.0, 0))
        bucket["levels"][item["level"]] = (earned + credit, count + 1)

    skill_results = {}
    weighted_sum = 0.0
    weight_total = 0.0
    framework_order = [skill["skill_code"] for skill in skills]
    ordered = sorted(per_skill.items(), key=lambda pair: framework_order.index(pair[0]) if pair[0] in framework_order else len(framework_order))
    for skill_code, bucket in ordered:
        meta = skill_meta.get(skill_code, {})
        percent = round(100 * bucket["earned"] / bucket["possible"], 2) if bucket["possible"] else 0.0
        low, high = wilson_interval(bucket["credit_sum"], bucket["count"])
        level, highest_tested = estimate_level(bucket["levels"])
        target = int(meta.get("target_level", 2))
        skill_results[skill_code] = {
            "skill_code": skill_code,
            "skill_name": meta.get("skill_name", skill_code),
            "is_core": bool(meta.get("is_core")),
            "weight": meta.get("weight", 0),
            "items": bucket["count"],
            "points_earned": round(bucket["earned"], 2),
            "points_possible": bucket["possible"],
            "percent": percent,
            "confidence_interval": [round(low * 100, 1), round(high * 100, 1)],
            "reliability": "LOW" if bucket["count"] < 4 else ("MEDIUM" if bucket["count"] < 8 else "HIGH"),
            "level_breakdown": {str(lv): {"credit": round(e, 2), "items": c, "percent": round(100 * e / c, 1) if c else 0} for lv, (e, c) in sorted(bucket["levels"].items())},
            "estimated_level": level,
            "highest_level_tested": highest_tested,
            "target_level": target,
            "gap": max(0, target - level),
        }
        weight = float(meta.get("weight", 0)) or 1.0
        weighted_sum += weight * percent
        weight_total += weight

    total_possible = sum(result["points_possible"] for result in item_results)
    total_earned = sum(result["points_earned"] for result in item_results)
    return {
        "raw_points": round(total_earned, 2),
        "max_points": total_possible,
        "raw_percent": round(100 * total_earned / total_possible, 2) if total_possible else 0.0,
        # Composite weighs skills by the career framework so a long SQL section cannot dominate.
        "composite_score": round(weighted_sum / weight_total, 2) if weight_total else 0.0,
        "answered": sum(1 for result in item_results if result["answered"]),
        "total_items": len(item_results),
        "correct_items": sum(1 for result in item_results if result["credit"] >= 1.0),
        "skills": skill_results,
        "items": item_results,
    }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def band_for(score: float) -> dict:
    for threshold, code, label, summary in BANDS:
        if score >= threshold:
            return {"code": code, "label": label, "summary": summary}
    return {"code": BANDS[-1][1], "label": BANDS[-1][2], "summary": BANDS[-1][3]}


def integrity_review(item_results: list[dict], events: list[dict], auto_submitted: bool) -> dict:
    focus_losses = sum(1 for event in events if event.get("type") == "focus_lost")
    pastes = sum(1 for event in events if event.get("type") == "paste")
    rapid = [r["item_id"] for r in item_results if r["answered"] and 0 < (r.get("time_spent_seconds") or 0) < RAPID_RESPONSE_SECONDS]
    flags = []
    if focus_losses >= FOCUS_LOSS_WARNING:
        flags.append(f"Rời khỏi trang làm bài {focus_losses} lần.")
    if pastes:
        flags.append(f"Dán nội dung {pastes} lần.")
    if len(rapid) >= max(3, len(item_results) // 4):
        flags.append(f"{len(rapid)} câu trả lời dưới {RAPID_RESPONSE_SECONDS} giây (có thể đoán).")
    if auto_submitted:
        flags.append("Hết giờ, hệ thống tự nộp bài.")
    needs_review = focus_losses >= FOCUS_LOSS_WARNING or len(rapid) >= max(3, len(item_results) // 4)
    return {
        "status": "NEEDS_REVIEW" if needs_review else "OK",
        "focus_losses": focus_losses,
        "paste_events": pastes,
        "rapid_responses": rapid,
        "auto_submitted": auto_submitted,
        "flags": flags,
    }


def build_evaluation(score: dict, blueprint: dict, activities: list[dict], previous: Optional[dict] = None, cohort_scores: Optional[list[float]] = None) -> dict:
    composite = score["composite_score"]
    skills = score["skills"]
    pass_mark = float(blueprint.get("pass_mark_percent", 60))
    core_min = float(blueprint.get("core_skill_min_percent", 0))
    failing_core = [s["skill_name"] for s in skills.values() if s["is_core"] and s["percent"] < core_min]
    passed = composite >= pass_mark and not failing_core

    reasons = []
    if composite < pass_mark:
        reasons.append(f"Điểm tổng hợp {composite:.1f} thấp hơn ngưỡng đạt {pass_mark:.0f}.")
    for name in failing_core:
        reasons.append(f"Kỹ năng cốt lõi '{name}' dưới mức tối thiểu {core_min:.0f}%.")

    strengths = sorted((s for s in skills.values() if s["percent"] >= 75), key=lambda s: -s["percent"])
    weaknesses = sorted((s for s in skills.values() if s["percent"] < 60 or s["gap"] > 0), key=lambda s: (not s["is_core"], s["percent"]))

    topic_stats: dict[tuple[str, str], list[float]] = {}
    for result in score["items"]:
        topic_stats.setdefault((result["skill_code"], result.get("topic") or "Khác"), []).append(result["credit"])
    topic_gaps = sorted(
        ({"skill_code": skill, "topic": topic, "percent": round(100 * sum(c) / len(c), 1), "items": len(c)}
         for (skill, topic), c in topic_stats.items() if sum(c) / len(c) < 0.6),
        key=lambda gap: gap["percent"],
    )

    recommendations = []
    for skill in weaknesses:
        related = [a for a in activities if a.get("target_skill") == skill["skill_code"]]
        topics = [gap["topic"] for gap in topic_gaps if gap["skill_code"] == skill["skill_code"]]
        recommendations.append({
            "skill_code": skill["skill_code"],
            "skill_name": skill["skill_name"],
            "priority": "HIGH" if skill["is_core"] or skill["percent"] < 40 else "MEDIUM",
            "message": (f"Ôn lại: {', '.join(topics)}." if topics else "Củng cố kiến thức ở mức mục tiêu.")
                       + f" Mức ước lượng {skill['estimated_level']}/{skill['target_level']}.",
            "activities": [{"activity_id": a["activity_id"], "title": a["title"], "learning_outcome": a.get("learning_outcome"), "estimated_hours": a.get("estimated_hours")} for a in related],
            "practice_blueprint_id": f"SKILL_CHECK_{skill['skill_code']}",
        })

    comparison = None
    if previous:
        prev_skills = previous.get("skills", {})
        comparison = {
            "previous_attempt_id": previous.get("attempt_id"),
            "previous_submitted_at": previous.get("submitted_at"),
            "composite_delta": round(composite - previous.get("composite_score", 0), 2),
            "skill_deltas": {code: round(s["percent"] - prev_skills[code]["percent"], 2) for code, s in skills.items() if code in prev_skills},
        }

    percentile = None
    if cohort_scores and len(cohort_scores) >= 5:
        below = sum(1 for value in cohort_scores if value < composite)
        equal = sum(1 for value in cohort_scores if value == composite)
        percentile = round(100 * (below + 0.5 * equal) / len(cohort_scores), 1)

    band = band_for(composite)
    headline = f"{band['label']} – {composite:.1f}/100. " + ("Đạt yêu cầu bài kiểm tra." if passed else "Chưa đạt yêu cầu bài kiểm tra.")
    return {
        "passed": passed,
        "pass_mark_percent": pass_mark,
        "fail_reasons": reasons,
        "band": band,
        "headline": headline,
        "strengths": [{"skill_code": s["skill_code"], "skill_name": s["skill_name"], "percent": s["percent"]} for s in strengths],
        "weaknesses": [{"skill_code": s["skill_code"], "skill_name": s["skill_name"], "percent": s["percent"], "gap": s["gap"]} for s in weaknesses],
        "topic_gaps": topic_gaps,
        "recommendations": recommendations,
        "comparison": comparison,
        "percentile": percentile,
        "cohort_size": len(cohort_scores or []),
    }


def time_analytics(item_results: list[dict], time_limit_seconds: int, elapsed_seconds: float) -> dict:
    times = [r.get("time_spent_seconds") or 0 for r in item_results]
    answered_times = [t for r, t in zip(item_results, times) if r["answered"]]
    per_skill: dict[str, float] = {}
    for result, seconds in zip(item_results, times):
        per_skill[result["skill_code"]] = per_skill.get(result["skill_code"], 0) + seconds
    return {
        "elapsed_seconds": round(elapsed_seconds, 1),
        "time_limit_seconds": time_limit_seconds,
        "average_seconds_per_item": round(sum(answered_times) / len(answered_times), 1) if answered_times else 0,
        "slowest_items": [r["item_id"] for r, _ in sorted(zip(item_results, times), key=lambda pair: -pair[1])[:3] if _ > 0],
        "seconds_by_skill": {code: round(value, 1) for code, value in per_skill.items()},
    }


# ---------------------------------------------------------------------------
# Item analysis (classical test theory)
# ---------------------------------------------------------------------------

def _point_biserial(item_scores: list[float], totals: list[float]) -> Optional[float]:
    n = len(item_scores)
    if n < 3:
        return None
    mean_item = sum(item_scores) / n
    mean_total = sum(totals) / n
    cov = sum((x - mean_item) * (y - mean_total) for x, y in zip(item_scores, totals)) / n
    var_item = sum((x - mean_item) ** 2 for x in item_scores) / n
    var_total = sum((y - mean_total) ** 2 for y in totals) / n
    if var_item == 0 or var_total == 0:
        return None
    return round(cov / math.sqrt(var_item * var_total), 3)


def item_analysis(items: list[dict], attempts: list[dict]) -> list[dict]:
    """Difficulty (mean credit) and discrimination (corrected item-total correlation)."""
    observations: dict[str, list[tuple[float, float]]] = {}
    for attempt in attempts:
        results = attempt.get("score", {}).get("items", [])
        total = sum(r["credit"] for r in results)
        for result in results:
            # Exclude the item itself from the total to avoid inflated correlations.
            observations.setdefault(result["item_id"], []).append((result["credit"], total - result["credit"]))
    report = []
    for item in items:
        data = observations.get(item["item_id"], [])
        n = len(data)
        p_value = round(sum(c for c, _ in data) / n, 3) if n else None
        discrimination = _point_biserial([c for c, _ in data], [t for _, t in data]) if n else None
        flags = []
        if n >= 5:
            if p_value is not None and p_value < 0.2:
                flags.append("Quá khó")
            if p_value is not None and p_value > 0.95:
                flags.append("Quá dễ")
            if discrimination is not None and discrimination < 0.2:
                flags.append("Phân loại kém")
        report.append({
            "item_id": item["item_id"],
            "skill_code": item["skill_code"],
            "level": item["level"],
            "type": item["type"],
            "topic": item.get("topic"),
            "status": item.get("status", "ACTIVE"),
            "exposures": n,
            "p_value": p_value,
            "discrimination": discrimination,
            "flags": flags if n >= 5 else ["Chưa đủ dữ liệu"] if n else [],
        })
    return report
