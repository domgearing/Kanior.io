"""Content-free operational checks for the single-user local runtime."""

from __future__ import annotations

import json
import socket
import ssl
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Settings  # noqa: E402

STATUS = ROOT / ".artifacts" / "local-release" / "status.json"
BACKUP_STATUS = ROOT / ".artifacts" / "local-release" / "backup-status.json"


def http_ok(url: str) -> bool:
    try:
        response = httpx.get(
            url,
            timeout=4,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (Verelo local health check)"},
        )
        return response.status_code == 200
    except (httpx.HTTPError, ValueError):
        return False


def tls_reachable(url: str) -> bool:
    from urllib.parse import urlsplit

    target = urlsplit(url)
    if target.scheme != "https" or target.hostname is None:
        return False
    try:
        with socket.create_connection((target.hostname, target.port or 443), timeout=4) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=target.hostname):
                return True
    except (OSError, ValueError, ssl.SSLError):
        return False


def database_ok(url: str) -> bool:
    engine = create_engine(url, connect_args={"connect_timeout": 3}, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return bool(connection.execute(text("SELECT 1")).scalar_one() == 1)
    except Exception:
        return False
    finally:
        engine.dispose()


def process_status() -> dict[str, bool]:
    try:
        report = json.loads(STATUS.read_text(encoding="utf-8"))
        checked = datetime.fromisoformat(report["checked_at"])
        fresh = (datetime.now(UTC) - checked).total_seconds() < 20
        return {
            name: fresh and bool(report["components"][name]["running"])
            for name in ("api", "worker")
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"api": False, "worker": False}


def backup_status() -> tuple[bool, str]:
    try:
        report = json.loads(BACKUP_STATUS.read_text(encoding="utf-8"))
        checked = datetime.fromisoformat(report["last_success_at"])
        fresh = 0 <= (datetime.now(UTC) - checked).total_seconds() < 48 * 60 * 60
        state = report["state"]
        code = report["code"]
        if not isinstance(code, str) or not code.replace("_", "").isalnum():
            return False, "invalid_status"
        if state != "ok":
            return False, code
        return fresh, "verified" if fresh else "backup_stale"
    except (OSError, ValueError, KeyError, TypeError):
        return False, "backup_not_verified"


def collect_checks(settings: Settings) -> dict[str, bool]:
    port = settings.api_port
    checks = {
        "database": database_ok(settings.database_url),
        "local_api": http_ok(f"http://127.0.0.1:{port}/ready"),
        "local_web": http_ok(f"http://127.0.0.1:{port}/"),
        "public_api": bool(settings.api_public_origin)
        and http_ok(f"{str(settings.api_public_origin).rstrip('/')}/ready"),
        "public_web": bool(settings.public_origin)
        and http_ok(str(settings.public_origin).rstrip("/") + "/"),
        "recall_reachable": bool(settings.recall_api_base_url)
        and tls_reachable(str(settings.recall_api_base_url)),
        "assemblyai_reachable": tls_reachable(str(settings.assemblyai_api_base_url)),
        "b2_reachable": bool(settings.b2_s3_endpoint)
        and tls_reachable(str(settings.b2_s3_endpoint)),
    }
    checks.update({f"{name}_process": ok for name, ok in process_status().items()})
    checks["backup"] = backup_status()[0]
    return checks


def main() -> int:
    checks = collect_checks(Settings())
    for name, ok in checks.items():
        suffix = f" ({backup_status()[1]})" if name == "backup" and not ok else ""
        print(f"{name}: {'OK' if ok else 'DOWN'}{suffix}")
    print("Provider checks prove TLS reachability, not credential validity or paid-job success.")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
