"""Detached, resumable model-artifact worker.

This process owns only external files under D:\\models.  It never imports the
application, loads a model, or changes a route.  State is written atomically
to the external manifest/status files so the main app can inspect it without
polling or keeping this process attached to a conversation.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(os.getenv("SAUDI_STA_MODEL_ROOT", r"D:\models"))
STATE = ROOT / "_downloads"
MANIFEST = STATE / "manifest.json"
STATUS = STATE / "worker-status.json"
LOG = STATE / "download-log.jsonl"
LOCK = STATE / "worker.lock"
HEARTBEAT_SECONDS = 5
STALE_SECONDS = 90


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def log(event: dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": now(), **event}, ensure_ascii=False) + "\n")


def mark_manifest(item: dict[str, Any], state: str, *, actual_sha256: str | None = None, actual_bytes: int | None = None) -> None:
    body = read_json(MANIFEST, {})
    changed = False
    for entry in body.get("queue", []):
        for file_entry in entry.get("files", []):
            if str(file_entry.get("path", "")).replace("/", "\\").lower() == str(item["path"]).replace("/", "\\").lower() or file_entry.get("name") == item["file"]:
                file_entry["status"] = state
                if actual_sha256:
                    file_entry["sha256"] = actual_sha256
                if actual_bytes is not None:
                    file_entry["downloaded_bytes"] = actual_bytes
                changed = True
    if not changed:
        body.setdefault("verified_artifacts", []).append({"model": item["model"], "file": item["file"], "path": str(item["path"]), "bytes": actual_bytes, "sha256": actual_sha256, "state": state})
    atomic_json(MANIFEST, body)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pid_alive(pid: int | None) -> bool:
    if not pid or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def acquire_lock(worker_id: str) -> None:
    existing = read_json(LOCK, {})
    if pid_alive(existing.get("pid")):
        raise SystemExit(f"worker already active: {existing}")
    # Exclusive creation closes the check-then-write race when two launchers
    # start at the same time. A stale lock is recoverable only after its PID is
    # demonstrably dead.
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        with LOCK.open("x", encoding="utf-8") as handle:
            json.dump({"worker_id": worker_id, "pid": os.getpid(), "started_at": now()}, handle)
    except FileExistsError:
        existing = read_json(LOCK, {})
        if pid_alive(existing.get("pid")):
            raise SystemExit(f"worker already active: {existing}")
        LOCK.unlink(missing_ok=True)
        with LOCK.open("x", encoding="utf-8") as handle:
            json.dump({"worker_id": worker_id, "pid": os.getpid(), "started_at": now()}, handle)


def release_lock() -> None:
    try:
        LOCK.unlink()
    except FileNotFoundError:
        pass


def update_status(base: dict[str, Any], **changes: Any) -> None:
    base.update(changes)
    base["last_heartbeat"] = now()
    atomic_json(STATUS, base)


def descriptor_queue(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the resolved queue, preserving the active projector first."""
    items: list[dict[str, Any]] = [{
        "model": "audarai/Audar-ASR-V1-Flash", "candidate_id": "AUDAR_FLASH_Q8_LOCAL",
        "revision": "54274d39245beba38f30048128e231d4176bd91d", "file": "mmproj-Audar-ASR-V1-Flash.gguf",
        "url": "https://huggingface.co/audarai/Audar-ASR-V1-Flash/resolve/54274d39245beba38f30048128e231d4176bd91d/mmproj-Audar-ASR-V1-Flash.gguf?download=true",
        "path": ROOT / "audar/Audar-ASR-V1-Flash/mmproj-Audar-ASR-V1-Flash.gguf", "bytes": 378575424,
        "sha256": "73f06fc82a009b4a9d6c825782a3676cb553402b3a5ecc27ae77a92caa6b7fa9",
    }]
    for entry in manifest.get("queue", []):
        model = entry.get("model", "")
        if model == "FireRedTeam/FireRedVAD":
            for item in entry.get("files", []):
                if item.get("sha256"):
                    items.append({"model": model, "candidate_id": entry.get("candidate_id"), "revision": entry.get("revision"), "file": item["name"], "url": f"https://huggingface.co/{model}/resolve/{entry['revision']}/{item['name']}?download=true", "path": Path(item["path"]), "bytes": item["bytes"], "sha256": item["sha256"]})
        elif model == "audarai/Audar-Diarization-V1":
            for item in entry.get("files", []):
                if item.get("sha256"):
                    items.append({"model": model, "candidate_id": entry.get("candidate_id"), "revision": entry.get("revision"), "file": item["name"], "url": f"https://huggingface.co/{model}/resolve/{entry['revision']}/{item['name']}?download=true", "path": Path(item["path"]), "bytes": item["bytes"], "sha256": item["sha256"]})
    # Metadata resolved during the bridge phase; the BF16 projector is shared
    # with Q4 and is intentionally not duplicated here.
    items.append({
        "model": "audarai/Audar-ASR-V1-Turbo", "candidate_id": "AUDAR_TURBO_Q8_LOCAL", "revision": "371428bea487c7aec82b27dc21f8d4324002e98e",
        "file": "Audar-ASR-V1-Turbo-Q8_0.gguf", "url": "https://huggingface.co/audarai/Audar-ASR-V1-Turbo/resolve/371428bea487c7aec82b27dc21f8d4324002e98e/Audar-ASR-V1-Turbo-Q8_0.gguf?download=true",
        "path": ROOT / "audar/Audar-ASR-V1-Turbo/Audar-ASR-V1-Turbo-Q8_0.gguf", "bytes": 2165034848, "sha256": "0a91ab40f6a30db06c4186e2f621f504f4625ba6058e639cc09f1cbefded10d2",
    })
    return items


