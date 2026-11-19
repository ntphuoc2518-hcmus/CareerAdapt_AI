"""Run submitted SQL in a disposable subprocess, never inside the API process.

The worker gets an isolated interpreter, an empty environment and a temporary directory that is
removed afterwards. Only the synthetic assessment dataset is passed to it, through stdin.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR
from backend.engine import container_sandbox

WORKER = Path(__file__).with_name("sql_sandbox_worker.py")
TIMEOUT_SECONDS = 3.0
MAX_OUTPUT_BYTES = 2 * 1024 * 1024


def load_dataset(dataset_name: str) -> tuple[list[str], list[dict[str, str]]]:
    if Path(dataset_name).name != dataset_name or not dataset_name.lower().endswith(".csv"):
        raise ValueError("Tên bộ dữ liệu không hợp lệ.")
    csv_path = DATA_DIR / dataset_name
    if not csv_path.is_file():
        raise ValueError("Bộ dữ liệu của đề chưa được cài đặt.")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    if not columns or len(columns) > 40 or len(rows) > 10000:
        raise ValueError("Cấu trúc bộ dữ liệu không hợp lệ.")
    return columns, rows


def execute_readonly_sql(source: str, dataset_name: str) -> dict[str, Any]:
    """Return {"executed", "result_sets", "error"}; every failure is reported, never raised."""
    try:
        columns, rows = load_dataset(dataset_name)
    except (ValueError, OSError, csv.Error, UnicodeError) as error:
        return {"executed": False, "result_sets": [], "error": str(error)[:180]}
    job = json.dumps({"source": source, "columns": columns, "rows": [[row.get(column, "") for column in columns] for row in rows]}, ensure_ascii=False)
    in_container = container_sandbox.use_container()
    if in_container and not container_sandbox.available():
        # Fail closed, as the Python sandbox does.
        return {"executed": False, "result_sets": [], "error": "Chưa khởi động được môi trường chạy truy vấn."}
    try:
        with tempfile.TemporaryDirectory(prefix="careeradapt-sql-") as workdir:
            if in_container:
                completed = subprocess.run(container_sandbox.command(WORKER, workdir, memory="256m", cpus="0.5"), input=job.encode("utf-8"), capture_output=True,
                                           timeout=TIMEOUT_SECONDS + container_sandbox.CONTAINER_START_SECONDS, cwd=workdir)
            else:
                completed = subprocess.run(
                    [getattr(sys, "_base_executable", sys.executable) or sys.executable, "-I", "-S", str(WORKER)],
                    input=job.encode("utf-8"), capture_output=True, timeout=TIMEOUT_SECONDS, cwd=workdir,
                    env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
                )
    except subprocess.TimeoutExpired:
        return {"executed": False, "result_sets": [], "error": "Truy vấn vượt giới hạn thời gian."}
    except OSError:
        return {"executed": False, "result_sets": [], "error": "Chưa khởi động được môi trường chạy truy vấn."}
    if completed.returncode != 0 or len(completed.stdout) > MAX_OUTPUT_BYTES:
        return {"executed": False, "result_sets": [], "error": "Truy vấn vượt giới hạn tài nguyên."}
    try:
        return json.loads(completed.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"executed": False, "result_sets": [], "error": "Không đọc được kết quả truy vấn."}
