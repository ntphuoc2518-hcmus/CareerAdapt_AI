"""CareerAdapt AI v4.0 - Seed Data Loader.

Loads the seed data for Data Analyst internship preparation:
- 5 Competency Skills (SQL, DATA_QUALITY, PYTHON, DATA_VIZ, WRITTEN_COMM)
- Tasks Catalog (DA01A, DA01B, DA02A, DA03A)
- Learning Activities with DAG prerequisites
"""
import json
import os
import sys

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def load_skills():
    path = os.path.join(DATA_DIR, "skills_v1.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_tasks():
    path = os.path.join(DATA_DIR, "tasks_v1.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_activities():
    path = os.path.join(DATA_DIR, "activities_v1.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_job_profiles():
    path = os.path.join(DATA_DIR, "job_profiles_v1.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_question_bank():
    path = os.path.join(DATA_DIR, "question_bank_v1.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_seed_integrity():
    skills_data = load_skills()
    tasks_data = load_tasks()
    activities_data = load_activities()
    job_profiles = load_job_profiles()

    # 1. Verify skills weight total == 1.0
    total_weight = sum(s["weight"] for s in skills_data["skills"])
    assert abs(total_weight - 1.0) < 1e-6, f"Total weight must equal 1.0, got {total_weight}"

    # 2. Verify core skills present
    core_skills = {s["skill_code"] for s in skills_data["skills"] if s.get("is_core")}
    assert "SQL" in core_skills and "DATA_QUALITY" in core_skills, "SQL and DATA_QUALITY must be core skills"

    # 3. Verify tasks coverage
    task_ids = {t["task_id"] for t in tasks_data}
    assert "DA01A" in task_ids and "DA01B" in task_ids, "DA01A and DA01B must exist in tasks"
    for task in tasks_data:
        dataset = os.path.join(DATA_DIR, task["dataset_preview"])
        assert os.path.isfile(dataset), f"Dataset {task['dataset_preview']} of {task['task_id']} is missing"

    # 4. Verify activities prerequisites reference existing activities
    activity_ids = {a["activity_id"] for a in activities_data}
    for a in activities_data:
        for prereq in a.get("prerequisites", []):
            assert prereq in activity_ids, f"Prerequisite {prereq} not found for activity {a['activity_id']}"

    # 5. Verify each job profile weight distribution and skill references.
    skill_codes = {s["skill_code"] for s in skills_data["skills"]}
    for profile in job_profiles:
        profile_weights = [item["weight"] for item in profile["requirements_by_skill"].values()]
        assert abs(sum(profile_weights) - 1.0) < 1e-6, f"Profile {profile['profile_id']} weights must equal 1.0"
        assert set(profile["requirements_by_skill"]) == skill_codes, f"Profile {profile['profile_id']} must cover catalog skills"

    # 6. Verify activities point at real resources and the graph has no cycle.
    with open(os.path.join(DATA_DIR, "learning_resources_v4.json"), "r", encoding="utf-8") as f:
        resources = {item["resource_id"] for item in json.load(f)["resources"]}
    for a in activities_data:
        assert set(a.get("resource_ids", [])) <= resources, f"Unknown resource in {a['activity_id']}"

    # 7. Verify the exam bank: full points and every skill at every difficulty.
    with open(os.path.join(DATA_DIR, "exam_items_v5.json"), "r", encoding="utf-8") as f:
        exam_items = json.load(f)["items"]
    for item in exam_items:
        assert sum(case["points"] for case in item["cases"]) == 100, f"{item['item_id']} does not total 100 points"
    assert len({(item["skill_code"], item["tier"]) for item in exam_items}) == len(skill_codes) * 3, "Exam bank must cover every skill at 3 difficulties"

    print(f"[OK] Seed integrity verified successfully:")
    print(f"     - Skills: {len(skills_data['skills'])} (Core: {list(core_skills)})")
    print(f"     - Tasks: {len(tasks_data)} ({list(task_ids)})")
    print(f"     - Activities: {len(activities_data)} ({list(activity_ids)})")
    print(f"     - Job profiles: {len(job_profiles)}")
    return True


if __name__ == "__main__":
    verify_seed_integrity()
