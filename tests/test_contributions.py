"""Question contributions (5.35): rights, automatic checks, review with four eyes, publishing and use in exams.
5.36: the reviewer checklist and the optional English version.

The questions written here are test fixtures, not bank content: they exist only in the in-memory test database.
"""
import copy

import pytest

from backend.engine.exam_grader import BANK, plan_questions, verify_exam
from backend.store import store
from v5_helpers import ADMIN, STUDENT, STUDENT_2, STUDENT_ID, client

A = "/api/v1"
STUDENT_2_ID = "22222222-2222-2222-2222-222222222222"
ADMIN_ID = "99999999-9999-9999-9999-999999999999"

EXAM_PAYLOAD = {
    "topic": "Đếm đơn hoàn thành", "answer_type": "sql", "workspace": "sql", "minutes": 6, "max_chars": 2000, "placeholder": "SELECT ...",
    "prompt": "Từ bảng orders_raw, viết truy vấn đếm số dòng có status = 'completed'. Kết quả là một ô duy nhất.",
    "cases": [
        {"id": "runs", "type": "sql_runs", "points": 10, "description": "Câu truy vấn chạy được và trả về dữ liệu"},
        {"id": "result", "type": "sql_result", "points": 90, "expected_sql": "SELECT COUNT(*) FROM orders_raw WHERE status = 'completed'", "description": "Đếm đúng số dòng hoàn thành"},
    ],
    "reference_answers": {"*": "SELECT COUNT(*) FROM orders_raw WHERE status = 'completed';"},
}
TEST_PAYLOAD = {
    "type": "single", "topic": "Lọc dữ liệu", "stem": "Mệnh đề nào trong SQL dùng để lọc các dòng trước khi nhóm dữ liệu lại với nhau?",
    "options": [{"id": "a", "text": "WHERE"}, {"id": "b", "text": "HAVING"}, {"id": "c", "text": "ORDER BY"}, {"id": "d", "text": "LIMIT"}],
    "answer": "a", "explanation": "WHERE lọc từng dòng trước GROUP BY; HAVING lọc các nhóm sau khi đã gộp.",
}


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield
    store.reset()


def grant(user_id=STUDENT_ID):
    response = client.post(f"{A}/admin/contributors", json={"user_id": str(user_id)}, headers=ADMIN)
    assert response.status_code == 201, response.text


