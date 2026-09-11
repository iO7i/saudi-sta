"""Read-only view of the detached external download worker."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())
    except ValueError:
        return None


def read_worker_status(path: str | Path = r"D:\models\_downloads\worker-status.json", *, stale_after_seconds: int = 90) -> dict[str, Any]:
    status_path = Path(path)
    try:
        body = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"effective_state": "STOPPED", "reason": "WORKER_STATUS_MISSING"}
    if not isinstance(body, dict):
        return {"effective_state": "FAILED", "reason": "WORKER_STATUS_INVALID"}
    pid = body.get("pid") if isinstance(body.get("pid"), int) else None
    age = _age_seconds(body.get("last_heartbeat"))
    process_alive = _pid_alive(pid)
    state = str(body.get("state", "UNKNOWN"))
    if state == "DOWNLOADING":
        effective = "ACTIVE" if process_alive and age is not None and age <= stale_after_seconds else "STALE"
    elif state == "FAILED":
        effective = "FAILED"
    elif state in {"QUEUE_COMPLETE", "STOPPED"}:
        effective = "STOPPED"
    else:
        effective = state
    return {**body, "effective_state": effective, "heartbeat_age_seconds": age, "process_alive": process_alive, "stale_after_seconds": stale_after_seconds}

