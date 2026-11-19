"""English mode: complete catalogs, exam text kept private, grading in English, stored source unchanged."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import i18n_extract  # noqa: E402
from ai_helpers import call, use_fake  # noqa: E402
from backend import i18n  # noqa: E402
from backend.ai_service import tool_registry  # noqa: E402
from backend.ai_service.career_context import ToolContext  # noqa: E402
from backend.engine.exam_grader import BANK, evaluate_question  # noqa: E402
from backend.store import store  # noqa: E402
from v5_helpers import ADMIN, FACTS, P, STUDENT, STUDENT_ID, answer_all, client, complete_process, questions_of, to_exam  # noqa: E402

PUBLIC = json.loads((ROOT / "frontend" / "js" / "lang" / "en.json").read_text(encoding="utf-8"))
PRIVATE = json.loads((ROOT / "data" / "i18n" / "sensitive_en.json").read_text(encoding="utf-8"))
NOT_DISPLAYED = set((ROOT / "tests" / "i18n_not_displayed.txt").read_text(encoding="utf-8").splitlines())
A = "/api/v1/assistant"
EN = {**STUDENT, "X-Language": "en"}


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield
    store.reset()


def uncovered(strings: set[str], catalog: dict) -> list[str]:
    return sorted(item for item in strings if item not in catalog and item not in NOT_DISPLAYED)


def test_every_interface_string_has_a_translation():
    assert uncovered(i18n_extract.ui_catalog(), PUBLIC) == []


def test_every_server_message_has_a_translation():
    assert uncovered(i18n_extract.backend_catalog(), PUBLIC) == []


def test_all_catalog_content_has_a_translation():
    assert uncovered(i18n_extract.data_catalog(), PUBLIC) == []


def test_all_exam_content_has_a_private_translation():
    assert uncovered(i18n_extract.sensitive_catalog(), PRIVATE) == []


@pytest.mark.parametrize("catalog", [PUBLIC, PRIVATE], ids=["public", "private"])
def test_no_translation_contains_vietnamese_and_placeholders_match(catalog):
    for source, target in catalog.items():
        assert not i18n_extract.VI.search(target), target
        assert sorted(re.findall(r"\{\d+\}", source)) == sorted(re.findall(r"\{\d+\}", target)), source


def test_the_public_catalog_holds_no_exam_content():
    served = json.dumps(PUBLIC, ensure_ascii=False)
    for item in BANK["items"]:
        assert item["prompt"] not in served and PRIVATE[item["prompt"]] not in served


def test_the_public_catalog_holds_no_question_bank_text():
    bank = json.loads((ROOT / "data" / "question_bank_v1.json").read_text(encoding="utf-8"))
    for item in bank["items"]:
        assert item["stem"] not in PUBLIC and PRIVATE.get(item["stem"], "\0") not in PUBLIC.values()


def test_the_private_catalog_is_for_admins_only():
    assert client.get("/api/v1/i18n/private-catalog", headers=STUDENT).status_code == 403
    assert client.get("/api/v1/i18n/private-catalog").status_code == 401
    assert client.get("/api/v1/i18n/private-catalog", headers=ADMIN).status_code == 200
    assert client.get("/data/i18n/sensitive_en.json").status_code == 404


def test_the_exam_is_served_in_english_and_stored_in_vietnamese():
    exam = to_exam()
    english = client.get(f"{P}/exam", headers=EN).json()
    assert not i18n_extract.VI.search(json.dumps([{key: item[key] for key in ("prompt", "topic", "placeholder")} for item in english["questions"]], ensure_ascii=False))
    assert i18n_extract.VI.search(client.get(f"{P}/exam", headers=STUDENT).json()["questions"][0]["prompt"])
    assert i18n_extract.VI.search(questions_of(exam["attempt_id"])[0]["prompt"])


def test_a_learners_own_answer_is_never_translated():
    to_exam()
    state = client.get(f"{P}/exam", headers=EN).json()
    text = "Chọn biểu đồ cột vì Biểu đồ cột dễ so sánh"
    question = state["questions"][0]["question_id"]
    assert client.put(f"{P}/exam/responses/{question}", json={"text": text}, headers=EN).status_code == 200
    assert client.get(f"{P}/exam", headers=EN).json()["questions"][0]["answer"] == text


def test_the_review_is_in_english():
    complete_process(kind="wrong")
    review = client.get(f"{P}/exam/review", headers=EN).json()
    assert PRIVATE[next(item["prompt"] for item in BANK["items"] if item["topic"] == review["questions"][0]["topic"] or PRIVATE[item["topic"]] == review["questions"][0]["topic"])] == review["questions"][0]["prompt"]


def test_vietnamese_stays_the_default():
    to_exam()
    assert i18n_extract.VI.search(client.get(f"{P}/exam", headers={**STUDENT, "X-Language": "xx"}).json()["questions"][0]["prompt"])


def test_knowledge_tests_are_served_in_english_and_grade_the_same():
    started = client.post("/api/v1/tests/attempts", json={"blueprint_id": "SKILL_CHECK_SQL"}, headers=EN).json()
    assert not i18n_extract.VI.search(json.dumps([item["stem"] for item in started["items"]], ensure_ascii=False))
    item = started["items"][0]
    chosen = item["options"][0]["id"] if item.get("options") else "1"
    assert client.put(f"/api/v1/tests/attempts/{started['attempt_id']}/responses/{item['item_id']}", json={"value": chosen}, headers=EN).status_code in {200, 422}


ENGLISH = {
    "DQ-2": lambda f: "Initial: 10 rows.\nAfter removing duplicates: 9 rows.\nAfter removing quantity zero: 8 rows.\nKeep completed: 7 rows.",
    "DQ-3": lambda f: f"Before cleaning: {f['raw'].replace('.', ',')}. After cleaning: {f['clean'].replace('.', ',')}. Difference: {f['diff'].replace('.', ',')}. Rules: order_id must be unique; quantity must be greater than 0 with a check constraint.",
    "VIZ-1": lambda f: "I chose a bar chart because it lets us compare revenue across regions. The horizontal axis is the region and the vertical axis is revenue.",
    "VIZ-3": lambda f: f"Main metrics: total net revenue {f['clean'].replace('.', ',')}; orders 7; top region {f['top']}: {f['top_v'].replace('.', ',')}. Use a line chart for the monthly trend and a bar chart to compare regions. Avoid cutting the axis, which starts above zero, because it can mislead.",
    "WC-1": lambda f: f"The first month reached {f['m1'].replace('.', ',')}. The second month reached {f['m2'].replace('.', ',')}. So revenue fell compared with the previous month.",
    "WC-2": lambda f: f"Dear manager. Revenue was {f['m1'].replace('.', ',')} then {f['m2'].replace('.', ',')}, so revenue fell. I recommend reviewing cancelled orders. We have only two months of data, so we cannot conclude the cause.",
    "WC-3": lambda f: f"Summary: revenue fell by {f['pct'].lstrip('-').replace(',', '.')}%.\nFindings: top region {f['top']}: {f['top_v'].replace('.', ',')}.\nRecommendations: the sales team should review this by next week.\nLimitations: only two months of data, so we cannot conclude the cause.",
}


@pytest.mark.parametrize("base", sorted(ENGLISH))
@pytest.mark.parametrize("variant", ["A", "B"])
def test_a_good_english_answer_earns_full_marks(base, variant):
    item = next(entry for entry in BANK["items"] if entry["item_id"] == base)
    question = {**item, "dataset": BANK["datasets"][variant], "gates": item.get("gates", [])}
    outcomes, critical = evaluate_question(question, ENGLISH[base](FACTS[variant]))
    assert [case for case, outcome in outcomes.items() if not outcome["passed"]] == [] and not critical


def test_the_assistant_is_told_to_reply_in_english(monkeypatch):
    fake = use_fake(monkeypatch, ["Hello [[CHAT]]"])
    conversation = client.post(f"{A}/conversations", headers=EN).json()["conversation_id"]
    client.post(f"{A}/conversations/{conversation}/messages", json={"content": "Hi", "page": "dashboard"}, headers=EN)
    assert "write the whole reply in English" in fake.requests[0].system


def test_vietnamese_replies_are_not_told_otherwise(monkeypatch):
    fake = use_fake(monkeypatch, ["Chào [[CHAT]]"])
    conversation = client.post(f"{A}/conversations", headers=STUDENT).json()["conversation_id"]
    client.post(f"{A}/conversations/{conversation}/messages", json={"content": "Chào", "page": "dashboard"}, headers=STUDENT)
    assert "in English" not in fake.requests[0].system


def test_lookup_without_ai_quotes_no_vietnamese_source_in_english():
    conversation = client.post(f"{A}/conversations", headers=EN).json()["conversation_id"]
    message = client.post(f"{A}/conversations/{conversation}/messages", json={"content": "học liệu SQL", "page": "resources"}, headers=EN).json()
    assert message["citations"] and all(item["excerpt"] == "" for item in message["citations"])


def test_tasks_ask_for_english(monkeypatch):
    complete_process()
    fake = use_fake(monkeypatch, [json.dumps({"summary": "You should review gaps.", "points": ["Focus on SQL."], "next_steps": ["Follow the plan."]})])
    assert client.post(f"{A}/tasks/skill_analysis", json={}, headers=EN).json()["message"]["mode"] == "AI"
    assert "Write every field in English." in fake.requests[0].system


def test_tools_keep_returning_the_source_values_for_the_model(monkeypatch):
    complete_process()
    use_fake(monkeypatch, [[call("get_my_skill_gap")], "Done."])
    assert tool_registry.execute("get_my_skill_gap", {}, ToolContext(STUDENT_ID))["data"]["skills"]


def test_answering_in_english_leaves_stored_answers_unchanged():
    exam = to_exam()
    answer_all(exam, headers=EN)
    assert client.post(f"{P}/exam/submit", json={}, headers=EN).status_code == 200
    assert i18n_extract.VI.search(store.db.one("SELECT payload FROM exam_attempts")["payload"])


def test_language_is_reset_between_requests():
    i18n.set_language("en")
    i18n.set_language(None)
    assert i18n.current() == "vi"


def test_scripts_and_styles_are_revalidated_so_updates_reach_the_browser():
    assert client.get("/js/charts.js").headers["cache-control"] == "no-cache"
    assert client.get("/css/app.css").headers["cache-control"] == "no-cache"


def test_only_the_theme_radio_buttons_carry_the_theme_choice_marker():
    boot = (ROOT / "frontend" / "js" / "boot.js").read_text(encoding="utf-8")
    assert "dataset.themeChoice" not in boot and "if (!CHOICES.includes(theme)) return;" in boot


def test_pages_load_the_theme_before_anything_is_painted():
    for page in ("index.html", "login.html"):
        html = (ROOT / "frontend" / page).read_text(encoding="utf-8")
        assert html.index("/js/boot.js") < html.index("stylesheet")
