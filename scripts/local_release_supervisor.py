"""Keep the local API and scoped worker supervisor alive without logging content."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Settings  # noqa: E402
from scripts.local_release_status import collect_checks  # noqa: E402

STATUS = ROOT / ".artifacts" / "local-release" / "status.json"
EVENTS = STATUS.parent / "events.jsonl"
ALERT_CHECKS = frozenset(
    {"database", "local_api", "public_api", "public_web", "api_process", "worker_process", "backup"}
)


def write_event(kind: str, component: str, code: str) -> None:
    """Keep bounded, content-free diagnostics even when child output is discarded."""
    try:
        EVENTS.parent.mkdir(parents=True, exist_ok=True)
        if EVENTS.exists() and EVENTS.stat().st_size > 1024 * 1024:
            EVENTS.replace(EVENTS.with_suffix(".previous.jsonl"))
        record = {
            "at": datetime.now(UTC).isoformat(),
            "kind": kind,
            "component": component,
            "code": code,
        }
        with EVENTS.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        pass


def notify_problem(names: set[str]) -> None:
    if os.name != "nt" or not names:
        return
    message = (
        "Checks need attention: " + ", ".join(sorted(names)) + ". Run local_release_status.py."
    )
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(ROOT / "scripts" / "local-release-notify.ps1"),
                "-Message",
                message,
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        write_event("alert", "desktop", "notification_unavailable")


def alert_transition(
    previous_bad: set[str],
    bad: set[str],
    bad_samples: int,
    alerted_bad: set[str],
) -> tuple[int, set[str], bool]:
    samples = bad_samples + 1 if bad and bad == previous_bad else 1 if bad else 0
    should_notify = samples >= 2 and bad != alerted_bad
    return samples, set(bad) if should_notify or not bad else set(alerted_bad), should_notify


def git_bash() -> str:
    configured = os.environ.get("VERELO_GIT_BASH")
    if configured and Path(configured).is_file():
        return configured
    installed = (
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "bin" / "bash.exe"
    )
    if installed.is_file():
        return str(installed)
    binary = shutil.which("bash")
    if binary is None or (os.name == "nt" and "system32" in binary.lower()):
        raise RuntimeError("Git Bash is required for the local worker supervisor")
    return binary


def write_status(
    processes: dict[str, subprocess.Popen[bytes]],
    restarts: dict[str, int],
    health: dict[str, bool],
) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "components": {
            name: {
                "running": process.poll() is None,
                "pid": process.pid,
                "restarts": restarts[name],
            }
            for name, process in processes.items()
        },
        "health": health,
    }
    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
    temporary.replace(STATUS)


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    port = int(os.environ.get("VERELO_API_PORT", "8000"))
    commands = {
        "api": [
            sys.executable,
            "-m",
            "uvicorn",
            "api.local_release_entry:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        "worker": [git_bash(), "scripts/local-worker-supervisor.sh"],
    }
    processes: dict[str, subprocess.Popen[bytes]] = {}
    restarts = {name: 0 for name in commands}
    health: dict[str, bool] = {}
    last_health_check = 0.0
    previous_bad: set[str] = set()
    bad_samples = 0
    alerted_bad: set[str] = set()
    stopping = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        while not stopping:
            for name, command in commands.items():
                current = processes.get(name)
                if current is not None and current.poll() is None:
                    continue
                if current is not None:
                    restarts[name] += 1
                    write_event("process", name, f"exited_{current.returncode}")
                processes[name] = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                write_event("process", name, "started")
            write_status(processes, restarts, health)
            if time.monotonic() - last_health_check >= 60:
                updated = collect_checks(Settings())
                for name, ok in updated.items():
                    if health.get(name) is not ok:
                        write_event("health", name, "ok" if ok else "down")
                health = updated
                bad = {name for name in ALERT_CHECKS if not health.get(name, False)}
                bad_samples, alerted_bad, should_notify = alert_transition(
                    previous_bad, bad, bad_samples, alerted_bad
                )
                if should_notify:
                    notify_problem(bad)
                previous_bad = bad
                last_health_check = time.monotonic()
            write_status(processes, restarts, health)
            time.sleep(5)
    finally:
        for process in processes.values():
            stop_process(process)
        write_status(processes, restarts, health)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
