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
import ctypes
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
    "livekit/turn-detector": "LiveKit Turn Detector v1-mini",
    "CohereLabs/cohere-transcribe-arabic-07-2026": "Cohere Transcribe Arabic 07-2026",
    "unsloth/Qwen3.8-27B-GGUF": "Qwen3.8-27B Q6_K_L",
    "ibm-granite/granite-4.1-30b-GGUF": "Granite 4.1-30B Q6_K",
    "bartowski/badtheorylabs_BTL-4-GGUF": "BTL-4 Q6_K_L",
    "facebook/omniASR-LLM-7B": "Meta OmniASR-LLM-7B",
    "audarai/Audar-TTS-V1-Turbo": "Audar TTS V1 Turbo + NeuCodec",
    "Qwen/Qwen3-Omni-30B-A3B-Instruct": "Qwen3-Omni-30B-A3B-Instruct",
}


def hf_item(
    label: str,
    model: str,
    candidate_id: str,
    revision: str,
    file: str,
    path: Path,
    expected_bytes: int,
    expected_sha256: str,
    *,
    remote_oid: str | None = None,
    defer_model_terminal: bool = False,
) -> dict[str, Any]:
    return {
        "model": model,
        "label": label,
        "candidate_id": candidate_id,
        "revision": revision,
        "file": file,
        "url": f"https://huggingface.co/{model}/resolve/{revision}/{file}?download=true",
        "path": path,
        "bytes": expected_bytes,
        "sha256": expected_sha256,
        "remote_oid": remote_oid,
        "defer_model_terminal": defer_model_terminal,
    }


