"""Knowledge Base and retrieval: versions, approval, hybrid search and what must never get in."""
import json
import sqlite3
from pathlib import Path

import pytest

from ai_helpers import GatewayError, use_fake
from backend.ai_service import knowledge
from backend.database import Database, SCHEMA_VERSION
from backend.store import store
from v5_helpers import ADMIN, STUDENT, client

DATA = Path(__file__).resolve().parents[1] / "data"
A = "/api/v1/assistant"


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield
    store.reset()


def all_chunks() -> str:
    return "\n".join(row["content"] for row in store.db.query("SELECT content FROM knowledge_chunks"))


def add_doc(title="Tài liệu nội bộ", body="Mô hình hồi quy tuyến tính dùng để dự báo doanh thu xanhlaquy theo tháng."):
    response = client.post(f"{A}/admin/knowledge", json={"title": title, "body": body}, headers=ADMIN)
    assert response.status_code == 201, response.text
    return response.json()["document_id"]


def decide(document_id, status="APPROVED"):
    assert client.post(f"{A}/admin/knowledge/{document_id}/decision", json={"status": status}, headers=ADMIN).status_code == 200


def test_chunks_follow_headings_and_a_long_paragraph_is_split_with_overlap():
    long_text = " ".join(f"tu{index}" for index in range(400))
    chunks = knowledge.chunk_text(f"# Mục A\n\nĐoạn một.\n\n# Mục B\n\n{long_text}")
    assert chunks[0] == {"heading": "Mục A", "content": "Đoạn một."}
    parts = [item for item in chunks if item["heading"] == "Mục B"]
    assert len(parts) > 1 and all(len(item["content"]) <= knowledge.CHUNK_CHARS for item in parts)
    assert parts[0]["content"].split()[-1] in parts[1]["content"]


def test_seed_loads_the_inherited_catalogs_once():
    kinds = {row["kind"]: row["n"] for row in store.db.query("SELECT kind, COUNT(*) AS n FROM knowledge_documents GROUP BY kind")}
    assert kinds["SKILL"] == 6 and kinds["RESOURCE"] > 0 and kinds["ACTIVITY"] == 13 and kinds["JOB_PROFILE"] == 4 and kinds["JD_LIBRARY"] > 0 and kinds["SKILL_MAPPING"] == 1
    before = store.db.one("SELECT COUNT(*) AS n FROM knowledge_chunks")["n"]
    knowledge.seed_knowledge(store.db)
    assert store.db.one("SELECT COUNT(*) AS n FROM knowledge_chunks")["n"] == before


def test_a_changed_document_gets_a_new_version_and_only_the_new_one_is_retrieved():
    knowledge.save_document(store.db, "doc", "Tài liệu", "DOCUMENT", "ADMIN", "Nội dung cũ về kiểm toán vòng một.", status="APPROVED")
    knowledge.save_document(store.db, "doc", "Tài liệu", "DOCUMENT", "ADMIN", "Nội dung mới về hợp nhất báo cáo.", status="APPROVED")
    assert [row["version"] for row in store.db.query("SELECT version FROM knowledge_documents WHERE document_id = 'doc' ORDER BY version")] == [1, 2]
    assert knowledge.retrieve(store.db, "kiểm toán vòng một") == []
    hit = knowledge.retrieve(store.db, "hợp nhất báo cáo")[0]
    assert hit["version"] == 2 and hit["document_id"] == "doc"


def test_a_draft_is_invisible_until_it_is_approved_and_a_retired_one_disappears():
    document_id = add_doc()
    assert knowledge.retrieve(store.db, "hồi quy xanhlaquy") == []
    decide(document_id)
    assert knowledge.retrieve(store.db, "hồi quy xanhlaquy")[0]["document_id"] == document_id
    decide(document_id, "RETIRED")
    assert knowledge.retrieve(store.db, "hồi quy xanhlaquy") == []


