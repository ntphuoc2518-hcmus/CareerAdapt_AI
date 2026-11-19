"""Knowledge Base: versioned, approved documents and hybrid retrieval with source citation.

Only sources on the allow-list below are ingested. The question bank, exam items, rubrics, blueprints
and everything owned by a learner stay out by construction, and an uploaded document that repeats exam
content is refused. Retrieval reads current, approved versions only.
"""
from __future__ import annotations

import array
import hashlib
import json
import math
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Optional

from backend.clock import utcnow
from backend.database import Database, dumps

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
GUIDE_FILE = DATA_DIR / "knowledge" / "huong_dan_career_adapt.md"
INDUSTRY_FILE = DATA_DIR / "knowledge" / "chi_so_theo_nganh.md"
# Reviewer of the catalogs these documents come from; they were not read again by a person here.
SEED_REVIEWER = "seed-import"
CHUNK_CHARS = 800
CHUNK_OVERLAP = 100
TOP_K = 5
RRF_K = 60
# Measured on gemini-embedding-2: related questions scored 0.70 or more, unrelated ones 0.58 or less.
MIN_COSINE = 0.64
EMBED_BATCH = 20
COMMON_TERM_SHARE = 0.4
MIN_TERM_MATCH = 0.5
STOPWORDS = set("la gi co the va cua cho voi trong tren nhu nao sao mot cac nhung duoc khong toi minh ban em anh chi hay nhe a ha thi ma de ve tu den khi neu vi nen da dang se rat cung nay do kia the what how why is are the a an of to in for and or do does can i my".split())
STATUSES = ("DRAFT", "APPROVED", "REJECTED", "RETIRED")


class KnowledgeError(ValueError):
    pass


