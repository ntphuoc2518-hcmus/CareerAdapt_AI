"""Every exam question, on both datasets: a right answer passes, a wrong or blank one does not."""
import pytest

from backend.engine.exam_grader import BANK, build_blueprint, evaluate_question, plan_questions, tier_for_level, validate_bank, verified_level, verify_exam
from backend.engine.rubric_engine import score_submission
from v5_helpers import GOOD, FACTS, WRONG


def question_for(item, variant):
    return {
        **{key: item[key] for key in ("skill_code", "tier", "topic", "prompt", "answer_type", "minutes", "max_chars", "cases")},
        "question_id": "Q1", "label": "Bài 1", "item_id": f"{item['item_id']}-{variant}", "dataset": BANK["datasets"][variant], "gates": item.get("gates", []),
        "placeholder": "", "declared_level": None, "weight": 1.0, "target_level": 2,
    }


CASES = [(item, variant) for item in BANK["items"] for variant in BANK["datasets"]]
IDS = [f"{item['item_id']}-{variant}" for item, variant in CASES]


def earned(question, answer):
    outcomes, violated = evaluate_question(question, answer)
    return sum(case["points"] for case in question["cases"] if outcomes[case["id"]]["passed"]), outcomes, violated


def test_bank_is_consistent_and_complete():
    assert validate_bank() == []
    assert len(BANK["items"]) == 18
    assert {(item["skill_code"], item["tier"]) for item in BANK["items"]} == {(skill, tier) for skill in ("SQL", "DATA_QUALITY", "PYTHON", "DATA_VIZ", "WRITTEN_COMM", "STATISTICS") for tier in (1, 2, 3)}


@pytest.mark.parametrize("item,variant", CASES, ids=IDS)
def test_reference_answer_scores_full_marks(item, variant):
    question = question_for(item, variant)
    points, outcomes, violated = earned(question, GOOD[item["item_id"]](FACTS[variant]))
    assert points == 100, {key: value for key, value in outcomes.items() if not value["passed"]}
    assert violated == []


@pytest.mark.parametrize("item,variant", CASES, ids=IDS)
def test_wrong_answer_does_not_pass(item, variant):
    question = question_for(item, variant)
    points, _, _ = earned(question, WRONG[item["answer_type"]])
    assert points < 40


@pytest.mark.parametrize("item,variant", CASES, ids=IDS)
def test_blank_scores_zero_and_level_zero(item, variant):
    question = question_for(item, variant)
    result = verify_exam([question], {"Q1": "   "})
    assert result["skill_results"][item["skill_code"]]["level"] == 0
    assert not any(case["passed"] for case in result["test_cases"].values())


def test_answers_of_one_dataset_fail_on_the_other():
    item = next(entry for entry in BANK["items"] if entry["item_id"] == "WC-1")
    points, _, _ = earned(question_for(item, "B"), GOOD["WC-1"](FACTS["A"]))
    assert points <= 50


def test_listing_every_order_id_is_not_accepted():
    item = next(entry for entry in BANK["items"] if entry["item_id"] == "DQ-1")
    answer = "ORD001 ORD002 ORD003 ORD004 ORD005 ORD006 ORD007 ORD008 ORD009"
    assert earned(question_for(item, "A"), answer)[0] == 0


def test_sql_answer_is_judged_by_output_not_by_keywords():
    item = next(entry for entry in BANK["items"] if entry["item_id"] == "SQL-2")
    comment_only = "-- SELECT DISTINCT region, SUM(quantity * unit_price * (1 - discount)) GROUP BY region WHERE status = 'completed'\nSELECT 1;"
    assert earned(question_for(item, "A"), comment_only)[0] <= 15


