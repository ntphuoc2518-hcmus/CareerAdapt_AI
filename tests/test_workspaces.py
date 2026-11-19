"""Exam workspaces: every question names its tool, code really runs, and grading uses the real run."""
import json
import sys
from pathlib import Path

import pytest

from backend.engine import python_sandbox
from backend.engine.exam_grader import BANK, WORKSPACES, evaluate_question, validate_bank
from backend.engine.python_sandbox import check_source, run_python
from backend.engine.sql_sandbox import execute_readonly_sql
from backend import exam_service
from backend.store import store
from v5_helpers import FACTS, P, STUDENT, STUDENT_2, client, good_answer, to_exam

ROOT = Path(__file__).resolve().parents[1]
DATASET = "orders_da01a.csv"
EN = {**STUDENT, "X-Language": "en"}


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    exam_service._last_run.clear()
    exam_service.RUN_GAP_SECONDS = 0
    yield
    store.reset()
    exam_service.RUN_GAP_SECONDS = 1.0


def item(code, variant="A"):
    entry = next(entry for entry in BANK["items"] if entry["item_id"] == code)
    return {**entry, "dataset": BANK["datasets"][variant], "gates": entry.get("gates", [])}


def question(exam, workspace):
    return next(entry for entry in client.get(f"{P}/exam", headers=STUDENT).json()["questions"] if entry["workspace"] == workspace)


def run(question_id, code, headers=STUDENT):
    return client.post(f"{P}/exam/run", json={"question_id": question_id, "code": code}, headers=headers)


# --- Workspace selection ---

def test_every_question_declares_a_known_workspace():
    assert validate_bank() == []
    assert {entry["workspace"] for entry in BANK["items"]} == WORKSPACES


def test_each_skill_gets_its_own_tool():
    workspaces = {entry["item_id"]: entry["workspace"] for entry in BANK["items"]}
    assert all(workspaces[f"SQL-{n}"] == "sql" and workspaces[f"PY-{n}"] == "python" and workspaces[f"DQ-{n}"] == "data_quality" and workspaces[f"WC-{n}"] == "report" for n in (1, 2, 3))
    assert (workspaces["VIZ-1"], workspaces["VIZ-2"], workspaces["VIZ-3"]) == ("visualization", "python", "visualization")


def test_only_the_structured_report_offers_predefined_sections():
    assert [entry["item_id"] for entry in BANK["items"] if entry.get("report_sections")] == ["WC-3"]


def test_the_exam_state_carries_workspace_and_schema_but_no_sample_code_or_answer_key():
    to_exam()
    state = client.get(f"{P}/exam", headers=STUDENT).json()
    sql = next(entry for entry in state["questions"] if entry["workspace"] == "sql")
    assert sql["dataset"]["table"] == "orders_raw" and {"name": "quantity", "type": "INTEGER"} in sql["dataset"]["schema"]
    assert "starter" not in sql and sql["answer"] == "" and "cases" not in sql and "expected_sql" not in json.dumps(state)


def test_an_attempt_from_before_workspaces_still_opens():
    assert exam_service._workspace({"answer_type": "sql"}) == "sql"
    assert exam_service._workspace({"answer_type": "text"}) == "report"


def test_the_workspace_is_never_guessed_from_question_text():
    source = (ROOT / "frontend" / "js" / "workspaces.js").read_text(encoding="utf-8")
    assert "question.workspace" in source and "question.prompt" not in source


# --- SQL ---

def test_sql_really_runs_on_the_task_dataset():
    exam = to_exam()
    sql = question(exam, "sql")
    response = run(sql["question_id"], "SELECT COUNT(*) AS n FROM orders_raw;").json()
    assert response["status"] == "OK" and response["result_sets"][0]["columns"] == ["n"] and response["result_sets"][0]["rows"] == [[len(sql["dataset"]["rows"])]]


def test_sql_errors_are_reported_not_hidden():
    exam = to_exam()
    response = run(question(exam, "sql")["question_id"], "SELEC nope").json()
    assert response["status"] == "ERROR" and "syntax" in response["message"]


@pytest.mark.parametrize("statement", ["DROP TABLE orders_raw", "DELETE FROM orders_raw", "ATTACH DATABASE 'x' AS y", "SELECT * FROM sqlite_master"])
def test_sql_cannot_change_or_leave_the_dataset(statement):
    exam = to_exam()
    assert run(question(exam, "sql")["question_id"], statement).json()["status"] == "ERROR"


# --- Python ---