def resolved_static_items() -> list[dict[str, Any]]:
    """Pinned, read-only metadata resolved from the authoritative model APIs."""
    items = [
        hf_item(
            "LiveKit Turn Detector v1-mini", "livekit/turn-detector", "LIVEKIT_TURN_DETECTOR_V1_MINI",
            "fba34c38ad5d30a63ebb83a9e6bf271cf4c91d67", "model_quantized.onnx",
            ROOT / "livekit/turn-detector-v1-mini/model_quantized.onnx", 165035487,
            "4e685767c3643b0363c9f826a98325683f29e9c7d550162c8e8740ba33aa31aa",
            remote_oid="b7b8af319ab3915d259c63495d2f87232f2842b8",
        ),
        hf_item(
            "Qwen3.8-27B Q6_K_L", "unsloth/Qwen3.8-27B-GGUF", "QWEN38_27B_Q6_K_L",
            "4ca720788d1e01f1bff70c033e0d0028fd02e502", "Qwen3.8-27B-UD-Q6_K_L.gguf",
            ROOT / "qwen/Qwen3.8-27B-Q6_K_L/Qwen3.8-27B-UD-Q6_K_L.gguf", 24193919904,
            "121355b4c7422771da25adc74090e3c90138f77ce5c92d348687d47824ec80f4",
            remote_oid="1a0dae67b19bd7665c30f521abd75ca481ffbaaf",
        ),
        hf_item(
            "Granite 4.1-30B Q6_K", "ibm-granite/granite-4.1-30b-GGUF", "GRANITE_41_30B_Q6_K",
            "26a44ffe9923eea39af3ad811b56c9b0071e4347", "granite-4.1-30b-Q6_K.gguf",
            ROOT / "granite/granite-4.1-30b-Q6_K/granite-4.1-30b-Q6_K.gguf", 23684179168,
            "182f89335e9b891b799230f496af5bd1f1dfff97e79bab424776b2d65766b53b",
            remote_oid="13f2bc5f2a576df4c3a2a2cb0c5ae00c542199c3",
        ),
        hf_item(
            "BTL-4 Q6_K_L", "bartowski/badtheorylabs_BTL-4-GGUF", "BTL4_Q6_K_L",
            "799d011b498e3287f514eb463ea04d6624ec945f", "badtheorylabs_BTL-4-Q6_K_L.gguf",
            ROOT / "btl/BTL-4-Q6_K_L/badtheorylabs_BTL-4-Q6_K_L.gguf", 30299748480,
            "ff76ac2a57a9330e05d0ada00114bac5c2ebd412deead2771a2d0e49110de658",
            remote_oid="43904f991cc102cd52dbcf23dec574d14a6823e0",
        ),
        hf_item(
            "Meta OmniASR-LLM-7B", "facebook/omniASR-LLM-7B", "META_OMNIASR_LLM_7B",
            "4b0bada258b398cb7e6c5b3a6ed5448fb914385b", "omniASR-LLM-7B.pt",
            ROOT / "meta/omniASR-LLM-7B/omniASR-LLM-7B.pt", 31205087103,
            "2dd335727bf1cdb8910e824b456d77a6c2cad4d8994d48bef5ce5193cf846d72",
            remote_oid="e08e71881565ecdb398ca2ef178f24d9c3a9f15e",
            defer_model_terminal=True,
        ),
        hf_item(
            "Meta OmniASR-LLM-7B", "facebook/omniASR-LLM-7B", "META_OMNIASR_LLM_7B",
            "4b0bada258b398cb7e6c5b3a6ed5448fb914385b", "omniASR_tokenizer_v7.model",
            ROOT / "meta/omniASR-LLM-7B/omniASR_tokenizer_v7.model", 87607,
            "52f25c7e63b4cb0b27e7fedac9ac79b913a19a815656e5cafa99310ce911e165",
            remote_oid="8ba69714ac78d422ba8cd4b302ba7eb03e10bfc6",
            defer_model_terminal=True,
        ),
    ]
    qwen_shards = [
        ("model-00001-of-00015.safetensors", 4997899632, "f95d142b727fbd0698f0ed9478e222d4f29467df855e21862e46bd1401049065", "c5c3d8c6cfb49d054a0b0e879535506b9cf7d1fa"),
        ("model-00002-of-00015.safetensors", 4997754216, "320c1f31f7ddc4efd2501891590eca2c481ce4eca3db33d70ebbb637dae85764", "0fe6554f32d0fa0f82fb151931526c7b6b45484d"),
        ("model-00003-of-00015.safetensors", 4997754216, "306f06b05ef032f1fa51eb62e72c3432324e7a084fa0d15ed17ff856adffcf33", "a33370662f17348245bad8594fa5ec8a268ef5a4"),
        ("model-00004-of-00015.safetensors", 4997755648, "4cb551f433bfb4d83a5843e433e74688d71a96eeb1b62217b37d719026d559b5", "4ade23e6f6df55d5dda3872f22b74fcc4f192dd8"),
        ("model-00005-of-00015.safetensors", 4997755792, "8aec5e8cc0e0b179a81f690af31a1149238f4b1d18ac60e3f690020fdf7d915f", "90603a01a044c3281d24ccb0dc44cfc7bfd198b5"),
        ("model-00006-of-00015.safetensors", 4997755792, "8ff40a3d9e9c59a35a10257c1c5b216f472e6a102a4d6059bd31183eee03cb4c", "f4ee22a063afd42a98fee514738dd0672be00240"),
        ("model-00007-of-00015.safetensors", 4997755792, "f6d84cc1d47178850f9ba1fe9c01f45ee63d9a8b9975f92821ee2b4a0387860b", "f5ae7d4e8b0b50565d2fdbaeecc42763e9016013"),
        ("model-00008-of-00015.safetensors", 4997755792, "9f369ccdc9d2d2a55df794005b23cdbce44494a72e4a0069a150ae471cfea720", "da77eb0f52bf3491341a00144fb2c1a0878155d7"),
        ("model-00009-of-00015.safetensors", 4997755792, "980f754b21c4b20f36e02d184b792f5625f7c9d24b8a5c9da94287cf3cfde11b", "35fa26106a398b8c3579297a080ddb4605b291ff"),
        ("model-00010-of-00015.safetensors", 4997755792, "5c5a798376321d74df2eb3f235e1c8c68669f09b0c753b5698a16e681204d808", "e08dfb813f79e2d3a57e8dc66e01edf0806ab909"),
        ("model-00011-of-00015.safetensors", 4997755792, "6f7c051bd391c89279b43e7342ff4a243ad2ba2144f4aa62233fd2b02d72fce0", "ac01862171a7352821d3ddd663ac371243476b84"),
        ("model-00012-of-00015.safetensors", 4997755792, "a8b09a9367cd31ebf928e87b9eaf002492379d9d21d352b480854c2fbe6d9978", "494bef648dd806a5f60c9fb3dd6a2cdcb48768c6"),
        ("model-00013-of-00015.safetensors", 4999771808, "d9b7441c3a33e066d109cd6338e74ed680de9aa407d4df66eba5cb3c15c6d738", "4e8b39ac6e58928db12f9d81599075e93fb4e095"),
        ("model-00014-of-00015.safetensors", 4996618552, "73f09f187ff7b469a8937b39b8ac772e539e0d61311526c345558c5e6a6eb09a", "5c9c360dc2cc73f9123a4ec79ed26910e6836cfb"),
        ("model-00015-of-00015.safetensors", 553698794, "68880d566a50643807a4e73f5227c4f468bb31532925ed5fae78a51bdd39492a", "d5258d7260e6830b12e03a68aba14f2f8a3f2301"),
    ]
    for file, size, digest, oid in qwen_shards:
        items.append(hf_item(
            "Qwen3-Omni-30B-A3B-Instruct", "Qwen/Qwen3-Omni-30B-A3B-Instruct", "QWEN3_OMNI_30B_A3B",
            "26291f793822fb6be9555850f06dfe95f2d7e695", file,
            ROOT / "qwen/Qwen3-Omni-30B-A3B-Instruct" / file, size, digest,
            remote_oid=oid, defer_model_terminal=True,
        ))
    return items


