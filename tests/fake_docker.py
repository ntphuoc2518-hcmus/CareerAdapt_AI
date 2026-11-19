"""A stand-in for the docker CLI, used only by tests/test_container_sandbox.py.

Docker is not installed on every development machine, so this script checks the integration instead:
it records the exact `docker run` arguments, maps the two bind mounts (/sandbox and /work) back to the
host folders, rewrites the container library paths in the job to this interpreter's, and runs the same
worker the container would run. It proves the command, the mounts and the stdin/stdout protocol; it
gives none of a real container's isolation.
"""
import json
import os
import subprocess
import sys
import sysconfig

LOG = os.environ.get("FAKE_DOCKER_LOG")


def main() -> int:
    args = sys.argv[1:]
    if args[:2] == ["image", "inspect"]:
        return 1 if os.environ.get("FAKE_DOCKER_NO_IMAGE") == "1" else 0
    if not args or args[0] != "run":
        return 2
    if LOG:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(args) + "\n")
    mounts = {}
    for index, value in enumerate(args):
        if value == "--mount":
            fields = dict(part.split("=", 1) for part in args[index + 1].split(",") if "=" in part)
            mounts[fields["target"]] = fields["source"]
    script = args[-1]
    host_script = script.replace("/sandbox", mounts["/sandbox"], 1)
    job = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if "site_paths" in job:
        site = sysconfig.get_paths()["purelib"]
        job["site_paths"] = [site]
        job["read_roots"] = [sys.base_prefix, sys.prefix, site, os.environ.get("TEMP", "/tmp")]
    completed = subprocess.run([sys.executable, "-I", "-S", host_script], input=json.dumps(job).encode("utf-8"), capture_output=True, cwd=mounts["/work"],
                               env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "MPLBACKEND": "Agg", "MPLCONFIGDIR": os.environ.get("TEMP", "/tmp")})
    sys.stdout.buffer.write(completed.stdout)
    sys.stderr.buffer.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
