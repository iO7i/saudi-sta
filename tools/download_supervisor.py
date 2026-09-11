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
WORKER = Path(__file__).with_name("download_worker.py")


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
    while True:
        state = read()
        pid = state.get("pid")
        if state.get("state") in {"QUEUE_COMPLETE", "FAILED", "STOPPED"} or not alive(pid):
            subprocess.Popen([sys.executable, str(WORKER)], close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return 0
        time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