def download(item: dict[str, Any], status: dict[str, Any]) -> bool:
    final = Path(item["path"])
    partial = Path(str(final) + ".part")
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.is_file() and final.stat().st_size == item["bytes"] and sha256(final).lower() == item["sha256"].lower():
        mark_manifest(item, "INTEGRITY_VERIFIED", actual_sha256=item["sha256"], actual_bytes=final.stat().st_size)
        log({"model": item["model"], "file": item["file"], "state": "INTEGRITY_VERIFIED", "bytes": final.stat().st_size, "sha256": item["sha256"], "note": "already verified"})
        return True
    status.update({"current_model": item["model"], "current_file": item["file"], "expected_bytes": item["bytes"], "downloaded_bytes": partial.stat().st_size if partial.exists() else 0, "percentage": round((partial.stat().st_size if partial.exists() else 0) * 100 / item["bytes"], 2), "state": "DOWNLOADING", "last_error": None})
    atomic_json(STATUS, {**status, "last_heartbeat": now()})
    command = ["curl.exe", "--fail", "--location", "--retry", "5", "--retry-all-errors", "--connect-timeout", "30", "--continue-at", "-", "--output", str(partial), item["url"]]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
    while process.poll() is None:
        current = partial.stat().st_size if partial.exists() else 0
        update_status(status, state="DOWNLOADING", downloaded_bytes=current, expected_bytes=item["bytes"], percentage=round(current * 100 / item["bytes"], 2))
        time.sleep(HEARTBEAT_SECONDS)
    current = partial.stat().st_size if partial.exists() else 0
    if process.returncode != 0:
        update_status(status, state="FAILED", downloaded_bytes=current, percentage=round(current * 100 / item["bytes"], 2), last_error=f"curl_exit_{process.returncode}")
        log({"model": item["model"], "file": item["file"], "state": "FAILED", "bytes": current, "expected_bytes": item["bytes"], "error": f"curl_exit_{process.returncode}"})
        return False
    actual = sha256(partial)
    if current != item["bytes"] or actual.lower() != item["sha256"].lower():
        update_status(status, state="FAILED", downloaded_bytes=current, percentage=round(current * 100 / item["bytes"], 2), last_error="SIZE_OR_HASH_MISMATCH")
        log({"model": item["model"], "file": item["file"], "state": "FAILED", "bytes": current, "expected_bytes": item["bytes"], "sha256": actual, "expected_sha256": item["sha256"], "error": "SIZE_OR_HASH_MISMATCH"})
        return False
    os.replace(partial, final)
    mark_manifest(item, "INTEGRITY_VERIFIED", actual_sha256=actual, actual_bytes=current)
    log({"model": item["model"], "file": item["file"], "state": "INTEGRITY_VERIFIED", "bytes": current, "sha256": actual})
    update_status(status, state="INTEGRITY_VERIFIED", downloaded_bytes=current, percentage=100, last_error=None)
    return True


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    worker_id = f"download-worker-{uuid.uuid4().hex[:12]}"
    acquire_lock(worker_id)
    manifest = read_json(MANIFEST, {})
    queue = descriptor_queue(manifest)
    status: dict[str, Any] = {"worker_id": worker_id, "pid": os.getpid(), "started_at": now(), "last_heartbeat": now(), "current_model": None, "current_file": None, "downloaded_bytes": 0, "expected_bytes": 0, "percentage": 0, "state": "STARTING", "last_error": None, "next_model": queue[0]["model"] if queue else None}
    atomic_json(STATUS, status)
    log({"event": "WORKER_STARTED", "worker_id": worker_id, "pid": os.getpid(), "queue_length": len(queue)})
    try:
        for index, item in enumerate(queue):
            status["next_model"] = queue[index + 1]["model"] if index + 1 < len(queue) else None
            update_status(status, state="QUEUED", current_model=item["model"], current_file=item["file"])
            download(item, status)
        update_status(status, state="QUEUE_COMPLETE", current_model=None, current_file=None, next_model=None)
        log({"event": "QUEUE_COMPLETE", "worker_id": worker_id})
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
