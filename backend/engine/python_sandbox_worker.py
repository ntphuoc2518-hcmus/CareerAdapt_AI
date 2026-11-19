"""Disposable Python worker. Runs as its own process, never imported by the API.

Reads one job from stdin and writes one JSON result to stdout. The process gets an empty environment,
a temporary working directory holding only the task's CSV, and OS limits on CPU, memory and child
processes. Libraries load first; then an audit hook denies files outside the allowed folders, the
network, child processes and native calls for the learner's code.
"""
import ast
import base64
import contextlib
import io
import json
import os
import sys
import time
import traceback
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sql_sandbox_worker import limit_process  # noqa: E402

READY = "READY:"  # same marker as python_sandbox.READY
MEMORY_BYTES = 900 * 1024 * 1024
CPU_SECONDS = 8
MAX_STDOUT_CHARS = 40_000
MAX_TABLES = 4
MAX_TABLE_ROWS = 20
MAX_FIGURES = 3
MAX_WRITTEN_FILES = 5
ANSWER_FILE = "answer.py"
DENIED_EVENTS = (
    "socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork", "os.forkpty", "os.startfile", "os.remove", "os.rename", "os.rmdir",
    "os.mkdir", "os.chmod", "os.chown", "os.link", "os.symlink", "os.truncate", "os.putenv", "os.unsetenv", "os.kill", "ctypes.", "winreg.", "msvcrt.", "mmap.",
    "shutil.", "sqlite3.connect", "urllib.Request", "ftplib.", "smtplib.", "http.client.", "webbrowser.", "pickle.find_class", "cpython.run_", "sys.setprofile", "sys.settrace",
)
DENIED_IMPORTS = {"socket", "ssl", "subprocess", "multiprocessing", "http", "urllib", "ftplib", "smtplib", "webbrowser", "shutil", "pickle", "marshal", "winreg", "sqlite3", "importlib"}


class Blocked(PermissionError):
    pass


def install_guard(workdir: str, read_roots: list[str]) -> None:
    roots = [os.path.normcase(os.path.abspath(path)) for path in read_roots]
    home = os.path.normcase(os.path.abspath(workdir))
    written = [0]

    def inside(path: str, folders: list[str]) -> bool:
        target = os.path.normcase(os.path.abspath(path))
        return any(target == folder or target.startswith(folder + os.sep) for folder in folders)

    def guard(event: str, args: tuple) -> None:
        if event == "open":
            path, mode = args[0], args[1]
            if not isinstance(path, (str, bytes, os.PathLike)):
                return
            text = os.fsdecode(path)
            writing = isinstance(mode, str) and any(flag in mode for flag in "wax+")
            if writing:
                written[0] += 1
                if not inside(text, [home]) or written[0] > MAX_WRITTEN_FILES:
                    raise Blocked("Bài làm không được ghi tệp ở vị trí này.")
            elif not inside(text, [home, *roots]):
                raise Blocked("Bài làm chỉ được đọc tệp dữ liệu của đề.")
        elif event in {"os.listdir", "os.scandir", "glob.glob"}:
            if args and isinstance(args[0], (str, bytes, os.PathLike)) and not inside(os.fsdecode(args[0]), [home, *roots]):
                raise Blocked("Bài làm chỉ được đọc tệp dữ liệu của đề.")
        elif event == "import":
            if str(args[0]).split(".")[0] in DENIED_IMPORTS:
                raise Blocked("Bài làm không được dùng thư viện này.")
        elif event.startswith(DENIED_EVENTS):
            raise Blocked("Bài làm không được dùng thao tác này trong môi trường kiểm tra.")

    sys.addaudithook(guard)


def safe_text(value) -> str:
    """The learner's own __str__ can fail; showing a value must not."""
    try:
        return str(value)
    except BaseException:
        return type(value).__name__


def cell_text(cell) -> str:
    """A missing value shows blank. pd.NA has no truth value and an array compares item by item."""
    try:
        return "" if cell != cell else safe_text(cell)
    except (TypeError, ValueError):
        return "" if cell is sys.modules["pandas"].NA else safe_text(cell)


