"""Keep the detached download worker advancing after a worker exits."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(os.getenv("SAUDI_STA_MODEL_ROOT", r"D:\models"))
STATUS = ROOT / "_downloads/worker-status.json"
SUPERVISOR_STATUS = ROOT / "_downloads/supervisor-status.json"
WORKER = Path(__file__).with_name("download_worker.py")
MAX_RESTARTS = 3


def read() -> dict:
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> int:
    # Do not compete with the currently active transfer.  Once its PID exits,
    # launch one fresh worker, which reads the same pinned external state.
    restarts = 0
    while True:
        state = read()
        pid = state.get("pid")
        worker_state = state.get("state")
        if worker_state == "QUEUE_COMPLETE":
            SUPERVISOR_STATUS.write_text(json.dumps({"state": "STOPPED", "reason": "NORMAL_QUEUE_COMPLETION", "updated_at": time.time()}), encoding="utf-8")
            return 0
        if worker_state == "WAITING_METADATA" and alive(pid):
            time.sleep(10)
            continue
        if not alive(pid):
            restarts += 1
            if restarts > MAX_RESTARTS:
                SUPERVISOR_STATUS.write_text(json.dumps({"state": "FAILED", "reason": "RESTART_LIMIT", "updated_at": time.time()}), encoding="utf-8")
                return 2
            state["state"] = "INTERRUPTED"
            state["last_error"] = "WORKER_EXITED_WITH_PENDING_QUEUE"
            STATUS.write_text(json.dumps(state, indent=2), encoding="utf-8")
            SUPERVISOR_STATUS.write_text(json.dumps({"state": "RESTARTING", "attempt": restarts, "updated_at": time.time()}), encoding="utf-8")
            subprocess.Popen([sys.executable, str(WORKER)], close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return 0
        time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
