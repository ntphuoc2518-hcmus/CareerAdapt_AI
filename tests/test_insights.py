"""Ranking, salary reference, level guide and result sources (v5.11)."""
from __future__ import annotations

import json
import uuid

from backend import insights
from backend.clock import utcnow
from backend.database import dumps
from backend.levels import LEVEL_NAMES, LEVELS
from backend.store import store
from v4_helpers import ADMIN, STUDENT, STUDENT_ID, client

P = "/api/v1/career-process"
SALARY = {
    "role_label": "Data Analyst", "statistic": "Lương trung vị", "unit": "triệu đồng/tháng",
    "bands": [{"label": "1-2 năm", "value": 20}, {"label": "5-8 năm", "value": 30}],
    "source": {"label": "Báo cáo thử nghiệm", "url": "https://example.org/report", "checked_at": "2026-11-11"},
}


def me() -> str:
    return str(STUDENT_ID)


def add_result(user_id: str, levels: list[int], score: float) -> None:
    """A graded Career Adapt exam, stored the way exam_service stores one."""
    now = utcnow().isoformat()
    run_id, submission_id = str(uuid.uuid4()), str(uuid.uuid4())
    per_skill = {f"S{index}": {"level": level} for index, level in enumerate(levels)}
    with store.db.transaction():
        store.db.execute("INSERT INTO career_runs(run_id, user_id, career_code, status, step, payload, created_at, updated_at, completed_at, archived_at) VALUES (?, ?, 'DATA_ANALYST', 'ARCHIVED', 'DONE', '{}', ?, ?, ?, ?)", (run_id, user_id, now, now, now, now))
        store.db.execute("INSERT INTO exam_attempts(attempt_id, run_id, user_id, status, submission_id, started_at, expires_at, submitted_at, payload) VALUES (?, ?, ?, 'GRADED', ?, ?, ?, ?, '{}')", (str(uuid.uuid4()), run_id, user_id, submission_id, now, now, now))
        # The submission row comes first, as in a real exam: final_assessments refers to it (foreign key since 2026-11-15).
        store.db.execute("INSERT INTO assessment_attempts(submission_id, user_id, task_id, mode, status, submitted_at, updated_at, payload) VALUES (?, ?, 'EXAM', 'ASSESSMENT', 'GRADED', ?, ?, '{}')", (submission_id, user_id, now, now))
        store.db.execute("INSERT INTO final_assessments(submission_id, user_id, task_id, mode, status, final_score, passed, final_level, created_at, updated_at, payload) VALUES (?, ?, 'EXAM', 'ASSESSMENT', 'GRADED', ?, 1, ?, ?, ?, ?)",
                         (submission_id, user_id, score, min(levels), now, now, dumps({"per_skill_results": per_skill})))


def setup_function():
    store.reset()


def test_levels_have_one_name_each_and_the_guide_lists_every_skill():
    assert [item["level"] for item in LEVELS] == [0, 1, 2, 3] and len(set(LEVEL_NAMES.values())) == 4
    guide = client.get(f"{P}/insights", headers=STUDENT).json()["levels"]
    assert [item["name"] for item in guide["scale"]] == [LEVEL_NAMES[level] for level in range(4)]
    assert {item["skill_code"] for item in guide["skills"]} == {skill["skill_code"] for skill in store.skills}
    assert all(item["levels"] for item in guide["skills"])


def test_a_learner_without_a_graded_exam_has_no_position():
    ranking = client.get(f"{P}/insights", headers=STUDENT).json()["ranking"]
    assert ranking["me"] is None and ranking["top_percent"] is None and ranking["board"] == []


def test_ranking_orders_by_verified_levels_then_score_and_ties_share_a_position():
    user = me()
    others = [str(uuid.uuid4()) for _ in range(3)]
    add_result(others[0], [3, 3, 2], 90)
    add_result(others[1], [2, 2, 1], 95)
    add_result(others[2], [2, 2, 1], 95)
    add_result(user, [2, 2, 2], 60)
    ranking = client.get(f"{P}/insights", headers=STUDENT).json()["ranking"]
    assert [row["rank"] for row in ranking["board"]] == [1, 2, 3, 3]
    assert ranking["me"]["rank"] == 2 and ranking["me"]["level_points"] == 6 and ranking["me"]["max_points"] == 9
    # Four people are too few for a percentage.
    assert ranking["total"] == 4 and ranking["enough"] is False and ranking["top_percent"] is None


