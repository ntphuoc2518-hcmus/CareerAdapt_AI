"""Skill report: suggest a self-assessment from a learner's experience text and an optional JD.

Transparent keyword rules, not a language model: every suggestion lists the sentences
that triggered it so the learner can check it before confirming. Suggested levels are a
starting point for self-assessment only and never count as verified evidence.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from xml.etree import ElementTree

MAX_TEXT_CHARS = 30000
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

# Signals per skill and level (accent-free, lower case). Higher levels need stronger signals.
LEVEL_SIGNALS: dict[str, dict[int, tuple[str, ...]]] = {
    "STATISTICS": {
        1: ("statistics", "thong ke", "mean", "median", "trung binh", "trung vi", "descriptive"),
        2: ("standard deviation", "do lech chuan", "correlation", "tuong quan", "distribution", "phan phoi", "scipy"),
        3: ("a/b test", "ab test", "hypothesis", "kiem dinh", "p-value", "confidence interval", "khoang tin cay", "experiment design", "regression", "hoi quy"),
    },
    "SQL": {
        1: ("sql", "select", "where", "truy van", "query", "mysql", "postgres", "sql server"),
        2: ("join", "group by", "having", "subquery", "aggregate", "tong hop", "left join", "inner join"),
        3: ("window function", "over (", "partition by", "cte", "with recursive", "query optimization", "toi uu truy van", "index", "execution plan", "row_number", "rank("),
    },
    "DATA_QUALITY": {
        1: ("data cleaning", "lam sach", "clean data", "missing value", "gia tri thieu", "duplicate", "trung lap"),
        2: ("data validation", "kiem tra du lieu", "outlier", "ngoai lai", "data quality", "chat luong du lieu", "deduplicate", "reconcile", "doi chieu"),
        3: ("data pipeline", "etl", "great expectations", "data contract", "automated test", "kiem thu tu dong", "constraint", "data governance", "monitoring"),
    },
    "PYTHON": {
        1: ("python", "pandas", "read_csv", "jupyter", "notebook"),
        2: ("groupby", "pivot", "merge", "numpy", "datetime", "apply(", "lambda", "matplotlib", "seaborn"),
        3: ("vectoriz", "scikit", "sklearn", "airflow", "unit test", "pytest", "package", "module", "api", "automation", "tu dong hoa"),
    },
    "DATA_VIZ": {
        1: ("chart", "bieu do", "excel chart", "graph", "visualization", "truc quan"),
        2: ("dashboard", "power bi", "tableau", "looker", "data studio", "kpi"),
        3: ("dax", "data model", "drill", "storytelling", "design system", "executive dashboard", "row level security", "accessibility"),
    },
    "WRITTEN_COMM": {
        1: ("report", "bao cao", "presentation", "thuyet trinh", "email"),
        2: ("stakeholder", "recommendation", "khuyen nghi", "de xuat", "insight", "executive summary", "tom tat"),
        3: ("published", "xuat ban", "training", "dao tao", "mentor", "workshop", "documentation", "tai lieu huong dan", "led", "lanh dao"),
    },
}
PRODUCT_MARKERS = ("project", "du an", "san pham", "product", "built", "xay dung", "developed", "phat trien", "dashboard", "report", "bao cao", "github", "portfolio", "khoa luan", "thesis", "capstone")
YEARS_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:\+\s*)?(?:years?|nam)\b")


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold()).replace("đ", "d")
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\n+|•|•|^\s*[-*]\s+", text, flags=re.MULTILINE)
    return [part.strip(" -*\t") for part in parts if part and len(part.strip()) > 3]


def _contains(normalized_sentence: str, term: str) -> bool:
    term = normalize(term)
    if not term[-1:].isalnum():
        return term in normalized_sentence
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", normalized_sentence) is not None


def analyze_experience(text: str, skills_catalog: list[dict]) -> dict:
    """Suggest a level per skill with the evidence sentences, and list mentioned products."""
    text = (text or "")[:MAX_TEXT_CHARS]
    sentences = _sentences(text)
    normalized = [(sentence, normalize(sentence)) for sentence in sentences]
    names = {skill["skill_code"]: skill.get("skill_name", skill["skill_code"]) for skill in skills_catalog}
    suggestions = []
    for skill_code, levels in LEVEL_SIGNALS.items():
        if skill_code not in names:
            continue
        evidence: list[str] = []
        terms: set[str] = set()
        level_hits: dict[int, int] = {}
        for original, norm in normalized:
            for level, signals in levels.items():
                hits = [signal for signal in signals if _contains(norm, signal)]
                if hits:
                    # Count distinct signals, not sentences: one rich sentence can be strong evidence.
                    new_hits = [hit for hit in hits if hit not in terms]
                    level_hits[level] = level_hits.get(level, 0) + len(new_hits)
                    terms.update(hits)
                    if original not in evidence and len(evidence) < 4:
                        evidence.append(original[:220])
        # A level counts only when the level below is also evidenced (no "level 3 from one buzzword").
        suggested = 0
        for level in (1, 2, 3):
            if level_hits.get(level) and (level == 1 or suggested == level - 1 or level_hits.get(level, 0) >= 2):
                suggested = level
        years = [float(match.replace(",", ".")) for _, norm in normalized for match in YEARS_PATTERN.findall(norm)
                 if any(_contains(norm, signal) for signal in levels[1] + levels[2])]
        if suggested == 2 and years and max(years) >= 2 and level_hits.get(3):
            suggested = 3
        suggestions.append({
            "skill_code": skill_code,
            "skill_name": names[skill_code],
            "suggested_level": suggested,
            "detected": suggested > 0,
            "matched_terms": sorted(terms)[:8],
            "evidence": evidence,
        })
    products = []
    for original, norm in normalized:
        if any(_contains(norm, marker) for marker in PRODUCT_MARKERS) and original not in products:
            products.append(original[:220])
        if len(products) >= 8:
            break
    return {"suggestions": suggestions, "products": products}


def extract_text_from_upload(filename: str, data: bytes) -> str:
    """Plain text from .txt/.md/.csv, .pdf or .docx (read as XML, no macros or external parsers)."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Tệp vượt quá 2 MB.")
    name = (filename or "").lower()
    if name.endswith((".txt", ".md", ".csv")):
        for encoding in ("utf-8-sig", "utf-16", "cp1258", "latin-1"):
            try:
                return data.decode(encoding)[:MAX_TEXT_CHARS]
            except UnicodeDecodeError:
                continue
        raise ValueError("Không đọc được mã hóa của tệp văn bản.")
    if name.endswith(".pdf"):
        from backend.engine.jd_parser import _read_pdf

        return _read_pdf(data)[0][:MAX_TEXT_CHARS]
    if name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > 20 * 1024 * 1024:
                    raise ValueError("Tài liệu quá lớn.")
                xml = archive.read(info)
        except (zipfile.BadZipFile, KeyError):
            raise ValueError("Tệp .docx không hợp lệ.")
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            # Word never emits DTDs; refusing them rules out entity-expansion attacks.
            raise ValueError("Tệp .docx không hợp lệ.")
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        root = ElementTree.fromstring(xml)
        paragraphs = ["".join(node.text or "" for node in paragraph.iter(namespace + "t")) for paragraph in root.iter(namespace + "p")]
        return "\n".join(p for p in paragraphs if p.strip())[:MAX_TEXT_CHARS]
    raise ValueError("Chỉ hỗ trợ tệp .pdf, .txt, .md, .csv hoặc .docx.")
