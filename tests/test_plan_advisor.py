"""5.47: the AI advisor strip of the Career Adapt Plan only hands questions to the real Assistant.

Its buttons name server tasks; each must exist, and every Plan section the strip covers must have an advisor role on
the server, so the Assistant answers in the right role. The strip must not call any endpoint itself.
"""
import re
from pathlib import Path

from backend.ai_service import task_engine
from backend.ai_service.assistant import ADVISORS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "frontend" / "js" / "plan-advisor.js").read_text(encoding="utf-8")
SECTIONS = re.findall(r"^    ([a-z]+): \{$", SOURCE, flags=re.M)


def test_the_strip_covers_every_plan_section():
    assert set(SECTIONS) == {"overview", "exam", "gap", "roadmap", "rank", "progress"}


def test_every_task_button_names_a_real_server_task():
    tasks = re.findall(r'task: "([a-z_]+)"', SOURCE)
    assert tasks, "the strip offers at least one server task"
    assert set(tasks) <= set(task_engine.TASKS)


def test_every_section_has_an_advisor_role_on_the_server():
    for section in SECTIONS:
        assert f"plan_{section}" in ADVISORS


def test_the_strip_only_hands_questions_to_the_assistant():
    # No direct API calls, scores or writes: it imports askAssistant and nothing that talks to the server.
    assert "askAssistant" in SOURCE
    assert not re.search(r"\b(api|fetch|XMLHttpRequest)\s*\(", SOURCE)


def test_the_plan_page_mounts_the_strip_before_the_detail_buttons():
    plan = (ROOT / "frontend" / "js" / "pages" / "plan.js").read_text(encoding="utf-8")
    apply = plan[plan.index("function keepDisclosed"):]
    assert apply.index("mountPlanAdvisor(root, key)") < apply.index("disclose(root, key, PANELS[key])")