def test_top_percent_appears_once_enough_learners_are_ranked():
    user = me()
    for index in range(4):
        add_result(str(uuid.uuid4()), [1, 1, 1], 40 + index)
    add_result(user, [3, 3, 3], 100)
    ranking = client.get(f"{P}/insights", headers=STUDENT).json()["ranking"]
    assert ranking["enough"] is True and ranking["me"]["rank"] == 1 and ranking["top_percent"] == 20


def test_only_the_latest_graded_exam_of_a_learner_counts():
    user = me()
    add_result(user, [3, 3, 3], 100)
    add_result(user, [1, 1, 1], 30)
    ranking = client.get(f"{P}/insights", headers=STUDENT).json()["ranking"]
    assert ranking["total"] == 1 and ranking["me"]["score"] == 30


def test_other_learners_are_anonymous_and_never_identified():
    user, other = me(), str(uuid.uuid4())
    add_result(other, [3, 3, 3], 99)
    add_result(user, [1, 1, 1], 50)
    body = client.get(f"{P}/insights", headers=STUDENT)
    rows = body.json()["ranking"]["board"]
    assert rows[0]["name"] == insights.ANONYMOUS and rows[0]["is_me"] is False and rows[1]["name"] == "Bạn"
    assert other not in body.text and "user_id" not in json.dumps(rows) and "email" not in json.dumps(rows)


def test_showing_a_name_is_the_learners_own_choice_and_off_by_default():
    assert client.get(f"{P}/insights", headers=STUDENT).json()["ranking"]["visible"] is False
    assert client.put(f"{P}/leaderboard-visibility", headers=STUDENT, json={"visible": True}).json() == {"visible": True}
    assert client.get(f"{P}/insights", headers=STUDENT).json()["ranking"]["visible"] is True
    assert store.profiles[uuid.UUID(me())][insights.VISIBLE_FIELD] is True
    assert client.put(f"{P}/leaderboard-visibility", headers=STUDENT, json={"visible": "maybe"}).status_code == 422
    assert client.put(f"{P}/leaderboard-visibility", json={"visible": True}).status_code in (401, 403)


def test_salary_reference_carries_its_source_and_a_computed_growth():
    salary = client.get(f"{P}/insights", headers=STUDENT).json()["salary"]
    assert salary["source"]["url"].startswith("https://") and salary["source"]["checked_at"]
    low, high = salary["bands"][0]["value"], salary["bands"][-1]["value"]
    assert salary["growth_percent"] == round((high - low) / low * 100)


def test_salary_without_a_source_is_not_shown():
    store.db.execute("INSERT INTO content_state(key, payload, updated_at) VALUES (?, ?, ?)", (insights.SALARY_KEY, dumps({"bands": [{"label": "x", "value": 10}], "source": {}}), utcnow().isoformat()))
    assert insights.salary_reference() is None
    assert client.get(f"{P}/insights", headers=STUDENT).json()["salary"] is None


def test_only_an_administrator_can_change_the_salary_reference_and_it_must_be_sourced():
    assert client.put(f"{P}/admin/salary-reference", headers=STUDENT, json=SALARY).status_code == 403
    assert client.put(f"{P}/admin/salary-reference", headers=ADMIN, json={**SALARY, "source": {**SALARY["source"], "url": "javascript:alert(1)"}}).status_code == 422
    assert client.put(f"{P}/admin/salary-reference", headers=ADMIN, json={**SALARY, "bands": []}).status_code == 422
    assert client.put(f"{P}/admin/salary-reference", headers=ADMIN, json={**SALARY, "bands": [{"label": "a", "value": -1}]}).status_code == 422
    saved = client.put(f"{P}/admin/salary-reference", headers=ADMIN, json=SALARY)
    assert saved.status_code == 200 and saved.json()["salary"]["growth_percent"] == 50
    assert client.get(f"{P}/insights", headers=STUDENT).json()["salary"]["source"]["label"] == "Báo cáo thử nghiệm"


def test_the_basis_names_where_each_part_of_a_result_comes_from():
    basis = client.get(f"{P}/insights", headers=STUDENT).json()["basis"]
    titles = [item["title"] for item in basis]
    assert titles[:4] == ["Khung kỹ năng", "Mức JD yêu cầu", "Điểm và mức đã xác thực", "Học liệu trong lộ trình"] and "Lương tham khảo" in titles
    assert all(item["detail"] for item in basis)
    assert all(link["url"].startswith("http") for item in basis for link in item["links"])