def test_sql_cancelled_orders_trip_the_critical_gate():
    item = next(entry for entry in BANK["items"] if entry["item_id"] == "SQL-2")
    answer = "WITH c AS (SELECT DISTINCT * FROM orders_raw WHERE quantity > 0) SELECT COALESCE(NULLIF(TRIM(region), ''), 'Unknown') AS v, SUM(quantity * unit_price * (1 - discount)) FROM c GROUP BY v;"
    question = question_for(item, "A")
    _, _, violated = earned(question, answer)
    assert violated == ["CG_CANCELLED_INCLUDED"]
    result = verify_exam([question], {"Q1": answer})
    assert result["skill_results"]["SQL"]["level"] <= 1
    scoring = score_submission(build_blueprint([question]), result, [])
    assert scoring["passed"] is False


def test_wrong_trend_trips_the_critical_gate():
    item = next(entry for entry in BANK["items"] if entry["item_id"] == "WC-1")
    answer = GOOD["WC-1"](FACTS["A"]).replace("giảm", "tăng")
    assert earned(question_for(item, "A"), answer)[2] == ["CG_WRONG_TREND"]


def test_sql_injection_style_answer_is_harmless():
    item = next(entry for entry in BANK["items"] if entry["item_id"] == "SQL-1")
    points, outcomes, _ = earned(question_for(item, "A"), "DROP TABLE orders_raw; ATTACH DATABASE 'x.db' AS y;")
    assert points == 0
    assert outcomes["runs"]["passed"] is False


@pytest.mark.parametrize("level,tier", [(None, 1), (0, 1), (1, 1), (2, 2), (3, 3)])
def test_declared_level_sets_difficulty(level, tier):
    assert tier_for_level(level) == tier


@pytest.mark.parametrize("tier,ratio,blank,critical,expected", [
    (1, 1.0, False, False, 1), (1, 0.6, False, False, 0), (2, 1.0, False, False, 2), (2, 0.5, False, False, 1), (2, 0.2, False, False, 0),
    (3, 1.0, False, False, 3), (3, 0.5, False, False, 2), (3, 0.2, False, False, 1), (3, 0.0, False, False, 0), (3, 1.0, True, False, 0), (3, 1.0, False, True, 1),
])
def test_level_is_capped_by_what_the_question_can_prove(tier, ratio, blank, critical, expected):
    assert verified_level(tier, ratio, blank, critical) == expected


def test_question_count_follows_the_jd_and_never_repeats_a_topic():
    two = {"SQL": {"weight": 0.7, "target_level": 2}, "PYTHON": {"weight": 0.3, "target_level": 1}, "DATA_VIZ": {"weight": 0}}
    five = {code: {"weight": 0.2, "target_level": 2} for code in ("SQL", "DATA_QUALITY", "PYTHON", "DATA_VIZ", "WRITTEN_COMM")}
    assert [question["skill_code"] for question in plan_questions(two, {}, set(), 1)] == ["SQL", "PYTHON"]
    questions = plan_questions(five, {"SQL": 3}, set(), 1)
    assert len(questions) == 5 and len({question["skill_code"] for question in questions}) == 5 and len({question["topic"] for question in questions}) == 5
    # Audit A-01 (2026-11-12): difficulty follows the JD level (2 here), not the declared 3.
    assert next(question for question in questions if question["skill_code"] == "SQL")["tier"] == 2


def test_blueprint_points_sum_to_100_with_uneven_weights():
    requirements = {"SQL": {"weight": 0.33, "target_level": 2}, "PYTHON": {"weight": 0.33, "target_level": 1}, "DATA_VIZ": {"weight": 0.34, "target_level": 2}}
    blueprint = build_blueprint(plan_questions(requirements, {}, set(), 3))
    assert round(sum(item["max_points"] for item in blueprint["criteria"]), 2) == 100
    assert round(sum(item["points"] for item in blueprint["test_cases"]), 2) == 100


def test_a_reset_learner_gets_the_other_dataset():
    requirements = {"SQL": {"weight": 1, "target_level": 2}}
    first = plan_questions(requirements, {}, set(), 5)[0]["item_id"]
    second = plan_questions(requirements, {}, {first}, 5)[0]["item_id"]
    assert first != second and first[:-1] == second[:-1]