def test_the_written_guide_waits_for_approval():
    assert store.db.one("SELECT status FROM knowledge_documents WHERE document_id = 'guide-career-adapt'")["status"] == "DRAFT"
    assert not [item for item in knowledge.retrieve(store.db, "Readiness bị khóa khi nào") if item["document_id"] == "guide-career-adapt"]
    decide("guide-career-adapt")
    assert any(item["document_id"] == "guide-career-adapt" for item in knowledge.retrieve(store.db, "Readiness bị khóa khi nào"))


def test_a_retired_seed_document_stays_retired_after_a_restart():
    document_id = store.db.one("SELECT document_id FROM knowledge_documents WHERE kind = 'RESOURCE' LIMIT 1")["document_id"]
    decide(document_id, "RETIRED")
    knowledge.seed_knowledge(store.db)
    assert store.db.one("SELECT status FROM knowledge_documents WHERE document_id = ? AND is_current = 1", (document_id,))["status"] == "RETIRED"


def test_citations_carry_their_document_version_and_source_link():
    hit = knowledge.retrieve(store.db, "học liệu SQL")[0]
    assert hit["source_id"] == "S1" and hit["document_id"] and hit["version"] >= 1 and hit["kind"] and hit["heading"]
    assert any(item["source_url"] for item in knowledge.retrieve(store.db, "học liệu SQL"))


@pytest.mark.parametrize("question", ["công thức nấu phở bò ngon", "giá vàng hôm nay", "quantum entanglement theory"])
def test_a_question_outside_the_knowledge_base_finds_nothing(question):
    assert knowledge.retrieve(store.db, question) == []


def test_a_question_of_only_common_words_needs_them_together():
    assert knowledge.retrieve(store.db, "là gì") == []


def test_no_question_bank_or_exam_content_is_in_the_knowledge_base():
    text = " ".join(all_chunks().split())
    bank = json.loads((DATA / "question_bank_v1.json").read_text(encoding="utf-8"))
    exam = json.loads((DATA / "exam_items_v5.json").read_text(encoding="utf-8"))
    for item in bank["items"]:
        assert " ".join(item["stem"].split()) not in text
        assert not item.get("explanation") or " ".join(item["explanation"].split()) not in text
    for item in exam["items"]:
        assert " ".join(item["prompt"].split()) not in text
        for case in item["cases"]:
            # Descriptions are short generic labels that may echo the public rubric; solutions may not appear.
            assert not case.get("expected_sql") or " ".join(case["expected_sql"].split()) not in text


def test_a_search_with_an_exam_prompt_returns_no_exam_text():
    exam = json.loads((DATA / "exam_items_v5.json").read_text(encoding="utf-8"))
    for item in exam["items"]:
        for hit in knowledge.retrieve(store.db, item["prompt"]):
            assert hit["kind"] not in {"EXAM", "QUESTION_BANK"} and " ".join(item["prompt"].split()) not in " ".join(hit["content"].split())


def test_an_upload_that_repeats_exam_content_is_refused():
    exam = json.loads((DATA / "exam_items_v5.json").read_text(encoding="utf-8"))
    response = client.post(f"{A}/admin/knowledge", json={"title": "Đề rò rỉ", "body": f"Tài liệu ôn tập.\n{exam['items'][0]['prompt']}"}, headers=ADMIN)
    assert response.status_code == 422 and "ngân hàng đề" in response.json()["error"]["message"]
    bank = json.loads((DATA / "question_bank_v1.json").read_text(encoding="utf-8"))
    stem = next(item["stem"] for item in bank["items"] if len(item["stem"]) >= 40)
    assert client.post(f"{A}/admin/knowledge", json={"title": "Đề rò rỉ", "body": stem.upper()}, headers=ADMIN).status_code == 422


def test_a_learner_imported_jd_never_enters_shared_knowledge():
    jd = "Vị trí: Data Analyst tại CongTyRiengTuXYZ. Yêu cầu SQL và Python, liên hệ bimatnoibo@example.com"
    assert client.post("/jds/import", data={"text": jd, "title": "JD riêng"}, headers=STUDENT).status_code in {200, 201}
    assert "CongTyRiengTuXYZ" not in all_chunks()
    assert knowledge.retrieve(store.db, "CongTyRiengTuXYZ bimatnoibo") == []


