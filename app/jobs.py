"""Small bounded local job runner for slow model-backed routes.

Jobs are intentionally process-local.  The worker thread owns a cancellation
event that is propagated to adapters, which can terminate their child process
when a timeout or explicit cancellation is requested.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable


JobCallable = Callable[[threading.Event], Any]


class LocalJobManager:
    """Execute one bounded local job at a time without blocking the web worker."""

    def __init__(self, *, default_timeout_seconds: float = 360.0) -> None:
        self.default_timeout_seconds = float(default_timeout_seconds)
        self.jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def submit(self, work: JobCallable, *, timeout_seconds: float | None = None, kind: str = "local_route") -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        event = threading.Event()
        timeout = float(timeout_seconds or self.default_timeout_seconds)
        job = {
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "timeout_seconds": timeout,
            "cancel_requested": False,
            "result": None,
            "error": None,
        }
        with self._lock:
            self.jobs[job_id] = {**job, "_cancel_event": event}
        threading.Thread(target=self._run, args=(job_id, work, event, timeout), daemon=True, name=f"saudi-sta-job-{job_id[:8]}").start()
        return self.get(job_id) or job

    def _run(self, job_id: str, work: JobCallable, cancel_event: threading.Event, timeout_seconds: float) -> None:
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job["status"] = "running"
            job["started_at"] = time.time()
        timeout_fired = threading.Event()

        def trip_timeout() -> None:
            timeout_fired.set()
            cancel_event.set()
            # Publish the terminal timeout immediately.  Cooperative adapters
            # will unwind and let _run retain the same state; a non-cooperative
            # callable cannot leave the browser believing the job is healthy
            # indefinitely.
            with self._lock:
                current = self.jobs.get(job_id)
                if current and current["status"] in {"queued", "running"}:
                    current["status"] = "timed_out"
                    current["error"] = "LOCAL_JOB_TIMEOUT"
                    current["finished_at"] = time.time()

        timer = threading.Timer(timeout_seconds, trip_timeout)
        timer.daemon = True
        timer.start()
        timed_out = False
        try:
            result = work(cancel_event)
            timed_out = timeout_fired.is_set()
            with self._lock:
                job = self.jobs.get(job_id)
                if not job:
                    return
                if timed_out:
                    job["status"] = "timed_out"
                    job["error"] = "LOCAL_JOB_TIMEOUT"
                elif job["cancel_requested"] or cancel_event.is_set():
                    job["status"] = "cancelled"
                else:
                    job["status"] = "completed"
                job["result"] = result if job["status"] == "completed" else result
                job["finished_at"] = time.time()
        except Exception as exc:  # retain a bounded, inspectable failure
            with self._lock:
                job = self.jobs.get(job_id)
                if job:
                    elapsed = time.time() - float(job["started_at"] or time.time())
                    if timeout_fired.is_set() or (cancel_event.is_set() and elapsed >= timeout_seconds):
                        job["status"] = "timed_out"
                        job["error"] = "LOCAL_JOB_TIMEOUT"
                    elif job["cancel_requested"] or cancel_event.is_set():
                        job["status"] = "cancelled"
                        job["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
                    else:
                        job["status"] = "failed"
                        job["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
                    job["finished_at"] = time.time()
        finally:
            timer.cancel()

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            if job["status"] in {"queued", "running"}:
                job["cancel_requested"] = True
                job["_cancel_event"].set()
                if job["status"] == "queued":
                    job["status"] = "cancelled"
                    job["finished_at"] = time.time()
            return self._public(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self.jobs.get(job_id)
            return self._public(job) if job else None

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in job.items() if not key.startswith("_")}