def test_python_really_runs_and_returns_output_tables_and_figures():
    code = "import pandas as pd\nimport matplotlib.pyplot as plt\ndf = pd.read_csv('orders.csv')\nprint(len(df))\nplt.bar([1, 2], [3, 4])\ndf.head(2)"
    result = run_python(code, DATASET)
    assert result["status"] == "OK" and result["stdout"].strip() == "10" and len(result["figures"]) == 1
    assert {table["name"] for table in result["tables"]} == {"df", ""} and result["tables"][0]["shape"][0] == 10


FRAMES = "import pandas as pd\nimport numpy as np\ndf = pd.read_csv('orders.csv')\n"


@pytest.mark.parametrize("code", [
    "x = df.groupby('status')['status'].count()", "x = df.set_index('region', drop=False)",
    "x = pd.DataFrame({'a': [1, None]}).convert_dtypes()", "x = pd.DataFrame({'a': [np.array([1, 2])]})",
])
def test_showing_a_table_never_costs_the_output_of_a_run_that_worked(code):
    result = run_python(f"{FRAMES}{code}\nprint('xong')", DATASET)
    assert result["status"] == "OK" and result["stdout"].strip() == "xong"
    assert [table["name"] for table in result["tables"]] == ["df", "x"]


def test_the_last_line_can_be_a_table_named_like_its_index():
    result = run_python(f"{FRAMES}df.groupby('status')['status'].count()", DATASET)
    assert result["status"] == "OK" and result["tables"][-1]["name"] == "" and result["tables"][-1]["columns"] == ["status", "status"]


def test_every_kind_of_missing_value_shows_blank():
    result = run_python(f"{FRAMES}x = pd.DataFrame({{'a': [None, 1], 'b': [pd.NaT, pd.NaT], 'c': [np.nan, 2.0]}}).astype({{'a': 'Int64'}})", DATASET)
    assert result["tables"][-1]["rows"][0] == ["0", "", "", ""]


def test_an_unrelated_table_cannot_cost_marks():
    code = "import pandas as pd\ndf = pd.read_csv('orders.csv')\nkq = df[df['status'] == 'completed']\ndem = kq.groupby('status')['status'].count()\nprint(len(kq))"
    outcomes, _ = evaluate_question(item("PY-1"), code)
    assert outcomes["runs"]["passed"] and outcomes["result"]["passed"]


FAILS_TO_PRINT = "class A:\n    def __str__(self):\n        raise ValueError('hong')\n"


def test_a_value_that_cannot_be_printed_is_a_runtime_error_with_its_output():
    result = run_python(f"{FAILS_TO_PRINT}print('xong')\nA()", DATASET)
    assert result["status"] == "RUNTIME_ERROR" and result["stdout"].strip() == "xong"
    assert result["error"]["type"] == "ValueError" and result["error"]["line"] == 3


def test_an_exception_that_cannot_be_printed_is_still_reported():
    result = run_python("class E(Exception):\n    def __str__(self):\n        raise ValueError('x')\nprint('xong')\nraise E()", DATASET)
    assert result["status"] == "RUNTIME_ERROR" and result["stdout"].strip() == "xong" and result["error"]["type"] == "E"


@pytest.mark.parametrize("body", ["raise ValueError('hong')", "print('tieng on')\n        return 'a'", "raise SystemExit(0)"])
def test_a_table_cell_cannot_break_the_result(body):
    result = run_python(f"{FRAMES}class A:\n    def __str__(self):\n        {body}\nx = pd.DataFrame({{'a': [A()]}})\nprint('xong')", DATASET)
    assert result["status"] == "OK" and result["stdout"].strip() == "xong"
    assert [table["name"] for table in result["tables"]] == ["df", "x"]


@pytest.mark.parametrize("line", ["plt.title(r'$\\badcommand$')", "plt.gcf().set_size_inches(1000, 1000)"])
def test_a_figure_that_cannot_be_drawn_is_a_runtime_error_and_keeps_the_rest(line):
    result = run_python(f"import matplotlib.pyplot as plt\nplt.bar([1], [2])\nplt.figure()\nplt.bar([3], [4])\n{line}\nprint('xong')", DATASET)
    assert result["status"] == "RUNTIME_ERROR" and result["stdout"].strip() == "xong" and len(result["figures"]) == 1


@pytest.mark.parametrize("code", [
    "import json\njson.dumps = 1\nprint('xong')", "import pandas as pd\npd.io.common.os._exit(0)", "import pandas as pd\npd.io.common.os._exit(1)",
])
def test_code_that_ends_the_worker_is_its_own_runtime_error_not_a_limit_or_an_outage(code):
    result = run_python(code, DATASET)
    assert result["status"] == "RUNTIME_ERROR" and "CPU" not in result["error"]["message"]