def test_only_admins_manage_knowledge():
    assert client.get(f"{A}/admin/knowledge", headers=STUDENT).status_code == 403
    assert client.post(f"{A}/admin/knowledge", json={"title": "abc", "body": "x" * 30}, headers=STUDENT).status_code == 403
    assert client.post(f"{A}/admin/knowledge/skill-SQL/decision", json={"status": "RETIRED"}, headers=STUDENT).status_code == 403
    assert client.get(f"{A}/admin/usage", headers=STUDENT).status_code == 403


def test_hybrid_retrieval_finds_by_meaning_when_keywords_miss(monkeypatch):
    use_fake(monkeypatch)
    assert knowledge.embed_pending(store.db, limit=500) > 0
    hit = knowledge.retrieve(store.db, "sql")[0]
    assert hit["method"] == "HYBRID"
    meaning_only = knowledge.retrieve(store.db, "sql truyvankhongtontai123 abcxyz456 khongkhop789")
    assert meaning_only and {item["method"] for item in meaning_only} == {"VECTOR"}


def test_retrieval_falls_back_to_keywords_when_embedding_fails(monkeypatch):
    fake = use_fake(monkeypatch)
    knowledge.embed_pending(store.db, limit=500)
    fake.embed_error = GatewayError("hỏng", "AI_UNAVAILABLE")
    hits = knowledge.retrieve(store.db, "học liệu SQL")
    assert hits and {item["method"] for item in hits} == {"KEYWORD"}


def test_vectors_of_another_model_are_not_compared(monkeypatch):
    fake = use_fake(monkeypatch)
    knowledge.embed_pending(store.db, limit=500)
    monkeypatch.setattr(fake, "default_embedding_model", "fake-embedding-2")
    assert knowledge.retrieve(store.db, "sql truyvankhongtontai123 abcxyz456 khongkhop789") == []
    assert knowledge.embed_pending(store.db, limit=500) > 0


def test_migration_adds_the_ai_tables_with_a_backup_and_keeps_every_row(tmp_path):
    path = tmp_path / "old.sqlite3"
    old = Database(path)
    old.execute("INSERT INTO learner_state(user_id, payload, updated_at) VALUES ('u', '{}', 'now')")
    old.execute("INSERT INTO history_events(event_id, user_id, event, time) VALUES ('e', 'u', 'x', 'now')")
    for table in ("ai_messages", "ai_conversations", "knowledge_chunks_fts", "knowledge_chunks", "knowledge_documents", "ai_usage_traces"):
        old.execute(f"DROP TABLE {table}")
    old.execute("DELETE FROM meta WHERE key = 'ai_schema_version'")
    old.close()
    upgraded = Database(path)
    assert upgraded.get_meta("ai_schema_version") == "1" and upgraded.get_meta("schema_version") == str(SCHEMA_VERSION)
    assert upgraded.one("SELECT COUNT(*) AS n FROM learner_state")["n"] == 1 and upgraded.one("SELECT COUNT(*) AS n FROM history_events")["n"] == 1
    assert upgraded.one("SELECT COUNT(*) AS n FROM ai_conversations")["n"] == 0
    upgraded.close()
    backup = tmp_path / "old.sqlite3.pre-ai1.bak"
    assert backup.exists()
    copy = sqlite3.connect(backup)
    assert copy.execute("SELECT COUNT(*) FROM learner_state").fetchone()[0] == 1
    assert not copy.execute("SELECT 1 FROM sqlite_master WHERE name = 'ai_conversations'").fetchone()
    copy.close()


def test_a_second_start_does_not_migrate_again(tmp_path):
    path = tmp_path / "db.sqlite3"
    Database(path).close()
    backup = tmp_path / "db.sqlite3.pre-ai1.bak"
    backup.unlink()
    Database(path).close()
    assert not backup.exists()


def test_clearing_the_test_database_keeps_the_search_index_working():
    store.db.clear()
    knowledge.seed_knowledge(store.db)
    assert knowledge.retrieve(store.db, "học liệu SQL")
