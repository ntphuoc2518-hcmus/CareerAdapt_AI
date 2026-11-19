"""Run a learner's Python in a disposable subprocess, never inside the API process.

Three layers: the code is checked here before anything runs, the worker has OS limits, and an audit
hook in the worker denies files, network and child processes. On Windows without containers this is
strong against mistakes and casual misuse but it is not a security boundary against a determined
attacker. A public deployment should run the worker in a container with no network: set
CAREERADAPT_SANDBOX=docker (see backend/engine/container_sandbox.py and sandbox/Dockerfile).
"""
from __future__ import annotations

import ast
import copy
import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from backend.config import DATA_DIR
from backend.engine import container_sandbox
from backend.engine.sql_sandbox import load_dataset

WORKER = Path(__file__).with_name("python_sandbox_worker.py")
READY = "READY:"  # written by the worker just before the learner's code starts
PYTHON_EXIT_CODES = {0, 1}  # how Python itself ends; a limit kills the process with another code
TIMEOUT_SECONDS = 20.0
MAX_OUTPUT_BYTES = 6 * 1024 * 1024
DATA_FILE = "orders.csv"
ALLOWED_IMPORTS = {"pandas", "numpy", "matplotlib", "math", "statistics", "datetime", "re", "json", "collections", "itertools", "functools", "decimal", "fractions", "random", "string", "csv", "calendar", "typing", "dataclasses", "warnings", "textwrap"}
BLOCKED_NAMES = {"eval", "exec", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr", "delattr", "breakpoint", "input", "help", "exit", "quit", "memoryview"}
ALLOWED_DUNDERS = {"__init__", "__str__", "__repr__", "__name__", "__len__", "__eq__", "__lt__", "__add__", "__iter__", "__next__", "__call__", "__main__"}


def _fail(status: str, message: str, line: Optional[int] = None, kind: str = "") -> dict:
    return {"status": status, "stdout": "", "output_text": "", "tables": [], "figures": [], "elapsed_ms": 0,
            "error": {"type": kind or status, "message": message, "line": line, "traceback": f"Dòng {line}: {message}" if line else message}}


def check_source(source: str) -> Optional[dict]:
    """Syntax and the allow-list, before any process starts."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return _fail("SYNTAX_ERROR", f"Lỗi cú pháp: {error.msg}", error.lineno, "SyntaxError")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            names = []
        for name in names:
            if name.split(".")[0] not in ALLOWED_IMPORTS:
                return _fail("BLOCKED", f"Thư viện {name} không dùng được trong bài kiểm tra.", node.lineno, "ImportError")
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            return _fail("BLOCKED", f"Không dùng {node.id} trong bài kiểm tra.", node.lineno, "NameError")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr not in ALLOWED_DUNDERS:
            return _fail("BLOCKED", f"Không dùng {node.attr} trong bài kiểm tra.", node.lineno, "AttributeError")
    return None


def _modules(source: str) -> list[str]:
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return sorted(found & {"pandas", "numpy", "matplotlib"})


def _site_paths() -> list[str]:
    paths = [path for path in sys.path if path.endswith("site-packages")]
    return paths or site.getsitepackages()


def _font_cache() -> Path:
    folder = Path(tempfile.gettempdir()) / "careeradapt-mpl-cache"
    folder.mkdir(exist_ok=True)
    return folder


def _environment(cache: Path) -> dict[str, str]:
    return {"SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "MPLBACKEND": "Agg", "MPLCONFIGDIR": str(cache), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_MAX_THREADS": "1"}


def _command() -> list[str]:
    return [getattr(sys, "_base_executable", sys.executable) or sys.executable, "-I", "-S", str(WORKER)]


@lru_cache(maxsize=256)
def _run_cached(source: str, dataset_name: str) -> str:
    return json.dumps(_run(source, dataset_name), ensure_ascii=False)


def _run(source: str, dataset_name: str) -> dict:
    load_dataset(dataset_name)
    in_container = container_sandbox.use_container()
    if in_container and not container_sandbox.available():
        # Fail closed: never fall back to running learner code outside the container that was asked for.
        raise OSError("container sandbox unavailable")
    cache = _font_cache()
    if in_container:
        site_paths, roots = container_sandbox.python_paths()
    else:
        site_paths, roots = _site_paths(), [sys.base_prefix, sys.prefix, *_site_paths(), str(cache)]
    job = json.dumps({"source": source, "modules": _modules(source), "site_paths": site_paths, "read_roots": roots}, ensure_ascii=False)
    with tempfile.TemporaryDirectory(prefix="careeradapt-py-", ignore_cleanup_errors=True) as workdir:
        shutil.copyfile(DATA_DIR / dataset_name, Path(workdir) / DATA_FILE)
        if in_container:
            completed = subprocess.run(container_sandbox.command(WORKER, workdir, memory="1g"), input=job.encode("utf-8"), capture_output=True,
                                       timeout=TIMEOUT_SECONDS + container_sandbox.CONTAINER_START_SECONDS, cwd=workdir)
        else:
            completed = subprocess.run(_command(), input=job.encode("utf-8"), capture_output=True, timeout=TIMEOUT_SECONDS, cwd=workdir, env=_environment(cache))
    if len(completed.stdout) > MAX_OUTPUT_BYTES:
        return _fail("RESOURCE_LIMIT", "Bài làm in ra quá nhiều dữ liệu.")
    # Without the marker the learner's code never ran: an outage, which grading retries. Past it,
    # the failure is the learner's run and must be graded, or that exam could never finish.
    if not completed.stdout.startswith(READY.encode("ascii")):
        raise OSError("worker stopped before the code ran")
    try:
        return json.loads(completed.stdout[len(READY):].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        if completed.returncode in PYTHON_EXIT_CODES:
            return _fail("RUNTIME_ERROR", "Bài làm đã dừng tiến trình chạy trước khi có kết quả.", kind="ProcessExit")
        # The worker was killed by a limit before it could report.
        return _fail("RESOURCE_LIMIT", "Bài làm vượt giới hạn CPU hoặc bộ nhớ.")


def run_python(source: str, dataset_name: str) -> dict[str, Any]:
    """Status is SYNTAX_ERROR, BLOCKED, OK, RUNTIME_ERROR, TIMEOUT, RESOURCE_LIMIT or UNAVAILABLE. Never raises."""
    checked = check_source(source)
    if checked:
        return checked
    try:
        return copy.deepcopy(json.loads(_run_cached(source, dataset_name)))
    except subprocess.TimeoutExpired:
        return _fail("TIMEOUT", f"Code chạy quá {int(TIMEOUT_SECONDS)} giây nên đã bị dừng.")
    except (OSError, ValueError):
        return _fail("UNAVAILABLE", "Chưa khởi động được môi trường chạy Python.")