def _folded(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def terms_of(text: str) -> list[str]:
    seen = dict.fromkeys(term for term in re.findall(r"[a-z0-9_]+", _folded(text)) if len(term) >= 2 and term not in STOPWORDS)
    return list(seen)[:24]


def chunk_text(body: str) -> list[dict]:
    """Split at headings and paragraphs; a long paragraph is cut with an overlap."""
    chunks: list[dict] = []
    heading = ""
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        if buffer.strip():
            chunks.append({"heading": heading, "content": buffer.strip()})
        buffer = ""

    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            flush()
            heading = block.lstrip("# ").strip()
            continue
        while len(block) > CHUNK_CHARS:
            flush()
            cut = block.rfind(" ", 0, CHUNK_CHARS)
            cut = cut if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
            chunks.append({"heading": heading, "content": block[:cut].strip()})
            block = block[max(cut - CHUNK_OVERLAP, 1):].strip()
        if len(buffer) + len(block) > CHUNK_CHARS:
            flush()
        buffer = f"{buffer}\n\n{block}" if buffer else block
    flush()
    return chunks


def _insert_chunks(db: Database, document_id: str, version: int, title: str, body: str) -> None:
    for ordinal, chunk in enumerate(chunk_text(body)):
        chunk_id = f"{document_id}:{version}:{ordinal}"
        heading = f"{title} — {chunk['heading']}" if chunk["heading"] else title
        db.execute("INSERT INTO knowledge_chunks(chunk_id, document_id, version, ordinal, heading, content) VALUES (?, ?, ?, ?, ?, ?)", (chunk_id, document_id, version, ordinal, heading, chunk["content"]))
        db.execute("INSERT INTO knowledge_chunks_fts(chunk_id, heading, content) VALUES (?, ?, ?)", (chunk_id, heading, chunk["content"]))


def save_document(db: Database, document_id: str, title: str, kind: str, origin: str, body: str, *, status: str = "DRAFT", source_url: Optional[str] = None, language: str = "vi",
                  meta: Optional[dict] = None, reviewer_id: Optional[str] = None, created_by: Optional[str] = None) -> dict:
    """Add a version when the content changed. The same content again changes nothing."""
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    latest = db.one("SELECT version, content_hash FROM knowledge_documents WHERE document_id = ? ORDER BY version DESC LIMIT 1", (document_id,))
    if latest and latest["content_hash"] == content_hash:
        return {"document_id": document_id, "version": latest["version"], "changed": False}
    version = int(latest["version"]) + 1 if latest else 1
    now = utcnow().isoformat()
    with db.transaction():
        db.execute("UPDATE knowledge_documents SET is_current = 0 WHERE document_id = ?", (document_id,))
        db.execute(
            """INSERT INTO knowledge_documents(document_id, version, is_current, status, title, kind, origin, language, source_url, body, content_hash, meta, reviewer_id, reviewed_at, created_by, created_at)
               VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (document_id, version, status, title, kind, origin, language, source_url, body, content_hash, dumps(meta or {}), reviewer_id, now if status == "APPROVED" else None, created_by, now),
        )
        _insert_chunks(db, document_id, version, title, body)
    return {"document_id": document_id, "version": version, "changed": True}


def _skill_docs() -> list[dict]:
    data = json.loads((DATA_DIR / "skills_v1.json").read_text(encoding="utf-8"))
    docs = []
    for skill in data["skills"]:
        levels = "\n\n".join(f"Mức {level}: {text}" for level, text in sorted((skill.get("rubric_summary") or {}).items()))
        docs.append({"id": f"skill-{skill['skill_code']}", "title": f"Kỹ năng {skill['skill_name']}", "kind": "SKILL", "url": skill.get("source_reference"),
                     "body": f"{skill['skill_name']} thuộc nhóm {skill.get('category')}. {skill.get('description', '')}\n\nMức mục tiêu mặc định: {skill.get('target_level')}. Trọng số: {skill.get('weight')}. Kỹ năng cốt lõi: {'có' if skill.get('is_core') else 'không'}.\n\n{levels}"})
    return docs


def _job_profile_docs() -> list[dict]:
    docs = []
    for profile in json.loads((DATA_DIR / "job_profiles_v1.json").read_text(encoding="utf-8")):
        requirements = "\n\n".join(f"{code}: mức {item.get('target_level')}, trọng số {item.get('weight')}. {item.get('rationale', '')}" for code, item in profile.get("requirements_by_skill", {}).items() if float(item.get("weight", 0)) > 0)
        extras = ", ".join(profile.get("additional_requirements", []))
        sources = profile.get("sources") or []
        first = sources[0] if sources and isinstance(sources[0], str) else (sources[0].get("url") if sources else None)
        docs.append({"id": f"job-{profile['profile_id']}", "title": f"Hồ sơ nghề {profile['name']}", "kind": "JOB_PROFILE", "url": first,
                     "body": f"{profile.get('description', '')} Thị trường: {profile.get('market', '')}. {profile.get('scope_note', '')}\n\n{requirements}\n\nYêu cầu khác chưa có bài đo: {extras or 'không'}."})
    return docs


def _mapping_doc() -> list[dict]:
    data = json.loads((DATA_DIR / "skill_mapping_v4.json").read_text(encoding="utf-8"))
    measured = "\n\n".join(f"{code}: các cách gọi thường gặp trong JD gồm {', '.join(str(term.get('term') if isinstance(term, dict) else term) for term in terms[:14])}." for code, terms in data["skills"].items())
    unmeasured = ", ".join(item["label"] for item in data.get("unmeasured", []))
    return [{"id": "skill-mapping", "title": "Cách đọc yêu cầu kỹ năng trong JD", "kind": "SKILL_MAPPING", "url": None,
             "body": f"{measured}\n\nCác yêu cầu hệ thống nhận ra nhưng chưa có bài đo: {unmeasured}."}]


def _jd_docs() -> list[dict]:
    docs = []
    for entry in json.loads((DATA_DIR / "jd_library_v4.json").read_text(encoding="utf-8"))["entries"]:
        if entry.get("review_status") != "APPROVED":
            continue
        requirements = "\n\n".join(f"{code}: mức {item.get('target_level')}, {item.get('requirement_type')}. {item.get('rationale', '')}" for code, item in entry.get("requirements_by_skill", {}).items() if float(item.get("weight", 0)) > 0)
        docs.append({"id": f"jd-{entry['jd_id']}", "title": f"JD {entry['title']}", "kind": "JD_LIBRARY", "url": entry.get("source_url"),
                     "body": f"{entry.get('description', '')} {entry.get('scope_note', '')}\n\n{requirements}\n\nYêu cầu khác: {', '.join(entry.get('additional_requirements', [])) or 'không'}."})
    return docs


def _resource_docs() -> list[dict]:
    docs = []
    for resource in json.loads((DATA_DIR / "learning_resources_v4.json").read_text(encoding="utf-8"))["resources"]:
        if resource.get("status") != "APPROVED":
            continue
        docs.append({"id": f"resource-{resource['resource_id']}", "title": f"Học liệu {resource['title']}", "kind": "RESOURCE", "url": resource.get("url"),
                     "body": f"{resource['title']} của {resource.get('provider')}. Dạng: {resource.get('resource_type')}. Kỹ năng: {', '.join(resource.get('skill_ids', []))}. Mức: {resource.get('level')}. Thời lượng ước tính: {resource.get('estimated_minutes')} phút. Kết quả học tập: {resource.get('learning_outcome', '')}"})
    return docs


def _activity_docs() -> list[dict]:
    docs = []
    for activity in json.loads((DATA_DIR / "activities_v1.json").read_text(encoding="utf-8")):
        objectives = "; ".join(activity.get("learning_objectives", []))
        docs.append({"id": f"activity-{activity['activity_id']}", "title": f"Học phần {activity['title']}", "kind": "ACTIVITY", "url": None,
                     "body": f"{activity['title']} nhắm tới kỹ năng {activity.get('target_skill')} mức {activity.get('target_level')}, ước tính {activity.get('estimated_hours')} giờ. Mục tiêu: {objectives}. Kết quả: {activity.get('learning_outcome', '')}. Tiên quyết: {', '.join(activity.get('prerequisites', [])) or 'không'}."})
    return docs


def _market_doc() -> list[dict]:
    """Market overview derived from the reviewed salary reference and the approved JD library; nothing is typed in here."""
    salary = json.loads((DATA_DIR / "salary_reference_v1.json").read_text(encoding="utf-8"))
    entries = [entry for entry in json.loads((DATA_DIR / "jd_library_v4.json").read_text(encoding="utf-8"))["entries"] if entry.get("review_status") == "APPROVED"]
    source = salary["source"]
    bands = "; ".join(f"{band['label']}: {band['value']} {salary['unit']}" for band in salary["bands"])
    overall = f" Tính chung mọi mức kinh nghiệm: {salary['overall']['value']} {salary['unit']}." if salary.get("overall") else ""
    demand: dict[str, list[int]] = {}
    extras: dict[str, int] = {}
    for entry in entries:
        for code, item in entry.get("requirements_by_skill", {}).items():
            if float(item.get("weight", 0)) > 0:
                demand.setdefault(code, []).append(int(item.get("target_level", 0)))
        for label in entry.get("additional_requirements", []):
            extras[label] = extras.get(label, 0) + 1
    skills = "\n\n".join(f"{code}: có trong {len(levels)}/{len(entries)} JD, mức yêu cầu từ {min(levels)} đến {max(levels)}." for code, levels in sorted(demand.items(), key=lambda pair: -len(pair[1])))
    others = "; ".join(label for label, count in sorted(extras.items(), key=lambda pair: (-pair[1], pair[0]))[:12])
    body = (f"{salary['statistic']} của nhóm {salary['role_label']} theo {source['label']} (khảo sát {source.get('survey_period', '')}, kiểm tra ngày {source.get('checked_at', '')}): {bands}.{overall} "
            f"{salary.get('missing_note', '')} {salary.get('scope_note', '')}\n\n"
            f"Yêu cầu kỹ năng trong {len(entries)} JD đã duyệt của thư viện:\n\n{skills}\n\n"
            f"Yêu cầu khác xuất hiện trong các JD này nhưng hệ thống chưa có bài đo: {others}.")
    return [{"id": "market-data-analyst", "title": "Thị trường Data Analyst: lương tham khảo và yêu cầu trong JD", "kind": "MARKET", "url": source["url"], "body": body}]


SEED_BUILDERS = (_skill_docs, _job_profile_docs, _mapping_doc, _jd_docs, _resource_docs, _activity_docs, _market_doc)


def seed_knowledge(db: Database) -> None:
    """Load the allow-listed catalogs. Admin decisions stand: a retired document stays retired."""
    # One write transaction: server processes starting together take turns, and the second one finds the
    # documents the first already saved instead of inserting the same version again.
    with db.transaction():
        for build in SEED_BUILDERS:
            for doc in build():
                save_document(db, doc["id"], doc["title"], doc["kind"], "SEED", doc["body"], status="APPROVED", source_url=doc["url"], reviewer_id=SEED_REVIEWER)
        # Written for this platform, so it waits for a person to approve it.
        save_document(db, "guide-career-adapt", "Hướng dẫn Career Adapt", "GUIDE", "SEED", GUIDE_FILE.read_text(encoding="utf-8"), status="DRAFT")
        save_document(db, "guide-industry-metrics", "Chỉ số thường gặp theo ngành cho Data Analyst", "GUIDE", "SEED", INDUSTRY_FILE.read_text(encoding="utf-8"), status="DRAFT")


def _exam_fingerprints() -> list[str]:
    bank = json.loads((DATA_DIR / "question_bank_v1.json").read_text(encoding="utf-8"))
    exam = json.loads((DATA_DIR / "exam_items_v5.json").read_text(encoding="utf-8"))
    texts = [item.get("stem", "") for item in bank["items"]] + [item.get("prompt", "") for item in exam["items"]]
    return [" ".join(_folded(text).split()) for text in texts if len(text) >= 40]


def contains_exam_content(text: str) -> bool:
    folded = " ".join(_folded(text).split())
    return any(print_ in folded for print_ in _exam_fingerprints())


def add_uploaded_document(db: Database, title: str, body: str, admin_id: str, source_url: Optional[str] = None) -> dict:
    """An upload always starts as a draft. Exam content is refused outright."""
    if contains_exam_content(body):
        raise KnowledgeError("Tài liệu chứa nội dung ngân hàng đề nên không được đưa vào kho kiến thức.")
    return save_document(db, f"doc-{uuid.uuid4().hex[:12]}", title, "DOCUMENT", "ADMIN", body, source_url=source_url, created_by=admin_id)


def decide(db: Database, document_id: str, status: str, reviewer_id: str) -> dict:
    if status not in STATUSES:
        raise KnowledgeError("Trạng thái tài liệu không hợp lệ.")
    moved = db.execute("UPDATE knowledge_documents SET status = ?, reviewer_id = ?, reviewed_at = ? WHERE document_id = ? AND is_current = 1", (status, reviewer_id, utcnow().isoformat(), document_id)).rowcount
    if not moved:
        raise KnowledgeError("Không tìm thấy tài liệu.")
    return {"document_id": document_id, "status": status}


def list_documents(db: Database) -> list[dict]:
    return db.query(
        """SELECT d.document_id, d.version, d.status, d.title, d.kind, d.origin, d.source_url, d.reviewer_id, d.reviewed_at, d.created_at,
                  COUNT(c.chunk_id) AS chunks, COUNT(c.embedding) AS embedded
           FROM knowledge_documents d LEFT JOIN knowledge_chunks c ON c.document_id = d.document_id AND c.version = d.version
           WHERE d.is_current = 1 GROUP BY d.document_id ORDER BY d.kind, d.title""")


def pack(vector: list[float]) -> bytes:
    return array.array("f", vector).tobytes()


def unpack(blob: bytes) -> list[float]:
    values = array.array("f")
    values.frombytes(blob)
    return values.tolist()


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    top = sum(a * b for a, b in zip(left, right))
    bottom = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return top / bottom if bottom else 0.0


def embed_pending(db: Database, limit: int = 100) -> int:
    """Fill in vectors for approved chunks. Without a provider, retrieval simply stays keyword-only."""
    from backend.ai_service import gateway

    if not gateway.is_available():
        return 0
    model = gateway.embedding_model()
    rows = db.query(
        """SELECT c.chunk_id, c.heading, c.content FROM knowledge_chunks c JOIN knowledge_documents d ON d.document_id = c.document_id AND d.version = c.version
           WHERE d.is_current = 1 AND d.status = 'APPROVED' AND (c.embedding IS NULL OR c.embedding_model != ?) LIMIT ?""", (model, limit))
    if not rows:
        return 0
    done = 0
    for start in range(0, len(rows), EMBED_BATCH):
        batch = rows[start:start + EMBED_BATCH]
        try:
            vectors = gateway.embed([f"{row['heading']}\n{row['content']}" for row in batch], purpose="document")
        except gateway.GatewayError:
            # A rate limit keeps what is done so far; the next tick continues from there.
            if done:
                return done
            raise
        with db.transaction():
            for row, vector in zip(batch, vectors):
                db.execute("UPDATE knowledge_chunks SET embedding = ?, embedding_model = ? WHERE chunk_id = ?", (pack(vector), model, row["chunk_id"]))
        done += len(batch)
    return done


APPROVED_JOIN = "JOIN knowledge_documents d ON d.document_id = c.document_id AND d.version = c.version AND d.is_current = 1 AND d.status = 'APPROVED'"


def _content_words(text: str) -> list[str]:
    return [word for word in re.findall(r"\w+", unicodedata.normalize("NFC", text).lower()) if len(word) >= 2 and _folded(word) not in STOPWORDS]


def _matches(query: str, text: str, needed: int) -> bool:
    """FTS ignores tone marks, so "bò" also finds "bộ". Tones count here when the learner typed them,
    and Vietnamese syllables only mean something together, so a query must keep two words side by side."""
    asked = _content_words(query)
    words = _content_words(text)
    folded = [_folded(word) for word in words]

    def present(term: str) -> bool:
        return term in folded if term == _folded(term) else term in words

    if sum(present(term) for term in asked) < needed:
        return False
    if len(asked) < 2:
        return True
    pairs, folded_pairs = set(zip(words, words[1:])), set(zip(folded, folded[1:]))
    return any((a, b) in pairs or (a == _folded(a) and b == _folded(b) and (a, b) in folded_pairs) for a, b in zip(asked, asked[1:]))


def _keyword_hits(db: Database, query: str) -> list[str]:
    """Rank by BM25, keeping chunks that hold at least half of the query's distinctive terms."""
    terms = terms_of(query)
    if not terms:
        return []
    total = (db.one(f"SELECT COUNT(*) AS n FROM knowledge_chunks c {APPROVED_JOIN}") or {}).get("n") or 1
    frequency = {term: db.one(f"SELECT COUNT(*) AS n FROM knowledge_chunks_fts f JOIN knowledge_chunks c ON c.chunk_id = f.chunk_id {APPROVED_JOIN} WHERE knowledge_chunks_fts MATCH ?", (f'"{term}"',))["n"] for term in terms}
    distinctive = [term for term in terms if 0 < frequency[term] / total < COMMON_TERM_SHARE]
    if not distinctive:
        # Only everyday words of the domain are left, so all of them have to appear together.
        expression = " ".join(f'"{term}"' for term in terms) if all(frequency.values()) else None
        needed = 0
    else:
        expression = " OR ".join(f'"{term}"' for term in distinctive)
        needed = math.ceil(len(terms) * MIN_TERM_MATCH)
    if not expression:
        return []
    rows = db.query(
        f"""SELECT f.chunk_id, f.heading, f.content FROM knowledge_chunks_fts f JOIN knowledge_chunks c ON c.chunk_id = f.chunk_id {APPROVED_JOIN}
            WHERE knowledge_chunks_fts MATCH ? ORDER BY bm25(knowledge_chunks_fts) LIMIT 30""", (expression,))
    return [row["chunk_id"] for row in rows if _matches(query, f"{row['heading']} {row['content']}", needed)]


def _vector_hits(db: Database, query: str, user_id: Any) -> list[str]:
    from backend.ai_service import gateway

    if not gateway.is_available():
        return []
    rows = db.query(f"SELECT c.chunk_id, c.embedding FROM knowledge_chunks c {APPROVED_JOIN} WHERE c.embedding IS NOT NULL AND c.embedding_model = ?", (gateway.embedding_model(),))
    if not rows:
        return []
    try:
        vector = gateway.embed([query], purpose="query", user_id=user_id, retries=0)[0]
    except gateway.GatewayError:
        return []
    scored = sorted(((cosine(vector, unpack(row["embedding"])), row["chunk_id"]) for row in rows), reverse=True)
    return [chunk_id for score, chunk_id in scored[:30] if score >= MIN_COSINE]


def retrieve(db: Database, query: str, *, top_k: int = TOP_K, user_id: Any = None) -> list[dict]:
    """Keyword and vector rankings merged by reciprocal rank. Each hit is a citable source."""
    keyword = _keyword_hits(db, query)
    vector = _vector_hits(db, query, user_id)
    scores: dict[str, float] = {}
    for ranking in (keyword, vector):
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (RRF_K + rank + 1)
    sources = []
    for chunk_id in sorted(scores, key=lambda key: (-scores[key], key))[:top_k]:
        row = db.one(f"SELECT c.chunk_id, c.document_id, c.version, c.heading, c.content, d.kind, d.source_url, d.title, d.reviewer_id FROM knowledge_chunks c {APPROVED_JOIN} WHERE c.chunk_id = ?", (chunk_id,))
        if row:
            sources.append({"source_id": f"S{len(sources) + 1}", **row, "method": "HYBRID" if chunk_id in keyword and chunk_id in vector else ("VECTOR" if chunk_id in vector else "KEYWORD")})
    return sources
