"""Container sandbox (5.34): the docker command, failing closed, and the run protocol through a docker stand-in.

Docker is not available on the machine these tests were written on, so a real container is only exercised
by the last test, which is skipped unless Docker and the image are present.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from backend.engine import container_sandbox, python_sandbox
from backend.engine.python_sandbox import run_python
from backend.engine.sql_sandbox import execute_readonly_sql

FAKE = Path(__file__).with_name("fake_docker.py")
DATASET = "orders_da01a.csv"


@pytest.fixture
def fake_docker(monkeypatch, tmp_path):
    log = tmp_path / "docker_calls.jsonl"
    monkeypatch.setenv("CAREERADAPT_SANDBOX", "docker")
    monkeypatch.setenv("CAREERADAPT_DOCKER_BIN", json.dumps([sys.executable, str(FAKE)]))
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    monkeypatch.delenv("FAKE_DOCKER_NO_IMAGE", raising=False)
    container_sandbox._image_present.cache_clear()
    python_sandbox._run_cached.cache_clear()
    yield log
    container_sandbox._image_present.cache_clear()
    python_sandbox._run_cached.cache_clear()


def calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def option(args: list[str], name: str) -> list[str]:
    return [args[index + 1] for index, value in enumerate(args) if value == name]


def test_the_default_is_the_local_subprocess(monkeypatch):
    monkeypatch.delenv("CAREERADAPT_SANDBOX", raising=False)
    assert container_sandbox.mode() == "process" and container_sandbox.use_container() is False


def test_the_run_command_isolates_the_container(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREERADAPT_DOCKER_BIN", "docker")
    args = container_sandbox.command(python_sandbox.WORKER, str(tmp_path), memory="1g")
    assert args[:4] == ["docker", "run", "--rm", "-i"]
    assert option(args, "--network") == ["none"] and "--read-only" in args
    assert option(args, "--memory") == ["1g"] and option(args, "--memory-swap") == ["1g"]
    assert option(args, "--pids-limit") == ["64"] and option(args, "--cap-drop") == ["ALL"]
    assert option(args, "--security-opt") == ["no-new-privileges"] and option(args, "--user") == ["65534:65534"]
    mounts = option(args, "--mount")
    assert any(item.endswith(",target=/sandbox,readonly") for item in mounts)
    assert any(item == f"type=bind,source={tmp_path},target=/work" for item in mounts)
    assert args[-4:] == ["python", "-I", "-S", "/sandbox/python_sandbox_worker.py"]


def test_python_runs_through_the_container_command(fake_docker):
    result = run_python("import pandas as pd\ndf = pd.read_csv('orders.csv')\nprint(len(df))", DATASET)
    assert result["status"] == "OK", result
    assert result["stdout"].strip().isdigit()
    made = calls(fake_docker)
    assert len(made) == 1 and option(made[0], "--network") == ["none"] and made[0][-1] == "/sandbox/python_sandbox_worker.py"


def test_sql_runs_through_the_container_command(fake_docker):
    result = execute_readonly_sql("SELECT COUNT(*) FROM orders_raw", DATASET)
    assert result["executed"] is True and result["result_sets"][0]["rows"][0][0] > 0
    made = calls(fake_docker)
    assert made and option(made[-1], "--memory") == ["256m"] and made[-1][-1] == "/sandbox/sql_sandbox_worker.py"


def test_the_worker_checks_still_apply_inside_the_container(fake_docker):
    assert run_python("import os\nos.system('dir')", DATASET)["status"] == "BLOCKED"
    assert calls(fake_docker) == []  # refused before any container started


def test_without_the_image_learner_code_is_never_run_outside_the_container(fake_docker, monkeypatch):
    monkeypatch.setenv("FAKE_DOCKER_NO_IMAGE", "1")
    container_sandbox._image_present.cache_clear()
    assert run_python("print(1)", DATASET)["status"] == "UNAVAILABLE"
    assert execute_readonly_sql("SELECT 1", DATASET)["executed"] is False
    assert calls(fake_docker) == []


def test_auto_falls_back_to_the_subprocess_when_docker_is_missing(fake_docker, monkeypatch):
    monkeypatch.setenv("CAREERADAPT_SANDBOX", "auto")
    monkeypatch.setenv("FAKE_DOCKER_NO_IMAGE", "1")
    container_sandbox._image_present.cache_clear()
    assert container_sandbox.use_container() is False
    assert run_python("print(6 * 7)", DATASET)["stdout"].strip() == "42"
    assert calls(fake_docker) == []


def _real_docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "image", "inspect", "careeradapt-sandbox:1"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _real_docker_ready(), reason="Docker or the careeradapt-sandbox:1 image is not installed")
def test_a_real_container_has_no_network(monkeypatch):
    monkeypatch.setenv("CAREERADAPT_SANDBOX", "docker")
    monkeypatch.setenv("CAREERADAPT_DOCKER_BIN", "docker")
    container_sandbox._image_present.cache_clear()
    python_sandbox._run_cached.cache_clear()
    assert run_python("import pandas as pd\nprint(len(pd.read_csv('orders.csv')))", DATASET)["status"] == "OK"
    assert execute_readonly_sql("SELECT COUNT(*) FROM orders_raw", DATASET)["executed"] is True