BLOCKED_SPECS = {
    "Cohere Transcribe Arabic 07-2026": (
        "BLOCKED_ACCESS",
        "CohereLabs/cohere-transcribe-arabic-07-2026 is gated=auto; authentication and license acceptance are required.",
    ),
    "Audar TTS V1 Turbo + NeuCodec": (
        "BLOCKED_ACCESS",
        "The required companion neuphonic/neucodec repository is gated=auto; the TTS bundle is incomplete without that access.",
    ),
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


def register_manifest_item(item: dict[str, Any]) -> None:
    """Persist the pinned descriptor before any transfer begins."""
    body = read_json(MANIFEST, {})
    target_model = item["model"]
    target_revision = item["revision"]
    target_path = str(item["path"]).replace("\\", "/").lower()
    for entry in body.setdefault("queue", []):
        if entry.get("model") != target_model or entry.get("revision") != target_revision:
            continue
        for file_entry in entry.setdefault("files", []):
            if str(file_entry.get("path", "")).replace("\\", "/").lower() == target_path:
                return
        entry["files"].append({
            "name": item["file"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
            "remote_oid": item.get("remote_oid"),
            "path": str(item["path"]),
            "status": "PLANNED",
        })
        entry["total_bytes"] = sum(int(file.get("bytes", 0)) for file in entry["files"])
        atomic_json(MANIFEST, body)
        return
    body["queue"].append({
        "model": target_model,
        "candidate_id": item["candidate_id"],
        "revision": target_revision,
        "files": [{
            "name": item["file"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
            "remote_oid": item.get("remote_oid"),
            "path": str(item["path"]),
            "status": "PLANNED",
        }],
        "total_bytes": item["bytes"],
        "source": f"https://huggingface.co/{target_model}",
        "evidence": "authoritative Hugging Face model API at the pinned revision; exact artifact metadata",
    })
    atomic_json(MANIFEST, body)


def ensure_frozen_queue(body: dict[str, Any]) -> dict[str, Any]:
    items = body.setdefault("frozen_queue", [])
    existing = {entry.get("model") for entry in items if isinstance(entry, dict)}
    for model in FROZEN_QUEUE:
        if model not in existing:
            items.append({"model": model, "state": "QUEUED", "retry_count": 0})
    return body


def set_model_state(model: str, state: str, *, label: str | None = None, error: str | None = None) -> None:
    body = ensure_frozen_queue(read_json(MANIFEST, {}))
    label = label or MODEL_LABELS.get(model, model)
    for entry in body["frozen_queue"]:
        if entry.get("model") in {model, label}:
            entry["state"] = state
            if error:
                entry["last_error"] = error
            elif state not in {"RETRY_PENDING", "FAILED_RETRY_EXHAUSTED", "BLOCKED_ACCESS", "BLOCKED_USER_ACTION"}:
                entry.pop("last_error", None)
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


def apply_blocked_specs() -> None:
    body = ensure_frozen_queue(read_json(MANIFEST, {}))
    changed = False
    for entry in body["frozen_queue"]:
        label = entry.get("model")
        blocked = BLOCKED_SPECS.get(label)
        if not blocked or entry.get("state") in TERMINAL_STATES:
            continue
        state, reason = blocked
        entry["state"] = state
        entry["last_error"] = reason
        log({"model": label, "state": state, "error": reason})
        changed = True
    if changed:
        atomic_json(MANIFEST, body)


def manifest_file_status(manifest: dict[str, Any], item: dict[str, Any]) -> str | None:
    target = str(item["path"]).replace("\\", "/").lower()
    for entry in manifest.get("queue", []):
        for file_entry in entry.get("files", []):
            if str(file_entry.get("path", "")).replace("\\", "/").lower() == target:
                return file_entry.get("status")
    return None


def estimate_remaining_bytes(manifest: dict[str, Any], items: list[dict[str, Any]]) -> int:
    total = 0
    for item in items:
        if manifest_file_status(manifest, item) == "INTEGRITY_VERIFIED":
            continue
        partial = Path(str(item["path"]) + ".part")
        current = partial.stat().st_size if partial.is_file() else 0
        total += max(int(item["bytes"]) - min(current, int(item["bytes"])), 0)
    return total


def descriptor_queue(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only resolved, nonterminal frozen-queue work items."""
    frozen = {entry.get("model"): entry.get("state", "QUEUED") for entry in manifest.get("frozen_queue", [])}
    items: list[dict[str, Any]] = []

    # Existing manifest metadata is authoritative for the repaired Audar item.
    for entry in manifest.get("queue", []):
        model = entry.get("model", "")
        label = MODEL_LABELS.get(model)
        if label not in {"Audar Diarization V1"} or frozen.get(label) in TERMINAL_STATES:
            continue
        for file_entry in entry.get("files", []):
            if not file_entry.get("sha256"):
                continue
            items.append({
                "model": model,
                "label": label,
                "candidate_id": entry.get("candidate_id"),
                "revision": entry.get("revision"),
                "file": file_entry["name"],
                "url": f"https://huggingface.co/{model}/resolve/{entry['revision']}/{file_entry['name']}?download=true",
                "path": Path(file_entry["path"]),
                "bytes": file_entry["bytes"],
                "sha256": file_entry["sha256"],
                "remote_oid": file_entry.get("remote_oid"),
                "defer_model_terminal": False,
            })

    static_by_label: dict[str, list[dict[str, Any]]] = {}
    for item in resolved_static_items():
        static_by_label.setdefault(item["label"], []).append(item)
    for label in (
        "LiveKit Turn Detector v1-mini", "Qwen3.8-27B Q6_K_L", "Granite 4.1-30B Q6_K",
        "BTL-4 Q6_K_L", "Meta OmniASR-LLM-7B", "Qwen3-Omni-30B-A3B-Instruct",
    ):
        if frozen.get(label) in TERMINAL_STATES:
            continue
        for item in static_by_label.get(label, []):
            register_manifest_item(item)
            items.append(item)
    return items


def quarantine_partial(item: dict[str, Any], partial: Path, *, reason: str) -> Path:
    actual_bytes = partial.stat().st_size
    actual_sha256 = sha256(partial)
    quarantined = partial.with_name(partial.name + f".invalid-{int(time.time())}")
    os.replace(partial, quarantined)
    log({
        "model": item["model"], "label": item["label"], "file": item["file"],
        "state": "INVALID_PARTIAL_QUARANTINED", "reason": reason,
        "bytes": actual_bytes, "expected_bytes": item["bytes"],
        "sha256": actual_sha256, "expected_sha256": item["sha256"],
        "revision": item["revision"], "remote_oid": item.get("remote_oid"),
        "quarantined_path": str(quarantined),
    })
    return quarantined


def final_is_verified(item: dict[str, Any], final: Path) -> bool:
    if not final.is_file() or final.stat().st_size != item["bytes"]:
        return False
    return sha256(final).lower() == item["sha256"].lower()


def download(item: dict[str, Any], status: dict[str, Any]) -> bool:
    final = Path(item["path"])
    partial = Path(str(final) + ".part")
    final.parent.mkdir(parents=True, exist_ok=True)
    label = item["label"]
    defer_terminal = bool(item.get("defer_model_terminal"))
    register_manifest_item(item)
    set_model_state(item["model"], "RETRY_PENDING" if partial.exists() else "METADATA_RESOLVED", label=label)

    if partial.exists() and partial.stat().st_size > item["bytes"]:
        quarantine_partial(item, partial, reason="PARTIAL_LARGER_THAN_EXPECTED")
        set_model_state(item["model"], "RETRY_PENDING", label=label, error="PARTIAL_LARGER_THAN_EXPECTED")
    if final_is_verified(item, final):
        mark_manifest(item, "INTEGRITY_VERIFIED", actual_sha256=item["sha256"], actual_bytes=final.stat().st_size)
        set_model_state(item["model"], "DOWNLOADING" if defer_terminal else "INTEGRITY_VERIFIED", label=label)
        log({"model": item["model"], "label": label, "file": item["file"], "state": "INTEGRITY_VERIFIED", "bytes": final.stat().st_size, "sha256": item["sha256"], "note": "already verified"})
        return True

    for attempt in range(1, MAX_INTEGRITY_RETRIES + 2):
        if partial.exists() and partial.stat().st_size > item["bytes"]:
            quarantine_partial(item, partial, reason="PARTIAL_LARGER_THAN_EXPECTED_DURING_RETRY")
        set_model_state(item["model"], "DOWNLOADING", label=label)
        current = partial.stat().st_size if partial.exists() else 0
        status.update({"current_model": label, "current_source": item["model"], "current_file": item["file"], "expected_bytes": item["bytes"], "retry_number": attempt, "downloaded_bytes": current, "percentage": round(current * 100 / item["bytes"], 2), "state": "DOWNLOADING", "last_error": None})
        atomic_json(STATUS, {**status, "last_heartbeat": now()})
        command = ["curl.exe", "--fail", "--location", "--retry", "5", "--retry-all-errors", "--connect-timeout", "30", "--continue-at", "-", "--output", str(partial), item["url"]]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        while process.poll() is None:
            current = partial.stat().st_size if partial.exists() else 0
            update_status(status, state="DOWNLOADING", downloaded_bytes=current, expected_bytes=item["bytes"], percentage=round(current * 100 / item["bytes"], 2), retry_number=attempt)
            time.sleep(HEARTBEAT_SECONDS)
        current = partial.stat().st_size if partial.exists() else 0
        if process.returncode != 0:
            set_model_state(item["model"], "RETRY_PENDING", label=label, error=f"curl_exit_{process.returncode}")
            log({"model": item["model"], "label": label, "file": item["file"], "state": "RETRY_PENDING", "attempt": attempt, "bytes": current, "expected_bytes": item["bytes"], "error": f"curl_exit_{process.returncode}"})
            continue
        actual = sha256(partial)
        if current != item["bytes"] or actual.lower() != item["sha256"].lower():
            quarantine_partial(item, partial, reason="SIZE_OR_HASH_MISMATCH")
            set_model_state(item["model"], "RETRY_PENDING", label=label, error="SIZE_OR_HASH_MISMATCH")
            log({"model": item["model"], "label": label, "file": item["file"], "state": "RETRY_PENDING", "attempt": attempt, "bytes": current, "expected_bytes": item["bytes"], "sha256": actual, "expected_sha256": item["sha256"], "error": "SIZE_OR_HASH_MISMATCH"})
            continue
        os.replace(partial, final)
        mark_manifest(item, "INTEGRITY_VERIFIED", actual_sha256=actual, actual_bytes=current)
        set_model_state(item["model"], "DOWNLOADING" if defer_terminal else "INTEGRITY_VERIFIED", label=label)
        log({"model": item["model"], "label": label, "file": item["file"], "state": "INTEGRITY_VERIFIED", "bytes": current, "sha256": actual, "attempt": attempt})
        update_status(status, state="INTEGRITY_VERIFIED", downloaded_bytes=current, percentage=100, retry_number=attempt, last_error=None)
        return True
    set_model_state(item["model"], "FAILED_RETRY_EXHAUSTED", label=label, error="MAX_INTEGRITY_RETRIES")
    update_status(status, state="FAILED_RETRY_EXHAUSTED", last_error="MAX_INTEGRITY_RETRIES")
    log({"model": item["model"], "label": label, "file": item["file"], "state": "FAILED_RETRY_EXHAUSTED", "attempts": MAX_INTEGRITY_RETRIES + 1})
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
    apply_blocked_specs()
    manifest = ensure_frozen_queue(read_json(MANIFEST, {}))
    queue = descriptor_queue(manifest)
    manifest = ensure_frozen_queue(read_json(MANIFEST, {}))
    queue = descriptor_queue(manifest)
    status: dict[str, Any] = {"worker_id": worker_id, "pid": os.getpid(), "started_at": now(), "last_heartbeat": now(), "current_model": None, "current_file": None, "downloaded_bytes": 0, "expected_bytes": 0, "percentage": 0, "retry_number": 0, "state": "STARTING", "last_error": None, "next_model": queue[0]["label"] if queue else None, "queue_summary": queue_summary(manifest), "remaining_download_bytes": estimate_remaining_bytes(manifest, queue)}
    atomic_json(STATUS, status)
    log({"event": "WORKER_STARTED", "worker_id": worker_id, "pid": os.getpid(), "queue_length": len(queue)})
    try:
        groups: list[tuple[str, list[dict[str, Any]]]] = []
        for item in queue:
            if groups and groups[-1][0] == item["label"]:
                groups[-1][1].append(item)
            else:
                groups.append((item["label"], [item]))
        for group_index, (label, group) in enumerate(groups):
            next_model = groups[group_index + 1][0] if group_index + 1 < len(groups) else None
            set_model_state(group[0]["model"], "METADATA_RESOLVED", label=label)
            group_ok = True
            for item in group:
                status["next_model"] = next_model
                update_status(status, state="QUEUED", current_model=label, current_source=item["model"], current_file=item["file"], queue_summary=queue_summary(ensure_frozen_queue(read_json(MANIFEST, {}))))
                if not download(item, status):
                    group_ok = False
                    break
            if group_ok:
                set_model_state(group[0]["model"], "INTEGRITY_VERIFIED", label=label)
            status["remaining_download_bytes"] = estimate_remaining_bytes(ensure_frozen_queue(read_json(MANIFEST, {})), queue)
        latest = ensure_frozen_queue(read_json(MANIFEST, {}))
        summary = queue_summary(latest)
        if queue_complete_allowed([str(entry.get("state", "QUEUED")) for entry in latest["frozen_queue"]]):
            update_status(status, state="QUEUE_COMPLETE", current_model=None, current_file=None, next_model=None, queue_summary=summary, remaining_download_bytes=0)
            log({"event": "QUEUE_COMPLETE", "worker_id": worker_id, "queue_summary": summary})
        else:
            pending = next((entry.get("model") for entry in latest["frozen_queue"] if entry.get("state") not in TERMINAL_STATES), None)
            # This is a safety state only. A descriptor missing from the resolved
            # queue must never be mistaken for successful completion.
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
