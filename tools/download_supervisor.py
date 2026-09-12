"""Keep the detached download worker advancing after a worker exits."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import ctypes
from pathlib import Path


ROOT = Path(os.getenv("SAUDI_STA_MODEL_ROOT", r"D:\models"))
STATUS = ROOT / "_downloads/worker-status.json"
MANIFEST = ROOT / "_downloads/manifest.json"
SUPERVISOR_STATUS = ROOT / "_downloads/supervisor-status.json"
SUPERVISOR_LOG = ROOT / "_downloads/supervisor-events.jsonl"
WORKER = Path(__file__).with_name("download_worker.py")
MAX_RESTARTS = 3
TERMINAL_STATES = {"INTEGRITY_VERIFIED", "BLOCKED_ACCESS", "BLOCKED_USER_ACTION", "FAILED_RETRY_EXHAUSTED"}


def read() -> dict:
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def queue_complete() -> bool:
    queue = read_manifest().get("frozen_queue", [])
    states = [str(entry.get("state", "QUEUED")) for entry in queue]
    return bool(states) and all(state in TERMINAL_STATES for state in states)


def write_supervisor(value: dict) -> None:
    SUPERVISOR_STATUS.parent.mkdir(parents=True, exist_ok=True)
    temp = SUPERVISOR_STATUS.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temp, SUPERVISOR_STATUS)


def supervisor_log(event: dict) -> None:
    SUPERVISOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": time.time(), **event}, ensure_ascii=False) + "\n")


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        try:
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def exit_code(pid: int | None) -> int | None:
    if not pid or os.name != "nt":
        return None
    process_query_limited_information = 0x1000
    still_active = 259
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return None
    value = ctypes.c_ulong()
    try:
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(value)):
            return None
        return None if value.value == still_active else int(value.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def main() -> int:
    # Keep supervising until the worker has genuinely completed the frozen
    # queue. A worker exit with pending items is an interruption, not success.
    try:
        previous_supervisor = json.loads(SUPERVISOR_STATUS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous_supervisor = {}
    previous_pid = previous_supervisor.get("worker_pid")
    restarts = 0 if previous_supervisor.get("state") == "ACTIVE" and alive(previous_pid) else int(previous_supervisor.get("restart_attempt", 0) or 0)
    while True:
        state = read()
        pid = state.get("pid")
        worker_state = state.get("state")
        manifest_complete = queue_complete()
        if worker_state == "QUEUE_COMPLETE" and manifest_complete:
            write_supervisor({"state": "STOPPED", "reason": "NORMAL_QUEUE_COMPLETION", "restart_attempt": restarts, "updated_at": time.time()})
            supervisor_log({"event": "SUPERVISOR_STOPPED", "reason": "NORMAL_QUEUE_COMPLETION", "worker_id": state.get("worker_id"), "worker_pid": pid})
            return 0
        if worker_state == "STOPPED" and state.get("stop_requested"):
            write_supervisor({"state": "STOPPED", "reason": "USER_STOP_REQUESTED", "restart_attempt": restarts, "updated_at": time.time()})
            supervisor_log({"event": "SUPERVISOR_STOPPED", "reason": "USER_STOP_REQUESTED", "worker_id": state.get("worker_id"), "worker_pid": pid})
            return 0
        if worker_state == "WAITING_METADATA" and alive(pid):
            time.sleep(10)
            continue
        if alive(pid):
            write_supervisor({"state": "ACTIVE", "worker_pid": pid, "worker_id": state.get("worker_id"), "pending_queue": not manifest_complete, "restart_attempt": restarts, "updated_at": time.time()})
            time.sleep(10)
            continue
        # A worker that disappeared before publishing a terminal state is an
        # interruption, never successful queue completion.
        restarts += 1
        if restarts > MAX_RESTARTS:
            write_supervisor({"state": "FAILED", "reason": "RESTART_LIMIT", "pending_queue": not manifest_complete, "restart_attempt": restarts, "updated_at": time.time()})
            supervisor_log({"event": "SUPERVISOR_FAILED", "reason": "RESTART_LIMIT", "worker_id": state.get("worker_id"), "worker_pid": pid, "exit_code": exit_code(pid), "pending_queue": not manifest_complete})
            return 2
        restart_reason = "WORKER_EXITED_WITH_PENDING_QUEUE" if not manifest_complete else "WORKER_EXITED_BEFORE_COMPLETION_STATE"
        supervisor_log({
            "event": "WORKER_EXITED",
            "generation_id": state.get("worker_id"),
            "pid": pid,
            "exit_time": time.time(),
            "exit_code": exit_code(pid),
            "restart_reason": restart_reason,
            "durable_local_bytes": state.get("actual_disk_bytes", state.get("downloaded_bytes", 0)),
            "tracked_bytes": state.get("downloaded_bytes", 0),
            "retry_number": state.get("retry_number", 0),
            "source": state.get("current_source"),
            "etag": state.get("source_etag"),
            "next_resume_offset": state.get("resume_offset", state.get("actual_disk_bytes", 0)),
            "restart_attempt": restarts,
        })
        state["state"] = "INTERRUPTED"
        state["last_error"] = restart_reason
        state["supervisor_restart_attempt"] = restarts
        state["updated_at"] = time.time()
        temp = STATUS.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(temp, STATUS)
        write_supervisor({"state": "RESTARTING", "attempt": restarts, "restart_attempt": restarts, "pending_queue": not manifest_complete, "updated_at": time.time()})
        subprocess.Popen([sys.executable, str(WORKER)], close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # Continue supervising the newly launched worker. Do not return and
        # leave a single restart unmonitored.
        time.sleep(2)
        continue


if __name__ == "__main__":
    raise SystemExit(main())
