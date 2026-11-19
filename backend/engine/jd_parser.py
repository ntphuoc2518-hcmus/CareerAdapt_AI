"""JD ingestion: read PDF/DOCX/TXT, extract fields, map requirements to the skill catalog.

Transparent rules, not a language model. Every mapped skill keeps the source sentence, the rule
that fired and a confidence, and weak matches are flagged for the learner to confirm. The parser
never guesses a missing field, a skill level or a number of years of experience.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from backend.engine.skill_report import extract_text_from_upload, normalize

MAPPING = json.loads((Path(__file__).resolve().parents[2] / "data" / "skill_mapping_v4.json").read_text(encoding="utf-8"))
MAPPING_VERSION: str = MAPPING["mapping_version"]
LOW_CONFIDENCE: float = MAPPING["low_confidence_threshold"]

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_JD_BYTES = 5 * 1024 * 1024
MAX_JD_CHARS = 30000
MIN_JD_CHARS = 80
MAX_PDF_PAGES = 30

SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "PREFERRED": ("uu tien", "loi the", "diem cong", "nice to have", "preferred", "good to have", "bonus"),
    "REQUIRED": ("yeu cau", "requirements", "requirement", "must have", "qualifications", "bat buoc", "what we need", "ky nang can co", "required skills"),
    "RESPONSIBILITY": ("mo ta cong viec", "trach nhiem", "nhiem vu", "responsibilities", "what you will do", "job description", "cong viec"),
    "EDUCATION": ("hoc van", "education", "bang cap", "trinh do"),
    "BENEFITS": ("quyen loi", "benefits", "phuc loi", "che do", "what we offer"),
}
PREFERRED_MARKERS = ("a plus", "nice to have", "preferred", "good to have", "bonus", "advantage", "advantageous", "uu tien", "loi the", "diem cong", "duoc danh gia cao")
REQUIRED_MARKERS = ("required", "must have", "must be", "mandatory", "bat buoc", "yeu cau", "can co", "phai co")
LEVEL_TERMS = (
    ("INTERN", ("intern", "internship", "thuc tap", "trainee", "thuc tap sinh")),
    ("FRESHER", ("fresher", "moi tot nghiep", "entry level", "entry-level")),
    ("JUNIOR", ("junior",)),
    ("SENIOR", ("senior", "lead", "principal", "truong nhom")),
    ("MIDDLE", ("middle", "mid-level", "mid level")),
)
LABELLED_FIELDS = {
    "title": r"(?:vi tri|chuc danh|position|job title|title|role)",
    "employer": r"(?:cong ty|don vi tuyen dung|nha tuyen dung|company|employer)",
}
URL_PATTERN = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
EXPERIENCE_PATTERN = re.compile(r"\d+\s*(?:\+|-\s*\d+)?\s*(?:years?|nam)\b", re.IGNORECASE)


def _has_term(normalized_text: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", normalized_text) is not None


def decode_text_bytes(data: bytes) -> str:
    """Decode a text upload; binary or undecodable content is refused rather than guessed."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16", errors="strict")
    else:
        if b"\x00" in data:
            raise ValueError("Tệp có nội dung nhị phân, không phải văn bản thuần. Hãy kiểm tra lại tệp.")
        text = None
        for encoding in ("utf-8-sig", "cp1258"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Không đọc được bảng mã của tệp. Hãy lưu lại dưới dạng UTF-8.")
    control = sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t")
    if text and control / len(text) > 0.02:
        raise ValueError("Tệp chứa nhiều ký tự điều khiển nên có thể đã hỏng.")
    return text


def _reflow_pdf_lines(text: str) -> str:
    """PDF extraction breaks lines where the layout wrapped; rejoin them so a sentence stays whole."""
    merged: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        starts_new = bool(re.match(r"^[-*•–●▪◦\d]", line)) or _heading_of(line) is not None
        previous = merged[-1] if merged else ""
        if previous and not starts_new and previous[-1] not in ".:;!?" and _heading_of(previous) is None:
            merged[-1] = f"{previous} {line}"
        else:
            merged.append(line)
    return "\n".join(merged)


def _read_pdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    if not data.startswith(b"%PDF"):
        raise ValueError("Tệp không phải PDF hợp lệ hoặc đã hỏng.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("PDF đang được đặt mật khẩu nên không đọc được. Hãy gỡ mật khẩu hoặc dán nội dung.")
        pages = reader.pages
        count = len(pages)
        if count > MAX_PDF_PAGES:
            raise ValueError(f"PDF có {count} trang, vượt giới hạn {MAX_PDF_PAGES} trang.")
        text = _reflow_pdf_lines("\n".join((page.extract_text() or "") for page in pages))
    except ValueError:
        raise
    except (PyPdfError, OSError, KeyError, IndexError, TypeError, AttributeError, RecursionError) as error:
        raise ValueError("PDF bị hỏng hoặc không đọc được.") from error
    return text, count


def extract_jd_text(filename: str, data: bytes) -> dict:
    """Return the text of an uploaded JD. Raises ValueError with a message the learner can act on."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError("Định dạng chưa hỗ trợ. Hãy tải lên tệp PDF, DOCX hoặc TXT, hoặc dán nội dung JD.")
    if not data:
        raise ValueError("Tệp rỗng, không có nội dung để đọc.")
    if len(data) > MAX_JD_BYTES:
        raise ValueError("Tệp vượt giới hạn 5 MB.")
    pages = None
    if suffix == ".pdf":
        text, pages = _read_pdf(data)
        if not text.strip():
            raise ValueError("PDF không có lớp văn bản (có thể là ảnh quét). Hãy dán nội dung JD.")
    elif suffix == ".docx":
        text = extract_text_from_upload(filename, data)
    else:
        text = decode_text_bytes(data)
    return {"text": text, "file_type": suffix[1:], "pages": pages}


def validate_jd_text(text: str) -> str:
    cleaned = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")).strip()
    if len(cleaned) < MIN_JD_CHARS:
        raise ValueError(f"Nội dung JD quá ngắn ({len(cleaned)} ký tự). Cần ít nhất {MIN_JD_CHARS} ký tự để phân tích.")
    if len(cleaned) > MAX_JD_CHARS:
        raise ValueError(f"Nội dung JD vượt giới hạn {MAX_JD_CHARS} ký tự.")
    letters = sum(1 for char in cleaned if char.isalpha())
    if letters / len(cleaned) < 0.5 or len(cleaned.split()) < 12:
        raise ValueError("Nội dung không giống một bản mô tả công việc. Hãy kiểm tra lại tệp hoặc nội dung đã dán.")
    return cleaned


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _heading_of(line: str) -> Optional[str]:
    normalized = normalize(line).strip(" :-*#•\t").strip()
    if not normalized or len(normalized) > 60:
        return None
    for section, keys in SECTION_HEADINGS.items():
        if any(normalized == key or normalized.startswith(key + " ") or normalized.endswith(" " + key) for key in keys):
            return section
    return None


def _clauses(line: str) -> list[str]:
    # Parentheses form their own clause: "SQL (Python is a plus)" must not make SQL optional.
    parts = re.split(r"(?<=[.;!?])\s+|[()]", line.strip(" \t-*•–●"))
    return [part.strip() for part in parts if part and part.strip()]


def _labelled(lines: list[str], field: str) -> Optional[str]:
    pattern = re.compile(rf"^\s*[-*•]?\s*{LABELLED_FIELDS[field]}\s*[:：]\s*(.+)$")
    for line in lines[:25]:
        normalized = normalize(line)
        match = pattern.match(normalized)
        if match:
            # Slice the original line so accents and capitals survive.
            return line.split(":", 1)[-1].split("：", 1)[-1].strip()[:180] or None
    return None


def _role_level(*texts: str) -> Optional[str]:
    for text in texts:
        normalized = normalize(text or "")
        for level, terms in LEVEL_TERMS:
            if any(_has_term(normalized, term) for term in terms):
                return level
    return None


def classify_scope(title: Optional[str], normalized_text: str, catalog_skill_count: int) -> tuple[str, str]:
    """Decide whether the JD is a Data Analyst role. Out-of-scope JDs are never mapped silently."""
    in_terms = MAPPING["scope"]["in_scope_terms"]
    other_terms = MAPPING["scope"]["other_role_terms"]
    normalized_title = normalize(title or "")
    title_in = any(_has_term(normalized_title, term) for term in in_terms)
    title_other = any(_has_term(normalized_title, term) for term in other_terms)
    if title_in and not title_other:
        return "IN_SCOPE", "Chức danh thuộc nhóm Data Analyst."
    if title_other and not title_in:
        return "OUT_OF_SCOPE", f"Chức danh “{title}” không thuộc nhóm Data Analyst mà hệ thống đang hỗ trợ."
    if any(_has_term(normalized_text, term) for term in in_terms):
        return "IN_SCOPE", "Nội dung JD có nhắc đến vai trò phân tích dữ liệu."
    if catalog_skill_count >= 2:
        return "UNCERTAIN", "Không xác định rõ chức danh nhưng JD có nhiều kỹ năng phân tích dữ liệu. Hãy xác nhận đây là JD Data Analyst."
    return "OUT_OF_SCOPE", "Không tìm thấy dấu hiệu của vị trí Data Analyst trong nội dung JD."


def _requirement_type(section: Optional[str], clause_normalized: str) -> tuple[str, str]:
    """Clause wording beats the section it sits in; an unlabelled mention stays UNSPECIFIED."""
    if any(_has_term(clause_normalized, marker) for marker in PREFERRED_MARKERS):
        return "PREFERRED", "Câu có từ khóa ưu tiên/lợi thế."
    if any(_has_term(clause_normalized, marker) for marker in REQUIRED_MARKERS):
        return "REQUIRED", "Câu có từ khóa bắt buộc/yêu cầu."
    if section == "PREFERRED":
        return "PREFERRED", "Thuộc mục ưu tiên/lợi thế."
    if section == "REQUIRED":
        return "REQUIRED", "Thuộc mục yêu cầu."
    return "UNSPECIFIED", "JD không nêu rõ là bắt buộc hay ưu tiên."


TYPE_RANK = {"REQUIRED": 2, "UNSPECIFIED": 1, "PREFERRED": 0}


def parse_job_description(text: str, title_hint: str = "", employer_hint: str = "", source_url: str = "") -> dict:
    """Extract reviewable fields and skill requirements; absent fields stay empty."""
    lines = [line.rstrip() for line in text.split("\n")]
    nonblank = [line for line in lines if line.strip()]
    title = (title_hint or "").strip() or _labelled(nonblank, "title")
    if not title and nonblank:
        first = nonblank[0].strip(" -*•#")
        if len(first.split()) >= 2 and len(first) <= 90 and ":" not in first and not _heading_of(first):
            title = first
    employer = (employer_hint or "").strip() or _labelled(nonblank, "employer")
    url_match = URL_PATTERN.search(text)
    url = (source_url or "").strip() or (url_match.group(0).rstrip(".,;") if url_match else "")

    found: dict[str, dict] = {}
    unmeasured: dict[str, dict] = {}
    responsibilities: list[str] = []
    education: list[str] = []
    experience: list[str] = []
    section: Optional[str] = None
    for line in nonblank:
        heading = _heading_of(line)
        if heading:
            section = heading
            # "Required: strong SQL" keeps its content after the heading word.
            if ":" not in line or not line.split(":", 1)[1].strip():
                continue
        if section == "BENEFITS":
            continue
        if section == "RESPONSIBILITY":
            responsibilities.append(line.strip(" -*•")[:220])
        if section == "EDUCATION":
            education.append(line.strip(" -*•")[:220])
        for clause in _clauses(line):
            normalized = normalize(clause)
            if EXPERIENCE_PATTERN.search(normalized):
                experience.append(clause[:220])
            requirement_type, type_reason = _requirement_type(section, normalized)
            for skill_code, terms in MAPPING["skills"].items():
                hits = [term for term in terms if _has_term(normalized, term["term"])]
                if not hits:
                    continue
                best = max(hits, key=lambda term: term["confidence"])
                entry = found.setdefault(skill_code, {
                    "skill_code": skill_code, "excerpts": [], "matched_terms": set(), "mentions": 0,
                    "confidence": 0.0, "mapping_rule": None, "requirement_type": requirement_type, "type_reason": type_reason,
                })
                entry["mentions"] += 1
                entry["matched_terms"].update(term["term"] for term in hits)
                if best["confidence"] > entry["confidence"]:
                    entry["confidence"] = best["confidence"]
                    entry["mapping_rule"] = best["rule"]
                if TYPE_RANK[requirement_type] > TYPE_RANK[entry["requirement_type"]]:
                    entry["requirement_type"], entry["type_reason"] = requirement_type, type_reason
                excerpt = clause[:300]
                if excerpt not in entry["excerpts"] and len(entry["excerpts"]) < 3:
                    entry["excerpts"].append(excerpt)
            for group in MAPPING["unmeasured"]:
                if any(_has_term(normalized, term) for term in group["terms"]):
                    item = unmeasured.setdefault(group["label"], {"label": group["label"], "requirement_type": requirement_type, "excerpt": clause[:300]})
                    if TYPE_RANK[requirement_type] > TYPE_RANK[item["requirement_type"]]:
                        item["requirement_type"] = requirement_type

    requirements = []
    for skill_code, entry in found.items():
        confidence = entry["confidence"]
        # A weak mention repeated several times is still a weak mapping.
        needs_confirmation = confidence < LOW_CONFIDENCE or entry["requirement_type"] == "UNSPECIFIED"
        reasons = []
        if confidence < LOW_CONFIDENCE:
            reasons.append("Từ khóa mơ hồ, có thể không đúng phạm vi kỹ năng.")
        if entry["requirement_type"] == "UNSPECIFIED":
            reasons.append(entry["type_reason"])
        requirements.append({
            "requirement_id": f"REQ-{uuid.uuid4().hex[:10]}",
            "skill_code": skill_code,
            "in_catalog": True,
            "requirement_type": entry["requirement_type"],
            "type_reason": entry["type_reason"],
            "source_excerpt": entry["excerpts"][0],
            "source_excerpts": entry["excerpts"],
            "normalized_text": f"{skill_code}: " + ", ".join(sorted(entry["matched_terms"])),
            "matched_terms": sorted(entry["matched_terms"]),
            "mentions": entry["mentions"],
            "confidence": confidence,
            "mapping_rule": entry["mapping_rule"],
            "needs_confirmation": needs_confirmation,
            "confirmation_reasons": reasons,
        })
    requirements.sort(key=lambda item: (-TYPE_RANK[item["requirement_type"]], -item["confidence"], item["skill_code"]))
    for item in unmeasured.values():
        requirements.append({
            "requirement_id": f"REQ-{uuid.uuid4().hex[:10]}",
            "skill_code": None,
            "in_catalog": False,
            "label": item["label"],
            "requirement_type": item["requirement_type"],
            "source_excerpt": item["excerpt"],
            "source_excerpts": [item["excerpt"]],
            "normalized_text": item["label"],
            "confidence": 0.8,
            "mapping_rule": "OUTSIDE_CATALOG",
            "needs_confirmation": False,
            "confirmation_reasons": [],
        })

    catalog_count = sum(1 for item in requirements if item["in_catalog"])
    scope_status, scope_reason = classify_scope(title, normalize(text), catalog_count)
    warnings = []
    if not title:
        warnings.append("Không xác định được chức danh; hãy nhập chức danh.")
    if not employer:
        warnings.append("JD không nêu tên đơn vị tuyển dụng.")
    if catalog_count == 0:
        warnings.append("Không ánh xạ được yêu cầu nào sang danh mục kỹ năng Data Analyst.")
    return {
        "title": title,
        "employer": employer,
        "role_level": _role_level(title or "", text[:800]),
        "source_url": url,
        "responsibilities": responsibilities[:12],
        "education": education[:6],
        "experience_statements": list(dict.fromkeys(experience))[:6],
        "scope_status": scope_status,
        "scope_reason": scope_reason,
        "requirements": requirements,
        "warnings": warnings,
        "mapping_version": MAPPING_VERSION,
    }


def build_target_requirements(decisions: list[dict], config_id: str, skills_catalog: list[dict]) -> dict[str, dict]:
    """Turn confirmed requirements into target levels and weights from the approved config.

    Levels and base weights come only from the config, so nothing is inferred from JD wording.
    Required skills keep their base weight, preferred ones are discounted, and weights sum to 1.
    Catalog skills the JD does not mention get weight 0 and stay out of coverage.
    """
    config = MAPPING["target_configs"].get(config_id)
    if not config:
        raise ValueError("Cấu hình mức mục tiêu không hợp lệ.")
    factor = float(MAPPING["preferred_weight_factor"])
    by_skill: dict[str, dict] = {}
    for item in decisions:
        code = item["skill_code"]
        current = by_skill.get(code)
        if current is None or TYPE_RANK[item["requirement_type"]] > TYPE_RANK[current["requirement_type"]]:
            by_skill[code] = item
    raw = {}
    for code, item in by_skill.items():
        base = float((config["skills"].get(code) or {}).get("base_weight", 0))
        raw[code] = base * (1.0 if item["requirement_type"] == "REQUIRED" else factor)
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("Chưa có kỹ năng hợp lệ nào được xác nhận.")
    requirements: dict[str, dict] = {}
    positive = sorted(raw, key=lambda code: -raw[code])
    assigned = 0.0
    for index, code in enumerate(positive):
        weight = 1.0 - assigned if index == len(positive) - 1 else round(raw[code] / total, 4)
        assigned += weight
        item = by_skill[code]
        requirements[code] = {
            "target_level": int(config["skills"][code]["target_level"]),
            "weight": round(weight, 4),
            "requirement_type": item["requirement_type"],
            "rationale": item.get("source_excerpt") or "Được người dùng xác nhận.",
        }
    for skill in skills_catalog:
        code = skill["skill_code"]
        requirements.setdefault(code, {"target_level": int((config["skills"].get(code) or {}).get("target_level", skill.get("target_level", 1))), "weight": 0.0,
                                       "requirement_type": "NOT_IN_JD", "rationale": "JD không yêu cầu kỹ năng này."})
    core_codes = {skill["skill_code"] for skill in skills_catalog if skill.get("is_core")}
    for code, requirement in requirements.items():
        requirement["is_core"] = code in core_codes and requirement["requirement_type"] == "REQUIRED"
    return requirements