def table_view(name, value) -> dict:
    frame = value.to_frame() if hasattr(value, "to_frame") else value
    # An index can share a column's name, as in df.groupby("a")["a"].count().
    shown = frame.head(MAX_TABLE_ROWS).reset_index(allow_duplicates=True)
    return {"name": name, "shape": list(frame.shape), "columns": [safe_text(column) for column in shown.columns], "rows": [[cell_text(cell) for cell in row] for row in shown.values.tolist()]}


def is_table(value) -> bool:
    return type(value).__name__ in {"DataFrame", "Series"} and type(value).__module__.startswith("pandas")


def error_view(error: BaseException, source: str) -> dict:
    """Only the learner's own lines: library frames and folders stay out."""
    frames = [frame for frame in traceback.walk_tb(error.__traceback__) if frame[0].f_code.co_filename == ANSWER_FILE]
    code = source.splitlines()
    numbers = [number for _, number in frames[-4:]]
    lines = [f"Dòng {number}: {code[number - 1].strip()}" for number in numbers if 0 < number <= len(code)]
    message = safe_text(error).replace(os.getcwd(), ".")[:600]
    return {"type": type(error).__name__, "message": message, "line": numbers[-1] if numbers else None, "traceback": "\n".join([*lines, f"{type(error).__name__}: {message}"])}


def figures() -> tuple[list[str], Optional[BaseException]]:
    """Drawing is when a bad figure fails, so a failure belongs to the learner's code."""
    plt = sys.modules.get("matplotlib.pyplot")
    images = []
    failure = None
    if plt:
        for number in plt.get_fignums()[:MAX_FIGURES]:
            buffer = io.BytesIO()
            try:
                plt.figure(number).savefig(buffer, format="png", dpi=90, bbox_inches="tight")
            except BaseException as caught:
                failure = failure or caught
                continue
            images.append(base64.b64encode(buffer.getvalue()).decode("ascii"))
    return images, failure


def tables_of(scope: dict, shown) -> list[dict]:
    named = [(name, value) for name, value in scope.items() if is_table(value) and not name.startswith("_")][-MAX_TABLES:]
    views = []
    for name, value in named + [("", shown)] * is_table(shown):
        try:
            views.append(table_view(name, value))
        except BaseException:
            continue  # A table that cannot be shown must not cost the output of a run that worked.
    return views


def execute(source: str) -> dict:
    tree = ast.parse(source, ANSWER_FILE)
    last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
    scope = {"__name__": "__main__"}
    stdout = io.StringIO()
    shown_text = None
    shown = None
    error = None
    # Showing results runs learner code too (__str__), so it stays redirected.
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
        try:
            exec(compile(tree, ANSWER_FILE, "exec"), scope)
            if last is not None:
                shown = eval(compile(ast.Expression(last.value), ANSWER_FILE, "eval"), scope)
                shown_text = None if shown is None else str(shown)
        except BaseException as caught:
            error = error_view(caught, source)
        output = stdout.getvalue()[:MAX_STDOUT_CHARS]
        tables = tables_of(scope, shown)
        images, drawing_failure = figures()
    if drawing_failure and not error:
        error = error_view(drawing_failure, source)
    # Like a notebook: the value of the last line counts as output.
    graded = output if shown_text is None else f"{output}\n{shown_text}"
    return {"status": "RUNTIME_ERROR" if error else "OK", "stdout": output, "output_text": graded[:MAX_STDOUT_CHARS], "error": error, "tables": tables, "figures": images}


def main() -> None:
    real_stdout = sys.stdout
    job = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    limit_process(MEMORY_BYTES, CPU_SECONDS)
    sys.path.extend(job["site_paths"])
    started = time.monotonic()
    if "numpy" in job["modules"] or "pandas" in job["modules"]:
        import numpy  # noqa: F401
    if "pandas" in job["modules"]:
        import pandas  # noqa: F401
    if "matplotlib" in job["modules"]:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot  # noqa: F401
    install_guard(os.getcwd(), job["read_roots"])
    # Everything up to here is the sandbox's own start; from here a failure belongs to the learner's run.
    real_stdout.write(READY)
    real_stdout.flush()
    result = execute(job["source"])
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    # ASCII output: -I ignores PYTHONIOENCODING, so stdout may not be able to encode Vietnamese.
    real_stdout.write(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
