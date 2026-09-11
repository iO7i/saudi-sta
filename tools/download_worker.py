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
MAX_INTEGRITY_RETRIES = 2
TERMINAL_STATES = {"INTEGRITY_VERIFIED", "BLOCKED_ACCESS", "BLOCKED_USER_ACTION", "FAILED_RETRY_EXHAUSTED"}
FROZEN_QUEUE = [
    "Whisper Large v3", "Audar Turbo Q4 + projector", "Audar Turbo Q8", "Audar Flash Q8 + projector", "FireRedVAD",
    "Audar Diarization V1", "LiveKit Turn Detector v1-mini", "Cohere Transcribe Arabic 07-2026", "Qwen3.8-27B Q6_K_L",
    "Granite 4.1-30B Q6_K", "BTL-4 Q6_K_L", "Meta OmniASR-LLM-7B", "Audar TTS V1 Turbo + NeuCodec", "Qwen3-Omni-30B-A3B-Instruct",
]
MODEL_LABELS = {
    "audarai/Audar-Diarization-V1": "Audar Diarization V1",
    "audarai/Audar-ASR-V1-Turbo": "Audar Turbo Q8",
    "audarai/Audar-ASR-V1-Flash": "Audar Flash Q8 + projector",
    "FireRedTeam/FireRedVAD": "FireRedVAD",
}


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


def ensure_frozen_queue(body: dict[str, Any]) -> dict[str, Any]:
    items = body.setdefault("frozen_queue", [])
    existing = {entry.get("model") for entry in items if isinstance(entry, dict)}
    for model in FROZEN_QUEUE:
        if model not in existing:
            items.append({"model": model, "state": "QUEUED", "retry_count": 0})
    return body


def set_model_state(model: str, state: str, *, error: str | None = None) -> None:
    body = ensure_frozen_queue(read_json(MANIFEST, {}))
    label = MODEL_LABELS.get(model, model)
    for entry in body["frozen_queue"]:
        if entry.get("model") in {model, label}:
            entry["state"] = state
            if error:
                entry["last_error"] = error
    atomic_json(MANIFEST, body)


def queue_complete_allowed(states: list[str]) -> bool:
    return bool(states) and all(state in TERMINAL_STATES for state in states)