def test_the_public_introduction_needs_no_account_and_holds_no_api_calls():
    page = client.get("/gioi-thieu")
    assert page.status_code == 200 and "CareerAdapt AI" in page.text and "/api/" not in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert client.get("/", follow_redirects=False).headers["location"] == "/gioi-thieu"


def test_current_ranking_uses_verified_levels_now_and_reports_the_change():
    user = me()
    others = [str(uuid.uuid4()) for _ in range(4)]
    for index, other in enumerate(others):
        add_result(other, [2, 2, 2], 80 - index)
    add_result(user, [0, 0, 0], 40)
    # Since the entry exam the learner verified higher levels through lessons and the final assessment.
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"] = {code: {"level": 3} for code in insights.framework_skills()}
    exam = client.get(f"{P}/insights?rank_basis=exam", headers=STUDENT).json()["ranking"]
    current = client.get(f"{P}/insights?rank_basis=current", headers=STUDENT).json()["ranking"]
    assert exam["me"]["rank"] == 5 and current["me"]["rank"] == 1 and current["rank_change"] == 4
    assert current["me"]["max_points"] == 3 * len(insights.framework_skills())


def test_a_single_skill_ranking_and_the_group_figures_are_aggregates_only():
    user = me()
    for index in range(4):
        add_result(str(uuid.uuid4()), [1, 1, 1], 50 + index)
    add_result(user, [1, 1, 1], 60)
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {"SQL": {"level": 3}}
    ranking = client.get(f"{P}/insights?rank_basis=current&skill=SQL", headers=STUDENT).json()["ranking"]
    assert ranking["skill"] == "SQL" and ranking["me"]["rank"] == 1 and ranking["me"]["max_points"] == 3
    sql = next(item for item in ranking["cohort"] if item["skill_code"] == "SQL")
    assert sql["mine"] == 3 and sql["at_or_below_percent"] == 100 and 0 < sql["average"] < 3
    assert sum(item["count"] for item in ranking["distribution"]) == ranking["total"]
    assert "user_id" not in json.dumps(ranking["cohort"] + ranking["distribution"])
    assert client.get(f"{P}/insights?rank_basis=current&skill=NOPE", headers=STUDENT).status_code == 422
    assert client.get(f"{P}/insights?rank_basis=other", headers=STUDENT).status_code == 422


def test_group_figures_stay_hidden_below_the_minimum_group():
    add_result(me(), [1, 1, 1], 60)
    ranking = client.get(f"{P}/insights?rank_basis=current", headers=STUDENT).json()["ranking"]
    assert ranking["cohort"] == [] and ranking["distribution"] == []


def test_board_pictures_follow_the_name_choice():
    import io
    from PIL import Image
    from backend import accounts
    from backend.avatar import process_avatar

    def picture(color):
        buffer = io.BytesIO()
        Image.new("RGB", (80, 80), color).save(buffer, format="PNG")
        return process_avatar(buffer.getvalue())

    shy, open_ = str(uuid.uuid4()), str(uuid.uuid4())
    add_result(shy, [3, 3, 3], 90)
    add_result(open_, [2, 2, 2], 80)
    add_result(me(), [1, 1, 1], 50)
    # Pictures exist for all three; only "me" and the learner who chose to show their name may appear.
    with accounts.closing(accounts._connect()) as conn:
        for user_id, color in ((shy, (200, 0, 0)), (open_, (0, 200, 0)), (me(), (0, 0, 200))):
            conn.execute("INSERT OR IGNORE INTO accounts(id, email, full_name, role, password_hash, created_at) VALUES (?, ?, 'Học Viên', 'student', 'x', 0)", (user_id, f"{user_id}@example.test"))
            conn.execute("INSERT OR REPLACE INTO account_avatars(user_id, image, updated_at) VALUES (?, ?, ?)", (user_id, picture(color), 1))
    store.get_or_create_profile(uuid.UUID(open_))[insights.VISIBLE_FIELD] = True
    rows = client.get(f"{P}/insights", headers=STUDENT).json()["ranking"]["board"]
    by_rank = {row["rank"]: row for row in rows}
    assert by_rank[1]["avatar"] is None and by_rank[1]["name"] == insights.ANONYMOUS
    assert by_rank[2]["avatar"].startswith("data:image/webp;base64,")
    assert by_rank[3]["is_me"] and by_rank[3]["avatar"].startswith("data:image/webp;base64,")