def test_code_that_ends_the_worker_is_graded_and_cannot_block_the_exam():
    outcomes, _ = evaluate_question(item("PY-1"), "import pandas as pd\npd.io.common.os._exit(0)")
    assert not outcomes["runs"]["passed"]


def worker_that(monkeypatch, script):
    monkeypatch.setattr(python_sandbox, "_command", lambda: [sys.executable, "-c", script])
    return python_sandbox._run("print(1)", DATASET)


@pytest.mark.parametrize("script", ["raise SystemExit(1)", "raise SystemExit(0)", "raise SystemExit(7)", "import os\nos.write(1, b'{}')"])
def test_a_worker_that_never_reached_the_code_is_an_outage(monkeypatch, script):
    with pytest.raises(OSError):
        worker_that(monkeypatch, script)


@pytest.mark.parametrize("code", [0xC0000044 - 2**32, 137])  # the Windows CPU limit's exit code, signed for os._exit
def test_a_process_killed_by_a_limit_is_still_reported_as_a_limit(monkeypatch, code):
    script = f"import os\nos.write(1, b'{python_sandbox.READY}')\nos._exit({code})"
    assert worker_that(monkeypatch, script)["status"] == "RESOURCE_LIMIT"


def test_syntax_runtime_and_success_are_told_apart():
    assert run_python("print(", DATASET)["status"] == "SYNTAX_ERROR"
    failure = run_python("x = 1\nprint(x / 0)", DATASET)
    assert failure["status"] == "RUNTIME_ERROR" and failure["error"]["type"] == "ZeroDivisionError" and failure["error"]["line"] == 2 and "x / 0" in failure["error"]["traceback"]
    assert run_python("print(1)", DATASET)["status"] == "OK"


def test_tracebacks_show_no_server_paths():
    result = run_python("import pandas as pd\npd.read_csv('khong_co.csv')", DATASET)
    assert "site-packages" not in result["error"]["traceback"] and "AppData" not in result["error"]["traceback"]


@pytest.mark.parametrize("code", ["import os", "import socket", "import subprocess", "from pathlib import Path", "eval('1')", "__import__('os')", "().__class__.__bases__", "getattr(print, 'x')"])
def test_dangerous_code_is_stopped_before_any_process_starts(code):
    assert check_source(code)["status"] == "BLOCKED"


@pytest.mark.parametrize("code", [
    "print(open(r'C:/Windows/win.ini').read())", "print(open('../secret.txt').read())", "open('C:/Windows/Temp/careeradapt_sandbox_test.txt', 'w')",
    "import pandas as pd\npd.io.common.os.system('whoami')", "import pandas as pd\npd.io.common.os.listdir('C:/')", "import pandas as pd\nprint(pd.io.common.os.environ.get('SYSTEMROOT') and pd.read_csv('C:/Windows/win.ini'))",
])
def test_the_running_worker_refuses_files_and_commands_outside_its_folder(code):
    result = run_python(code, DATASET)
    assert result["status"] == "RUNTIME_ERROR" and "Bài làm" in result["error"]["message"]
    assert not Path("C:/Windows/Temp/careeradapt_sandbox_test.txt").exists()


def test_the_environment_holds_no_secrets():
    result = run_python("import pandas as pd\nprint(sorted(pd.io.common.os.environ))", DATASET)
    assert result["status"] == "OK" and "LLM_API_KEY" not in result["stdout"] and "PATH" not in result["stdout"].replace("PATHEXT", "")


def test_memory_and_time_limits_stop_the_run():
    assert run_python("x = [bytearray(10**7) for i in range(200)]", DATASET)["status"] in {"RUNTIME_ERROR", "RESOURCE_LIMIT"}
    assert run_python("while True:\n    pass", DATASET)["status"] in {"RESOURCE_LIMIT", "TIMEOUT"}


def test_the_dataset_is_a_private_copy():
    run_python("open('orders.csv', 'w').write('hong')", DATASET)
    assert "order_id" in (ROOT / "data" / DATASET).read_text(encoding="utf-8")
    assert "order_id" in run_python("print(open('orders.csv').readline())", DATASET)["stdout"]


# --- Grading uses the real run ---

def test_a_number_in_a_comment_earns_nothing():
    code = "import pandas as pd\ndf = pd.read_csv('orders.csv')\nkq = df[df['status'] == 'completed']\n# Ket qua: 9"
    outcomes, _ = evaluate_question(item("PY-1"), code)
    assert outcomes["runs"]["passed"] and not outcomes["result"]["passed"]