def queue_summary(body: dict[str, Any]) -> dict[str, int]:
    states = [str(entry.get("state", "QUEUED")) for entry in ensure_frozen_queue(body).get("frozen_queue", [])]
    return {"total": len(states), "terminal": sum(state in TERMINAL_STATES for state in states), "pending": sum(state not in TERMINAL_STATES for state in states), "failed": sum(state in {"FAILED_RETRY_EXHAUSTED", "FAILED"} for state in states), "blocked": sum(state in {"BLOCKED_ACCESS", "BLOCKED_USER_ACTION"} for state in states)}


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
    set_model_state(item["model"], "RETRY_PENDING" if partial.exists() else "METADATA_RESOLVED")
    if partial.exists() and partial.stat().st_size > item["bytes"]:
        quarantined = partial.with_name(partial.name + f".invalid-{int(time.time())}")
        os.replace(partial, quarantined)
        log({"model": item["model"], "file": item["file"], "state": "INVALID_PARTIAL_QUARANTINED", "bytes": quarantined.stat().st_size, "expected_bytes": item["bytes"], "path": str(quarantined)})
        set_model_state(item["model"], "RETRY_PENDING", error="PARTIAL_LARGER_THAN_EXPECTED")
    if final.is_file() and final.stat().st_size == item["bytes"] and sha256(final).lower() == item["sha256"].lower():
        mark_manifest(item, "INTEGRITY_VERIFIED", actual_sha256=item["sha256"], actual_bytes=final.stat().st_size)
        set_model_state(item["model"], "INTEGRITY_VERIFIED")
        log({"model": item["model"], "file": item["file"], "state": "INTEGRITY_VERIFIED", "bytes": final.stat().st_size, "sha256": item["sha256"], "note": "already verified"})
        return True
    for attempt in range(1, MAX_INTEGRITY_RETRIES + 2):
        set_model_state(item["model"], "DOWNLOADING")
        status.update({"current_model": item["model"], "current_file": item["file"], "expected_bytes": item["bytes"], "retry_number": attempt, "downloaded_bytes": partial.stat().st_size if partial.exists() else 0, "percentage": round((partial.stat().st_size if partial.exists() else 0) * 100 / item["bytes"], 2), "state": "DOWNLOADING", "last_error": None})
        atomic_json(STATUS, {**status, "last_heartbeat": now()})
        command = ["curl.exe", "--fail", "--location", "--retry", "5", "--retry-all-errors", "--connect-timeout", "30", "--continue-at", "-", "--output", str(partial), item["url"]]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        while process.poll() is None:
            current = partial.stat().st_size if partial.exists() else 0
            update_status(status, state="DOWNLOADING", downloaded_bytes=current, expected_bytes=item["bytes"], percentage=round(current * 100 / item["bytes"], 2), retry_number=attempt)
            time.sleep(HEARTBEAT_SECONDS)
        current = partial.stat().st_size if partial.exists() else 0
        if process.returncode != 0:
            set_model_state(item["model"], "RETRY_PENDING", error=f"curl_exit_{process.returncode}")
            log({"model": item["model"], "file": item["file"], "state": "RETRY_PENDING", "attempt": attempt, "bytes": current, "expected_bytes": item["bytes"], "error": f"curl_exit_{process.returncode}"})
            continue
        actual = sha256(partial)
        if current != item["bytes"] or actual.lower() != item["sha256"].lower():
            quarantined = partial.with_name(partial.name + f".invalid-{int(time.time())}")
            os.replace(partial, quarantined)
            set_model_state(item["model"], "RETRY_PENDING", error="SIZE_OR_HASH_MISMATCH")
            log({"model": item["model"], "file": item["file"], "state": "RETRY_PENDING", "attempt": attempt, "bytes": current, "expected_bytes": item["bytes"], "sha256": actual, "expected_sha256": item["sha256"], "error": "SIZE_OR_HASH_MISMATCH", "quarantined": str(quarantined)})
            continue
        os.replace(partial, final)
        mark_manifest(item, "INTEGRITY_VERIFIED", actual_sha256=actual, actual_bytes=current)
        set_model_state(item["model"], "INTEGRITY_VERIFIED")
        log({"model": item["model"], "file": item["file"], "state": "INTEGRITY_VERIFIED", "bytes": current, "sha256": actual, "attempt": attempt})
        update_status(status, state="INTEGRITY_VERIFIED", downloaded_bytes=current, percentage=100, retry_number=attempt, last_error=None)
        return True
    set_model_state(item["model"], "FAILED_RETRY_EXHAUSTED", error="MAX_INTEGRITY_RETRIES")
    update_status(status, state="FAILED_RETRY_EXHAUSTED", last_error="MAX_INTEGRITY_RETRIES")
    log({"model": item["model"], "file": item["file"], "state": "FAILED_RETRY_EXHAUSTED", "attempts": MAX_INTEGRITY_RETRIES + 1})
    return False


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    worker_id = f"download-worker-{uuid.uuid4().hex[:12]}"
    acquire_lock(worker_id)
    manifest = ensure_frozen_queue(read_json(MANIFEST, {}))
    for verified_label in ("Whisper Large v3", "Audar Turbo Q4 + projector", "Audar Flash Q8 + projector", "FireRedVAD", "Audar Turbo Q8"):
        for frozen in manifest["frozen_queue"]:
            if frozen.get("model") == verified_label and frozen.get("state") not in {"FAILED_RETRY_EXHAUSTED", "BLOCKED_ACCESS", "BLOCKED_USER_ACTION"}:
                frozen["state"] = "INTEGRITY_VERIFIED"
    atomic_json(MANIFEST, manifest)
    queue = descriptor_queue(manifest)
    status: dict[str, Any] = {"worker_id": worker_id, "pid": os.getpid(), "started_at": now(), "last_heartbeat": now(), "current_model": None, "current_file": None, "downloaded_bytes": 0, "expected_bytes": 0, "percentage": 0, "retry_number": 0, "state": "STARTING", "last_error": None, "next_model": queue[0]["model"] if queue else None, "queue_summary": queue_summary(manifest)}
    atomic_json(STATUS, status)
    log({"event": "WORKER_STARTED", "worker_id": worker_id, "pid": os.getpid(), "queue_length": len(queue)})
    try:
        for index, item in enumerate(queue):
            status["next_model"] = queue[index + 1]["model"] if index + 1 < len(queue) else None
            update_status(status, state="QUEUED", current_model=item["model"], current_file=item["file"])
            download(item, status)
        latest = ensure_frozen_queue(read_json(MANIFEST, {}))
        summary = queue_summary(latest)
        if queue_complete_allowed([str(entry.get("state", "QUEUED")) for entry in latest["frozen_queue"]]):
            update_status(status, state="QUEUE_COMPLETE", current_model=None, current_file=None, next_model=None, queue_summary=summary)
            log({"event": "QUEUE_COMPLETE", "worker_id": worker_id, "queue_summary": summary})
        else:
            pending = next((entry.get("model") for entry in latest["frozen_queue"] if entry.get("state") not in TERMINAL_STATES), None)
            # Do not lie about completion. Keep a heartbeat-bearing worker alive
            # while unresolved metadata remains; the supervisor must not restart
            # it endlessly, and the UI can show exactly what is pending.
            update_status(status, state="WAITING_METADATA", current_model=None, current_file=None, next_model=pending, queue_summary=summary)
            log({"event": "QUEUE_PENDING", "worker_id": worker_id, "queue_summary": summary, "next_model": pending})
            while True:
                time.sleep(HEARTBEAT_SECONDS)
                update_status(status, state="WAITING_METADATA", current_model=None, current_file=None, next_model=pending, queue_summary=summary)
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
