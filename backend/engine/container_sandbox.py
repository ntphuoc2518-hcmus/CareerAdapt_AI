"""Run the sandbox workers inside a container (5.34).

By default (``CAREERADAPT_SANDBOX=process``) the SQL and Python workers run as local subprocesses, as before.
With ``docker`` every run starts a fresh container from ``sandbox/Dockerfile`` with:

* no network (``--network none``) and a read-only root filesystem;
* a memory cap with no swap, a CPU share and a process-count cap;
* every Linux capability dropped, no privilege escalation, an unprivileged user (65534 = nobody);
* the worker scripts mounted read-only and only the run's own temporary folder writable.

``docker`` fails closed: if Docker or the image is missing, code is not run at all and the answer is
reported as "sandbox unavailable", which grading retries later. ``auto`` uses a container when one
is available and falls back to the local subprocess otherwise.

The container keeps every check the subprocess path has (the static allow-list, the audit hook in
the worker, the timeouts), so it adds an operating-system boundary on top of them.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
WORK = "/work"
CODE = "/sandbox"
CONTAINER_START_SECONDS = 15.0  # added to a worker's own time limit for creating and removing the container


def mode() -> str:
    value = os.getenv("CAREERADAPT_SANDBOX", "process").strip().lower()
    return value if value in {"process", "docker", "auto"} else "process"


def image() -> str:
    return os.getenv("CAREERADAPT_SANDBOX_IMAGE", "careeradapt-sandbox:1")


def container_site() -> str:
    """Where the image installs pandas, numpy and matplotlib."""
    return os.getenv("CAREERADAPT_SANDBOX_SITE", "/usr/local/lib/python3.13/site-packages")


def docker_cli() -> list[str]:
    """The Docker command: a path, or a JSON list (lets tests put a stand-in in its place)."""
    value = os.getenv("CAREERADAPT_DOCKER_BIN", "docker").strip()
    return json.loads(value) if value.startswith("[") else [value]


@lru_cache(maxsize=8)
def _image_present(cli: tuple[str, ...], name: str) -> bool:
    if not shutil.which(cli[0]) and not Path(cli[0]).exists():
        return False
    try:
        return subprocess.run([*cli, "image", "inspect", name], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def available() -> bool:
    return _image_present(tuple(docker_cli()), image())


def use_container() -> bool:
    """True when this run must go through a container (``docker``, or ``auto`` with Docker ready)."""
    selected = mode()
    return selected == "docker" or (selected == "auto" and available())


def command(worker: Path, workdir: str, memory: str, cpus: str = "1") -> list[str]:
    """``docker run`` for one worker run. Only ``workdir`` is writable; it is mounted at /work."""
    # The unprivileged user inside the container must be able to write the run's own folder.
    os.chmod(workdir, 0o777)
    return [
        *docker_cli(), "run", "--rm", "-i",
        "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=64m,mode=1777",
        "--memory", memory, "--memory-swap", memory, "--cpus", cpus, "--pids-limit", "64",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "--mount", f"type=bind,source={ENGINE_DIR},target={CODE},readonly",
        "--mount", f"type=bind,source={workdir},target={WORK}",
        "--workdir", WORK, "--env", "MPLBACKEND=Agg", "--env", "MPLCONFIGDIR=/tmp",
        "--env", "OPENBLAS_NUM_THREADS=1", "--env", "OMP_NUM_THREADS=1",
        image(), "python", "-I", "-S", f"{CODE}/{worker.name}",
    ]


def python_paths() -> tuple[list[str], list[str]]:
    """site_paths and read_roots for the Python worker, as seen inside the container."""
    site = container_site()
    return [site], ["/usr/local", "/usr/lib", site, "/tmp"]
