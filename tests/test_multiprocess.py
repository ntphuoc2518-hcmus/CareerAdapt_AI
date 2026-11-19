"""Several server processes on one database (5.34).

These tests start real, separate Python processes. Each one imports the backend with persistence on and
points at a database in a temporary folder, exactly like two uvicorn workers would. The project's own
data files are never opened for writing.
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
STUDENT = {"Authorization": "Bearer token_student_1"}
STUDENT_ID = "11111111-1111-1111-1111-111111111111"


def environment(folder: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("CAREERADAPT_")}
    env.update({
        "CAREERADAPT_DB": str(folder / "careeradapt.sqlite3"), "CAREERADAPT_ACCOUNTS_DB": str(folder / "accounts.sqlite3"),
        "CAREERADAPT_STATE_PATH": str(folder / "no_legacy_state.json"), "CAREERADAPT_QUESTION_BANK_OVERRIDES_PATH": str(folder / "bank_overrides.json"),
        "CAREERADAPT_DEMO_AUTH": "true", "CAREERADAPT_ENV": "development", "CAREERADAPT_AUTO_LINK_CHECK": "false", "LLM_PROVIDER": "mock",
        "CAREERADAPT_USER_LOCK_WAIT": "60", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(ROOT),
    })
    return env


START = r'''
import os, sys, time, uuid
from backend.store import store
user = uuid.UUID(sys.argv[1])
# Wait until every process is loaded, so their loops really run at the same time.
print("ready", flush=True)
while not os.path.exists(sys.argv[3]):
    time.sleep(0.01)
'''

COUNTER = START + r'''
for _ in range(int(sys.argv[2])):
    # The same read-modify-write a request does, inside the learner's lock.
    with store.user_scope(user):
        profile = store.get_or_create_profile(user)
        seen = int(profile.get("counter", 0))
        time.sleep(0.02)  # a request doing some work between reading and writing
        profile["counter"] = seen + 1
        store.persist_user_runtime(user)
print("done")
'''

UNLOCKED = START + r'''
for _ in range(int(sys.argv[2])):
    # The same work without the lock: the processes overwrite each other.
    store.sync_user(user)
    profile = store.get_or_create_profile(user)
    seen = int(profile.get("counter", 0))
    time.sleep(0.02)
    profile["counter"] = seen + 1
    store.persist_user_runtime(user)
print("done")
'''

READ = r'''
import json, sys, uuid
from backend.store import store
user = uuid.UUID(sys.argv[1])
store.sync_user(user)
print(json.dumps({"counter": store.get_or_create_profile(user).get("counter"), "fk": store.db.get_meta("fk_schema_version"),
                  "pragma": store.db.one("PRAGMA foreign_keys")["foreign_keys"]}))
'''


def run_parallel(folder: Path, script: str, processes: int, rounds: int) -> None:
    (folder / "job.py").write_text(script, encoding="utf-8")
    env = environment(folder)
    # Create the database once so the parallel starts do not all build the schema together.
    subprocess.run([PYTHON, "-c", "from backend.store import store"], cwd=ROOT, env=env, check=True, capture_output=True, timeout=120)
    go = folder / "go"
    children = [subprocess.Popen([PYTHON, str(folder / "job.py"), STUDENT_ID, str(rounds), str(go)], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(processes)]
    for child in children:
        assert child.stdout.readline().strip() == b"ready"
    go.write_text("go", encoding="utf-8")
    for child in children:
        out, err = child.communicate(timeout=300)
        assert child.returncode == 0, err.decode("utf-8", "replace")[-2000:]


def read_back(folder: Path) -> dict:
    (folder / "read.py").write_text(READ, encoding="utf-8")
    result = subprocess.run([PYTHON, str(folder / "read.py"), STUDENT_ID], cwd=ROOT, env=environment(folder), capture_output=True, timeout=120, check=True)
    return json.loads(result.stdout.decode("utf-8").strip().splitlines()[-1])


def test_without_the_lock_parallel_processes_lose_updates(tmp_path):
    """The failure the lock exists for, shown on purpose: three stale copies overwrite each other."""
    run_parallel(tmp_path, UNLOCKED, processes=3, rounds=15)
    assert read_back(tmp_path)["counter"] < 45


def test_with_the_lock_no_update_from_any_process_is_lost(tmp_path):
    run_parallel(tmp_path, COUNTER, processes=3, rounds=15)
    state = read_back(tmp_path)
    assert state["counter"] == 45
    assert state["fk"] == "1" and state["pragma"] == 1


# --- Two real servers sharing one database, as two uvicorn workers would ---

def free_ports(count: int) -> list[int]:
    sockets = [socket.socket() for _ in range(count)]
    for sock in sockets:
        sock.bind(("127.0.0.1", 0))
    ports = [sock.getsockname()[1] for sock in sockets]
    for sock in sockets:
        sock.close()
    return ports


def call(port: int, method: str, path: str, body=None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method, headers={**STUDENT, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


@pytest.fixture
def two_servers(tmp_path):
    env = environment(tmp_path)
    # Both servers start on a brand-new database at the same moment, as uvicorn workers do.
    ports = free_ports(2)
    # Server output goes to files: an unread pipe fills up and freezes the server.
    logs = [open(tmp_path / f"server-{port}.log", "wb") for port in ports]
    servers = [subprocess.Popen([PYTHON, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT) for port, log in zip(ports, logs)]
    try:
        for port, server in zip(ports, servers):
            for _ in range(240):
                if server.poll() is not None:
                    # Fail at once: a dead port can take seconds per try on Windows.
                    raise RuntimeError("server stopped: " + (tmp_path / f"server-{port}.log").read_text(encoding="utf-8", errors="replace")[-2000:])
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2):
                        break
                except (OSError, ValueError, http.client.HTTPException):
                    time.sleep(0.25)
            else:
                raise RuntimeError("server did not start: " + (tmp_path / f"server-{port}.log").read_text(encoding="utf-8", errors="replace")[-2000:])
        yield ports
    finally:
        for server in servers:
            server.terminate()
            server.wait(timeout=30)
        for log in logs:
            log.close()


def test_a_change_made_through_one_server_is_seen_through_the_other(two_servers):
    first, second = two_servers
    assert call(second, "GET", "/api/v1/me/profile")[1]["weekly_hours_budget"] != 7.5
    status, _ = call(first, "PUT", "/api/v1/me/profile", {"weekly_hours_budget": 7.5, "target_timeline_weeks": 10})
    assert status == 200
    profile = call(second, "GET", "/api/v1/me/profile")[1]
    assert profile["weekly_hours_budget"] == 7.5 and profile["target_timeline_weeks"] == 10
    # And back the other way, with a write that also lands in its own table.
    status, _ = call(second, "PUT", "/api/v1/me/reminder-preferences", {"default_cycle_days": 14})
    assert status == 200
    assert call(first, "GET", "/api/v1/me/reminder-preferences")[1]["default_cycle_days"] == 14


def test_interleaved_writes_through_both_servers_all_survive(two_servers):
    first, second = two_servers
    for index in range(10):
        port = first if index % 2 == 0 else second
        assert call(port, "PUT", "/api/v1/me/profile", {"weekly_hours_budget": 1 + index, "target_timeline_weeks": 8, "major": f"Ngành {index}"})[0] == 200
        other = second if port == first else first
        assert call(other, "GET", "/api/v1/me/profile")[1]["major"] == f"Ngành {index}"


def test_several_processes_can_start_on_a_new_database_at_once(tmp_path):
    """Found by these tests: two servers creating the account database together used to crash one of them."""
    env = environment(tmp_path)
    starts = [subprocess.Popen([PYTHON, "-c", "import backend.main"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
    failures = []
    for process in starts:
        _, err = process.communicate(timeout=300)
        if process.returncode != 0:
            failures.append(err.decode("utf-8", "replace")[-800:])
    assert failures == []
