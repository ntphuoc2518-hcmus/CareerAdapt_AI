"""Disposable SQL worker. Runs as its own process, never imported by the API.

Reads {source, columns, rows} from stdin and writes one JSON result to stdout. The process gets an
empty environment, a temporary working directory and an in-memory database that receives the
dataset through stdin. SQLite's authorizer allows only reads of the dataset table, and the parent
kills the process on timeout, so a query cannot touch files, the network or the API's memory.
"""
import json
import sqlite3
import sys
import time

TIME_LIMIT_SECONDS = 0.8
HEAP_LIMIT_BYTES = 64 * 1024 * 1024
MAX_RESULT_ROWS = 1000
MAX_STATEMENTS = 12
SAFE_FUNCTIONS = {
    "sum", "total", "avg", "count", "min", "max", "round", "abs", "coalesce", "nullif", "ifnull", "iif", "lower", "upper", "trim", "ltrim", "rtrim",
    "replace", "substr", "substring", "instr", "length", "printf", "format", "strftime", "date", "datetime", "julianday", "cast", "typeof",
    "group_concat", "row_number", "rank", "dense_rank", "lag", "lead", "first_value", "last_value", "ntile", "percent_rank", "cume_dist",
}


def limit_process(memory_bytes: int = 256 * 1024 * 1024, cpu_seconds: int = 2) -> None:
    """Best-effort OS limits on top of the parent's kill-on-timeout."""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    except (ImportError, ValueError, OSError):
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

            class IO(ctypes.Structure):
                _fields_ = [(name, ctypes.c_ulonglong) for name in ("r", "w", "o", "rb", "wb", "ob")]

            class EXTENDED(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            job = kernel32.CreateJobObjectW(None, None)
            info = EXTENDED()
            info.BasicLimitInformation.LimitFlags = 0x100 | 0x8 | 0x2  # process memory, active process and CPU time limits
            info.BasicLimitInformation.ActiveProcessLimit = 1
            info.BasicLimitInformation.PerProcessUserTimeLimit = cpu_seconds * 10_000_000
            info.ProcessMemoryLimit = memory_bytes
            kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
            kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
        except (OSError, AttributeError, ValueError):
            pass


def split_statements(source: str) -> list:
    statements, buffer = [], ""
    for line in source.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())
    return statements


def run(job: dict) -> dict:
    columns, rows = job["columns"], job["rows"]
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    # NUMERIC affinity stores "0" and "0.25" as numbers so `quantity > 0` behaves as learners expect.
    definition = ", ".join('"' + column.replace('"', '""') + '" NUMERIC' for column in columns)
    connection.execute(f"CREATE TABLE orders_raw ({definition})")
    connection.executemany(f"INSERT INTO orders_raw VALUES ({','.join('?' for _ in columns)})", rows)
    connection.commit()
    connection.execute(f"PRAGMA hard_heap_limit = {HEAP_LIMIT_BYTES}")
    connection.execute("PRAGMA query_only = ON")
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}

    def authorize(action, arg1, arg2, database, trigger):
        if action not in allowed:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or arg1 or "").lower() not in SAFE_FUNCTIONS:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and arg1 != "orders_raw" and arg1:
            # CTE and subquery names are reported with an empty table argument by SQLite.
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(authorize)
    connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 500_000)
    connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 64)
    connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    started = time.monotonic()
    connection.set_progress_handler(lambda: int(time.monotonic() - started > TIME_LIMIT_SECONDS), 1000)
    result_sets = []
    for statement in split_statements(job["source"])[:MAX_STATEMENTS]:
        cursor = connection.execute(statement)
        if cursor.description:
            result_sets.append({
                "columns": [column[0] for column in cursor.description],
                "rows": [list(row) for row in cursor.fetchmany(MAX_RESULT_ROWS)],
            })
    connection.close()
    return {"executed": bool(result_sets), "result_sets": result_sets, "error": None}


def main() -> None:
    limit_process()
    try:
        job = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        result = run(job)
    except sqlite3.OperationalError as error:
        message = "Truy vấn vượt giới hạn thời gian." if "interrupted" in str(error) else f"Truy vấn không chạy được: {str(error)[:180]}"
        result = {"executed": False, "result_sets": [], "error": message}
    except (sqlite3.Error, ValueError, MemoryError) as error:
        result = {"executed": False, "result_sets": [], "error": f"Truy vấn không chạy được: {str(error)[:180]}"}
    # ASCII output: -I ignores PYTHONIOENCODING, so stdout may not be able to encode Vietnamese.
    sys.stdout.write(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