def draft(payload=None, bank="EXAM", skill="SQL", level=1, headers=STUDENT):
    response = client.post(f"{A}/contributions", json={"bank": bank, "skill_code": skill, "level": level, "payload": payload or EXAM_PAYLOAD}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def check(contribution, headers=STUDENT):
    response = client.post(f"{A}/contributions/{contribution['contribution_id']}/check", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["validation"]


def submitted(payload=None, bank="EXAM", skill="SQL", level=1):
    grant()
    item = draft(payload, bank, skill, level)
    response = client.post(f"{A}/contributions/{item['contribution_id']}/submit", headers=STUDENT)
    assert response.status_code == 200, response.text
    return response.json()


def approve(contribution, headers=ADMIN, note="", checklist="all"):
    """A reviewer who confirms every checklist point (5.36) unless the test passes its own checklist."""
    if checklist == "all":
        view = client.get(f"{A}/admin/contributions/{contribution['contribution_id']}", headers=ADMIN).json()
        checklist = {item["key"]: True for item in view["review_items"]}
    return client.post(f"{A}/admin/contributions/{contribution['contribution_id']}/decision", json={"decision": "APPROVE", "note": note, "checklist": checklist}, headers=headers)


# --- Rights ---

def test_only_a_granted_account_can_contribute_and_the_right_can_be_withdrawn():
    assert client.get(f"{A}/contributions/meta", headers=STUDENT).status_code == 403
    assert client.post(f"{A}/contributions", json={"bank": "EXAM", "skill_code": "SQL", "level": 1, "payload": EXAM_PAYLOAD}, headers=STUDENT).status_code == 403
    grant()
    assert client.get(f"{A}/contributions/meta", headers=STUDENT).status_code == 200
    assert client.post(f"{A}/admin/contributors", json={"user_id": STUDENT_ID.hex}, headers=STUDENT).status_code == 403
    assert client.delete(f"{A}/admin/contributors/{STUDENT_ID}", headers=ADMIN).status_code == 200
    assert client.get(f"{A}/contributions/mine", headers=STUDENT).status_code == 403


def test_the_coverage_shows_how_many_questions_each_cell_holds():
    grant()
    meta = client.get(f"{A}/contributions/meta", headers=STUDENT).json()
    assert meta["coverage"]["exam"]["SQL"] == {"1": 1, "2": 1, "3": 1}
    assert set(meta["datasets"]) == set(BANK["datasets"]) and meta["datasets"]["A"]["columns"]
    assert "sql_result" in meta["case_types"]["sql"]


def test_another_account_cannot_see_or_change_my_question():
    grant()
    grant(STUDENT_2_ID)
    mine = draft()
    path = f"{A}/contributions/{mine['contribution_id']}"
    assert client.get(path, headers=STUDENT_2).status_code == 404
    assert client.put(path, json={"bank": "EXAM", "skill_code": "SQL", "level": 1, "payload": EXAM_PAYLOAD}, headers=STUDENT_2).status_code == 404
    assert client.post(f"{path}/submit", headers=STUDENT_2).status_code == 404
    assert client.delete(path, headers=STUDENT_2).status_code == 404


# --- Automatic checks ---

def test_a_sound_question_passes_every_check_on_all_four_datasets():
    grant()
    report = check(draft())
    assert report["ok"] is True and report["errors"] == []
    assert set(report["datasets"]) == set(BANK["datasets"])
    assert all(entry["score"] == 100 for entry in report["datasets"].values())
    assert report["weak"] and all(entry["score"] < 40 for entry in report["weak"])


@pytest.mark.parametrize("change, message", [
    (lambda p: p["cases"][1].update(points=80), "Tổng điểm"),
    (lambda p: p["cases"][1].update(type="text_ids"), "không dùng cho bài sql"),
    (lambda p: p["cases"][1].pop("expected_sql"), "cần trường expected_sql"),
    (lambda p: p["cases"].__setitem__(1, {"id": "x", "type": "code_regex", "points": 90, "pattern": "(a+)+$", "description": "Mẫu nguy hiểm"}), "lồng nhau"),
    (lambda p: p.update(cases=[{"id": "runs", "type": "sql_runs", "points": 100, "description": "Chạy được là đủ"}]), "không chỉ"),
    (lambda p: p.update(reference_answers={}), "đáp án mẫu"),
    (lambda p: p.update(workspace="python"), "Không gian làm bài"),
])
def test_structural_mistakes_are_reported_and_block_sending(change, message):
    grant()
    payload = copy.deepcopy(EXAM_PAYLOAD)
    change(payload)
    item = draft(payload)
    report = check(item)
    assert report["ok"] is False and any(message in error for error in report["errors"]), report["errors"]
    assert client.post(f"{A}/contributions/{item['contribution_id']}/submit", headers=STUDENT).status_code == 422
    assert client.get(f"{A}/contributions/{item['contribution_id']}", headers=STUDENT).json()["status"] == "DRAFT"


def test_a_reference_answer_that_does_not_score_full_marks_is_caught():
    grant()
    payload = copy.deepcopy(EXAM_PAYLOAD)
    payload["reference_answers"] = {"*": "SELECT COUNT(*) FROM orders_raw;"}
    report = check(draft(payload))
    assert not report["ok"] and any("đáp án mẫu chỉ đạt" in error for error in report["errors"])


def test_a_question_that_a_wrong_answer_passes_is_refused():
    grant()
    payload = copy.deepcopy(EXAM_PAYLOAD)
    # "Some rows come back" is all this asks, so selecting the whole table already scores.
    payload["cases"] = [{"id": "runs", "type": "sql_runs", "points": 50, "description": "Câu truy vấn chạy được"},
                        {"id": "rows", "type": "sql_contains", "points": 50, "expected_sql": "SELECT order_id FROM orders_raw LIMIT 1", "description": "Có mã đơn đầu tiên"}]
    payload["reference_answers"] = {"*": "SELECT * FROM orders_raw;"}
    report = check(draft(payload))
    assert not report["ok"] and any("quá dễ đạt" in error for error in report["errors"])


def test_a_copy_of_a_bank_question_is_refused_and_a_near_copy_is_flagged():
    grant()
    seed = next(item for item in BANK["items"] if item["item_id"] == "SQL-2")
    copied = draft({**copy.deepcopy(EXAM_PAYLOAD), "prompt": seed["prompt"]})
    report = check(copied)
    assert not report["ok"] and any("trùng nội dung" in error for error in report["errors"])
    near = draft({**copy.deepcopy(EXAM_PAYLOAD), "prompt": seed["prompt"].replace("theo từng vùng", "theo từng khu vực")})
    report = check(near)
    assert report["similar"] and report["similar"][0]["ref"] == "SQL-2"


def test_a_multiple_choice_question_is_checked_like_the_admin_editor_does():
    grant()
    assert check(draft(TEST_PAYLOAD, bank="TEST", level=2))["ok"] is True
    broken = {**copy.deepcopy(TEST_PAYLOAD), "answer": "z"}
    report = check(draft(broken, bank="TEST", level=2))
    assert not report["ok"] and any("Đáp án phải là id" in error for error in report["errors"])
    no_reason = {**copy.deepcopy(TEST_PAYLOAD), "explanation": "Vì vậy."}
    assert any("giải thích" in error for error in check(draft(no_reason, bank="TEST", level=2))["errors"])


def test_editing_clears_the_last_check():
    grant()
    item = draft()
    check(item)
    updated = client.put(f"{A}/contributions/{item['contribution_id']}", json={"bank": "EXAM", "skill_code": "SQL", "level": 1, "payload": EXAM_PAYLOAD}, headers=STUDENT).json()
    assert updated["validation"] is None


# --- Review ---

def test_a_reviewer_must_give_a_reason_to_send_back_or_reject():
    item = submitted()
    path = f"{A}/admin/contributions/{item['contribution_id']}/decision"
    assert client.post(path, json={"decision": "REJECT", "note": ""}, headers=ADMIN).status_code == 422
    back = client.post(path, json={"decision": "REQUEST_CHANGES", "note": "Hãy nói rõ cột status có thể viết hoa."}, headers=ADMIN).json()
    assert back["status"] == "CHANGES_REQUESTED" and back["review_note"].startswith("Hãy nói rõ")
    again = client.post(f"{A}/contributions/{item['contribution_id']}/submit", headers=STUDENT).json()
    assert again["status"] == "SUBMITTED" and again["revision"] == 2


def test_nobody_approves_their_own_question():
    item = draft(headers=ADMIN)  # administrators may write questions too
    client.post(f"{A}/contributions/{item['contribution_id']}/submit", headers=ADMIN)
    response = approve(item)
    assert response.status_code == 403
    assert client.get(f"{A}/admin/contributions/{item['contribution_id']}", headers=ADMIN).json()["status"] == "SUBMITTED"


def test_a_learner_cannot_review():
    item = submitted()
    assert approve(item, headers=STUDENT).status_code == 403
    assert client.get(f"{A}/admin/contributions", headers=STUDENT).status_code == 403


def test_a_withdrawn_question_can_be_edited_again():
    item = submitted()
    assert client.post(f"{A}/contributions/{item['contribution_id']}/withdraw", headers=STUDENT).json()["status"] == "DRAFT"
    assert client.put(f"{A}/contributions/{item['contribution_id']}", json={"bank": "EXAM", "skill_code": "SQL", "level": 1, "payload": EXAM_PAYLOAD}, headers=STUDENT).status_code == 200


# --- Publishing and use ---

def test_an_approved_exam_question_joins_the_draw_but_never_for_its_author():
    item = submitted()
    published = approve(item).json()
    assert published["status"] == "APPROVED" and published["published_item_id"].startswith("C-SQL-1-")
    item_id = published["published_item_id"]
    requirements = {"SQL": {"weight": 1, "target_level": 1}}
    drawn = {plan_questions(requirements, {}, set(), seed)[0]["item_id"].rsplit("-", 1)[0] for seed in range(40)}
    assert drawn == {"SQL-1", item_id}
    mine = {plan_questions(requirements, {}, set(), seed, author_id=str(STUDENT_ID))[0]["item_id"].rsplit("-", 1)[0] for seed in range(40)}
    assert mine == {"SQL-1"}
    meta = client.get(f"{A}/contributions/meta", headers=STUDENT).json()
    assert meta["coverage"]["exam"]["SQL"]["1"] == 2


def test_a_learner_who_met_the_seed_question_gets_the_new_one_and_it_grades():
    published = approve(submitted()).json()
    requirements = {"SQL": {"weight": 1, "target_level": 1}}
    seen = {f"SQL-1-{variant}" for variant in BANK["datasets"]}
    questions = plan_questions(requirements, {}, seen, 7)
    assert questions[0]["item_id"].startswith(published["published_item_id"])
    result = verify_exam(questions, {questions[0]["question_id"]: EXAM_PAYLOAD["reference_answers"]["*"]})
    assert result["skill_results"]["SQL"]["level"] == 1 and result["skill_results"]["SQL"]["score"] == 1.0
    wrong = verify_exam(questions, {questions[0]["question_id"]: "SELECT 1;"})
    assert wrong["skill_results"]["SQL"]["level"] == 0


def test_a_retired_question_leaves_the_draw():
    published = approve(submitted()).json()
    assert client.post(f"{A}/admin/contributions/{published['contribution_id']}/retire", json={"note": "Đề lộ"}, headers=ADMIN).json()["status"] == "RETIRED"
    drawn = {plan_questions({"SQL": {"weight": 1, "target_level": 1}}, {}, set(), seed)[0]["item_id"].rsplit("-", 1)[0] for seed in range(20)}
    assert drawn == {"SQL-1"}


def test_an_approved_multiple_choice_question_enters_the_test_bank():
    published = approve(submitted(TEST_PAYLOAD, bank="TEST", level=2)).json()
    item = store.get_question_item(published["published_item_id"])
    assert item["status"] == "ACTIVE" and item["author_id"] == str(STUDENT_ID) and item["answer"] == "a"
    client.post(f"{A}/admin/contributions/{published['contribution_id']}/retire", json={"note": ""}, headers=ADMIN)
    assert store.get_question_item(published["published_item_id"])["status"] == "RETIRED"


def test_erasing_an_account_keeps_published_questions_without_the_name():
    published = approve(submitted()).json()
    grant()
    draft_id = draft({**copy.deepcopy(EXAM_PAYLOAD), "prompt": EXAM_PAYLOAD["prompt"] + " Ghi rõ tên cột."})["contribution_id"]
    store.purge_user_data(STUDENT_ID)
    assert store.db.one("SELECT 1 AS x FROM question_contributions WHERE contribution_id = ?", (draft_id,)) is None
    kept = store.db.one("SELECT author_name, status FROM question_contributions WHERE contribution_id = ?", (published["contribution_id"],))
    assert kept == {"author_name": None, "status": "APPROVED"}
    assert store.db.one("SELECT status FROM exam_bank_items WHERE item_id = ?", (published["published_item_id"],))["status"] == "ACTIVE"


def test_the_signed_in_user_says_whether_they_may_contribute():
    me = lambda: client.get(f"{A}/auth/me", headers=STUDENT)
    assert me().status_code in (200, 401)  # demo tokens have no account row; the flag is read from the grant table
    from backend.contributions import is_contributor

    assert is_contributor(STUDENT_ID) is False
    grant()
    assert is_contributor(STUDENT_ID) is True


# --- 5.36: reviewer checklist ---

def test_approval_needs_every_reviewer_confirmation_and_records_it():
    item = submitted()
    assert approve(item, checklist={}).status_code == 422
    assert approve(item, checklist={"correct": True, "clear": True, "level": True}).status_code == 422
    still = client.get(f"{A}/admin/contributions/{item['contribution_id']}", headers=ADMIN).json()
    assert still["status"] == "SUBMITTED" and still["published_item_id"] is None
    assert [check["key"] for check in still["review_items"]] == ["correct", "clear", "level", "safe"]
    done = approve(item).json()
    assert done["status"] == "APPROVED" and done["review_checklist"]["items"] == ["correct", "clear", "level", "safe"]


def test_a_checklist_value_must_be_a_real_yes():
    item = submitted()
    response = approve(item, checklist={"correct": True, "clear": True, "level": True, "safe": False})
    assert response.status_code == 422


def test_sending_back_needs_no_checklist():
    item = submitted()
    path = f"{A}/admin/contributions/{item['contribution_id']}/decision"
    assert client.post(path, json={"decision": "REJECT", "note": "Câu này trùng ý với bài SQL-1."}, headers=ADMIN).json()["status"] == "REJECTED"


# --- 5.36: English version ---

EXAM_ENGLISH = {
    "topic": "Count completed orders", "placeholder": "SELECT ...",
    "prompt": "From table orders_raw, write a query that counts the rows with status = 'completed'. The result is a single cell.",
    "cases.runs": "The query runs and returns data", "cases.result": "Counts the completed rows correctly",
}
TEST_ENGLISH = {"topic": "Filtering data", "stem": "Which SQL clause filters rows before the data is grouped together?",
                "explanation": "WHERE filters each row before GROUP BY; HAVING filters groups after they are formed."}


def test_without_english_the_question_is_valid_and_the_author_is_told():
    grant()
    report = check(draft())
    assert report["ok"] and report["english"]["given"] == 0 and any("tiếng Anh" in warning for warning in report["warnings"])


@pytest.mark.parametrize("english, message", [
    ({"topic": "Count completed orders"}, "còn thiếu"),
    ({**EXAM_ENGLISH, "prompt": "Từ bảng orders_raw, count the rows."}, "còn chữ tiếng Việt"),
    ({**EXAM_ENGLISH, "cases.old_id": "Something"}, "không còn trong câu"),
    ({**EXAM_ENGLISH, "topic": "x" * 400}, "dài bất thường"),
])
def test_a_partial_or_wrong_english_version_blocks_sending(english, message):
    grant()
    item = draft({**EXAM_PAYLOAD, "en": english})
    report = check(item)
    assert not report["ok"] and any(message in error for error in report["errors"]), report["errors"]
    assert client.post(f"{A}/contributions/{item['contribution_id']}/submit", headers=STUDENT).status_code == 422


def test_a_complete_english_version_passes_and_the_reviewer_must_confirm_it():
    grant()
    item = draft({**EXAM_PAYLOAD, "en": {**EXAM_ENGLISH, "unused": "  "}})
    report = check(item)
    assert report["ok"] and report["english"] == {"needed": 4, "given": 4, "complete": True}
    stored = client.get(f"{A}/contributions/{item['contribution_id']}", headers=STUDENT).json()["payload"]["en"]
    assert "unused" not in stored  # blank entries are dropped
    client.post(f"{A}/contributions/{item['contribution_id']}/submit", headers=STUDENT)
    view = client.get(f"{A}/admin/contributions/{item['contribution_id']}", headers=ADMIN).json()
    assert "english" in [check["key"] for check in view["review_items"]]
    assert approve(item, checklist={"correct": True, "clear": True, "level": True, "safe": True}).status_code == 422
    assert approve(item).status_code == 200


def test_an_english_version_must_be_text_pairs():
    grant()
    response = client.post(f"{A}/contributions", json={"bank": "EXAM", "skill_code": "SQL", "level": 1, "payload": {**EXAM_PAYLOAD, "en": {"topic": ["x"]}}}, headers=STUDENT)
    assert response.status_code == 422


def test_approved_english_is_served_and_drafts_are_not():
    from backend import i18n
    from backend.engine.test_engine import public_item

    grant()
    waiting = draft({**TEST_PAYLOAD, "en": TEST_ENGLISH}, bank="TEST", level=2)
    try:
        i18n.set_language("en")
        assert i18n.localize({"stem": TEST_PAYLOAD["stem"]})["stem"] == TEST_PAYLOAD["stem"]  # not approved yet
        assert client.post(f"{A}/contributions/{waiting['contribution_id']}/submit", headers=STUDENT).status_code == 200
        assert approve(waiting).status_code == 200
        published = client.get(f"{A}/admin/contributions/{waiting['contribution_id']}", headers=ADMIN).json()
        i18n.set_language("en")
        shown = i18n.localize(public_item(store.get_question_item(published["published_item_id"])))
        assert shown["stem"] == TEST_ENGLISH["stem"] and shown["topic"] == TEST_ENGLISH["topic"]
        assert [option["text"] for option in shown["options"]] == ["WHERE", "HAVING", "ORDER BY", "LIMIT"]
        assert i18n.localize(TEST_PAYLOAD["explanation"]) == TEST_ENGLISH["explanation"]
        assert i18n.should_translate("/api/v1/tests/attempts")
        i18n.set_language("vi")
        assert not i18n.should_translate("/api/v1/tests/attempts")  # Vietnamese responses are never rewritten
    finally:
        i18n.set_language("vi")


def test_an_approved_exam_question_reaches_english_learners_in_english():
    from backend import i18n

    published = approve(submitted({**EXAM_PAYLOAD, "en": EXAM_ENGLISH})).json()
    seen = {f"SQL-1-{variant}" for variant in BANK["datasets"]}
    question = plan_questions({"SQL": {"weight": 1, "target_level": 1}}, {}, seen, 3)[0]
    assert question["item_id"].startswith(published["published_item_id"])
    try:
        i18n.set_language("en")
        shown = i18n.localize(question)
    finally:
        i18n.set_language("vi")
    assert shown["prompt"] == EXAM_ENGLISH["prompt"] and shown["topic"] == EXAM_ENGLISH["topic"]
    assert [case["description"] for case in shown["cases"]] == [EXAM_ENGLISH["cases.runs"], EXAM_ENGLISH["cases.result"]]
    assert question["prompt"] == EXAM_PAYLOAD["prompt"]  # grading and storage keep the Vietnamese


def test_a_choice_is_translated_but_what_a_learner_wrote_is_not():
    from backend import i18n

    source = "Báo lỗi"
    assert source in i18n.catalog()
    try:
        i18n.set_language("en")
        assert i18n.localize({"options": [{"id": "d", "text": source}]})["options"][0]["text"] == i18n.catalog()[source]
        assert i18n.localize({"id": "q1", "text": source, "kind": "note"})["text"] == source
        assert i18n.localize({"answer_text": source})["answer_text"] == source
    finally:
        i18n.set_language("vi")


# --- 5.36: migration ---

def test_a_version_one_database_gains_the_checklist_column_and_keeps_its_rows(tmp_path):
    import sqlite3

    from backend.database import Database

    path = tmp_path / "v1.sqlite3"
    Database(path).close()
    raw = sqlite3.connect(path)
    # Rebuild the table as version 1 had it (no review_checklist) and put a row in it.
    raw.executescript("""
        DROP TABLE contribution_events; DROP TABLE exam_bank_items; DROP TABLE question_contributions;
        CREATE TABLE question_contributions (
            contribution_id TEXT PRIMARY KEY, bank TEXT NOT NULL CHECK (bank IN ('EXAM', 'TEST')), author_id TEXT NOT NULL, author_name TEXT,
            skill_code TEXT NOT NULL, level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 3), status TEXT NOT NULL, payload TEXT NOT NULL,
            validation TEXT, fingerprint TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, review_note TEXT, reviewer_id TEXT,
            published_item_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, submitted_at TEXT, decided_at TEXT);
        INSERT INTO question_contributions(contribution_id, bank, author_id, skill_code, level, status, payload, fingerprint, created_at, updated_at)
            VALUES ('c-1', 'EXAM', 'u-1', 'SQL', 1, 'DRAFT', '{}', 'f', '2026-11-15', '2026-11-15');
        UPDATE meta SET value = '1' WHERE key = 'contrib_schema_version';
    """)
    raw.commit()
    raw.close()
    upgraded = Database(path)
    columns = {row["name"] for row in upgraded.query("PRAGMA table_info(question_contributions)")}
    assert "review_checklist" in columns and upgraded.get_meta("contrib_schema_version") == "2"
    assert upgraded.one("SELECT status, review_checklist FROM question_contributions WHERE contribution_id = 'c-1'") == {"status": "DRAFT", "review_checklist": None}
    upgraded.close()
    again = Database(path)  # running twice changes nothing
    assert again.one("SELECT COUNT(*) AS n FROM question_contributions")["n"] == 1
    again.close()