def test_the_same_number_printed_by_the_code_earns_the_marks():
    code = "import pandas as pd\ndf = pd.read_csv('orders.csv')\nkq = df[df['status'] == 'completed']\nprint(len(kq))"
    outcomes, _ = evaluate_question(item("PY-1"), code)
    assert outcomes["result"]["passed"]


def test_printing_the_answer_directly_still_fails_the_code_checks():
    outcomes, _ = evaluate_question(item("PY-1"), "print(9)")
    assert outcomes["result"]["passed"] and not outcomes["read"]["passed"] and not outcomes["filter"]["passed"]


def test_code_that_parses_but_crashes_is_marked_as_such():
    outcomes, _ = evaluate_question(item("PY-1"), "import pandas as pd\ndf = pd.read_csv('orders.csv')\nkq = df[df['status'] == 'completed']\nprint(kq['nope'])")
    assert outcomes["parse"]["passed"] and not outcomes["runs"]["passed"] and not outcomes["result"]["passed"]
    assert "KeyError" not in outcomes["runs"]["actual_summary"] or "chạy" in outcomes["runs"]["actual_summary"]


def test_points_of_each_python_item_still_total_100():
    for entry in BANK["items"]:
        assert sum(case["points"] for case in entry["cases"]) == 100


@pytest.mark.parametrize("code", ["PY-1", "PY-2", "PY-3", "VIZ-2"])
@pytest.mark.parametrize("variant", ["A", "B"])
def test_reference_python_answers_earn_full_marks_from_their_real_output(code, variant):
    outcomes, critical = evaluate_question(item(code, variant), good_answer(f"{code}-{variant}"))
    assert [name for name, outcome in outcomes.items() if not outcome["passed"]] == [] and not critical


def test_a_sandbox_that_cannot_start_does_not_cost_marks(monkeypatch):
    from backend.engine import exam_grader

    monkeypatch.setattr(exam_grader, "run_python", lambda code, dataset: {"status": "UNAVAILABLE", "output_text": ""})
    with pytest.raises(RuntimeError):
        evaluate_question(item("PY-1"), "print(1)")


def test_workspace_answers_stay_plain_text_for_the_grader():
    report = "## Tóm tắt\n\ndoanh thu giảm **14,29%**"
    outcomes, _ = evaluate_question(item("WC-3"), report)
    assert outcomes["change"]["passed"]


# --- The run endpoint ---

def test_running_changes_nothing_in_the_exam():
    exam = to_exam()
    sql = question(exam, "sql")
    run(sql["question_id"], "SELECT 1;")
    assert client.get(f"{P}/exam", headers=STUDENT).json()["questions"][0]["answer"] == ""
    assert store.db.one("SELECT COUNT(*) AS n FROM exam_responses")["n"] == 0


def test_running_needs_your_own_open_exam():
    exam = to_exam()
    sql = question(exam, "sql")
    assert run(sql["question_id"], "SELECT 1;", STUDENT_2).status_code == 404
    assert client.post(f"{P}/exam/run", json={"question_id": sql["question_id"], "code": "SELECT 1;"}).status_code == 403
    assert run("Q99", "SELECT 1;").status_code == 404


def test_written_questions_have_nothing_to_run():
    exam = to_exam()
    assert run(question(exam, "report")["question_id"], "SELECT 1;").status_code == 409


def test_nothing_runs_after_submission():
    exam = to_exam()
    sql = question(exam, "sql")
    client.post(f"{P}/exam/submit", json={}, headers=STUDENT)
    assert run(sql["question_id"], "SELECT 1;").status_code == 409


def test_runs_are_rate_limited_per_account():
    exam = to_exam()
    sql = question(exam, "sql")
    exam_service.RUN_GAP_SECONDS = 60
    assert run(sql["question_id"], "SELECT 1;").status_code == 200
    assert run(sql["question_id"], "SELECT 1;").status_code == 429


def test_english_mode_keeps_output_untranslated():
    exam = to_exam()
    python = question(exam, "python")
    result = run(python["question_id"], "print('Biểu đồ cột')", EN).json()
    assert result["stdout"].strip() == "Biểu đồ cột"


def test_the_sql_engine_and_the_grader_see_the_same_rows():
    code = good_answer("SQL-1-A")
    assert execute_readonly_sql(code, DATASET)["result_sets"][0]["rows"]
    assert evaluate_question(item("SQL-1"), code)[0]["result"]["passed"]
    assert FACTS["A"]
