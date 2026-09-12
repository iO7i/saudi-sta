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
import re
import signal
import sys
import time
import uuid
import ctypes
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(os.getenv("SAUDI_STA_MODEL_ROOT", r"D:\models"))
STATE = ROOT / "_downloads"
MANIFEST = STATE / "manifest.json"
STATUS = STATE / "worker-status.json"
LOG = STATE / "download-log.jsonl"
LOCK = STATE / "worker.lock"
HEARTBEAT_SECONDS = 5
STALE_SECONDS = 90
MAX_INTEGRITY_RETRIES = 2
DOWNLOAD_CHUNK_BYTES = 4 * 1024 * 1024
ARTIFACT_LOCK_SUFFIX = ".lock"
TERMINAL_STATES = {"INTEGRITY_VERIFIED", "BLOCKED_ACCESS", "BLOCKED_USER_ACTION", "FAILED_RETRY_EXHAUSTED"}
_STOP_REQUESTED = False
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


class DownloadError(RuntimeError):
    """Base class for errors that are safe to classify and retry."""


class DownloadProtocolError(DownloadError):
    """The remote response cannot safely be written to the artifact."""


class ResumeNotHonored(DownloadProtocolError):
    """A ranged request returned a non-ranged response."""


class ArtifactIdentityChanged(DownloadProtocolError):
    """The remote artifact identity changed between attempts."""


class OversizeTransfer(DownloadProtocolError):
    """The response attempted to exceed the manifest byte ceiling."""


class TransientDownloadError(DownloadError):
    """A connection or server failure that may be retried safely."""


class DownloadStopped(DownloadError):
    """The worker received an explicit stop request."""


def request_stop(signum: int | None = None, frame: Any | None = None) -> None:
    """Request a cooperative stop without mutating any artifact."""

    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def stop_requested() -> bool:
    return _STOP_REQUESTED


def parse_content_range(value: str | None) -> tuple[int, int, int]:
    if not value:
        raise DownloadProtocolError("MISSING_CONTENT_RANGE")
    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", value.strip(), flags=re.IGNORECASE)
    if not match:
        raise DownloadProtocolError(f"INVALID_CONTENT_RANGE:{value}")
    start, end, total = (int(part) for part in match.groups())
    if end < start or total <= end:
        raise DownloadProtocolError(f"INVALID_CONTENT_RANGE:{value}")
    return start, end, total


def response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    return int(status or 0)


def response_header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get(name)
    return str(value) if value is not None else None


def validate_response(
    response: Any,
    *,
    offset: int,
    expected_bytes: int,
    previous_identity: dict[str, str | None] | None = None,
) -> dict[str, str | None]:
    """Validate the final response before a single byte is written."""

    status = response_status(response)
    etag = response_header(response, "ETag")
    last_modified = response_header(response, "Last-Modified")
    content_encoding = response_header(response, "Content-Encoding")
    if content_encoding and content_encoding.lower() not in {"identity", "none"}:
        raise DownloadProtocolError(f"CONTENT_ENCODING_NOT_IDENTITY:{content_encoding}")

    previous_identity = previous_identity or {}
    previous_etag = previous_identity.get("etag")
    previous_last_modified = previous_identity.get("last_modified")
    if previous_etag and etag and previous_etag != etag:
        raise ArtifactIdentityChanged(f"ETAG_CHANGED:{previous_etag}->{etag}")
    if previous_last_modified and last_modified and previous_last_modified != last_modified:
        raise ArtifactIdentityChanged("LAST_MODIFIED_CHANGED")
    if previous_etag and not etag and not last_modified:
        raise ArtifactIdentityChanged("PREVIOUS_IDENTITY_NOT_RETURNED")

    content_length = response_header(response, "Content-Length")
    length = int(content_length) if content_length and content_length.isdigit() else None
    if offset > 0:
        if status == 200:
            raise ResumeNotHonored("RANGE_REQUEST_RETURNED_HTTP_200")
        if status != 206:
            raise DownloadProtocolError(f"RANGE_REQUEST_STATUS_{status}")
        start, end, total = parse_content_range(response_header(response, "Content-Range"))
        if start != offset:
            raise DownloadProtocolError(f"CONTENT_RANGE_START_{start}_EXPECTED_{offset}")
        if total != expected_bytes:
            raise DownloadProtocolError(f"CONTENT_RANGE_TOTAL_{total}_EXPECTED_{expected_bytes}")
        expected_response_bytes = expected_bytes - offset
        if length is not None and length != expected_response_bytes:
            raise DownloadProtocolError(f"CONTENT_LENGTH_{length}_EXPECTED_{expected_response_bytes}")
    else:
        if status == 206:
            start, end, total = parse_content_range(response_header(response, "Content-Range"))
            if start != 0 or total != expected_bytes:
                raise DownloadProtocolError("INITIAL_CONTENT_RANGE_MISMATCH")
            if length is not None and length != expected_bytes:
                raise DownloadProtocolError(f"CONTENT_LENGTH_{length}_EXPECTED_{expected_bytes}")
        elif status == 200:
            if length is not None and length != expected_bytes:
                raise DownloadProtocolError(f"CONTENT_LENGTH_{length}_EXPECTED_{expected_bytes}")
        else:
            raise DownloadProtocolError(f"INITIAL_REQUEST_STATUS_{status}")

    return {
        "etag": etag,
        "last_modified": last_modified,
        "resolved_url": str(getattr(response, "url", "") or ""),
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
                    # sha256 is authoritative expected metadata. Never
                    # replace it with an observed digest after a mismatch.
                    file_entry["observed_sha256"] = actual_sha256
                if actual_bytes is not None:
                    file_entry["downloaded_bytes"] = actual_bytes
                changed = True
    if not changed:
        body.setdefault("verified_artifacts", []).append({"model": item["model"], "file": item["file"], "path": str(item["path"]), "bytes": actual_bytes, "sha256": actual_sha256, "state": state})
    atomic_json(MANIFEST, body)


def manifest_file_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    body = read_json(MANIFEST, {})
    target = str(item["path"]).replace("\\", "/").lower()
    for entry in body.get("queue", []):
        for file_entry in entry.get("files", []):
            if str(file_entry.get("path", "")).replace("\\", "/").lower() == target or file_entry.get("name") == item["file"]:
                return file_entry
    return None


def artifact_identity(item: dict[str, Any]) -> dict[str, str | None]:
    entry = manifest_file_entry(item) or {}
    return {
        "etag": entry.get("etag"),
        "last_modified": entry.get("last_modified"),
        "resolved_url": entry.get("resolved_url"),
    }


def record_artifact_identity(item: dict[str, Any], identity: dict[str, str | None]) -> None:
    body = read_json(MANIFEST, {})
    target = str(item["path"]).replace("\\", "/").lower()
    changed = False
    for entry in body.get("queue", []):
        for file_entry in entry.get("files", []):
            if str(file_entry.get("path", "")).replace("\\", "/").lower() != target and file_entry.get("name") != item["file"]:
                continue
            file_entry["source_url"] = item["url"]
            for key in ("etag", "last_modified", "resolved_url"):
                if identity.get(key):
                    file_entry[key] = identity[key]
            changed = True
    if changed:
        atomic_json(MANIFEST, body)


def clear_artifact_identity(item: dict[str, Any]) -> None:
    body = read_json(MANIFEST, {})
    target = str(item["path"]).replace("\\", "/").lower()
    changed = False
    for entry in body.get("queue", []):
        for file_entry in entry.get("files", []):
            if str(file_entry.get("path", "")).replace("\\", "/").lower() != target and file_entry.get("name") != item["file"]:
                continue
            for key in ("etag", "last_modified", "resolved_url"):
                file_entry.pop(key, None)
            changed = True
    if changed:
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
    except (OSError, ValueError):
        return False


def acquire_lock(worker_id: str):
    existing = read_json(LOCK, {})
    if pid_alive(existing.get("pid")):
        raise SystemExit(f"worker already active: {existing}")
    # Exclusive creation closes the check-then-write race when two launchers
    # start at the same time. A stale lock is recoverable only after its PID is
    # demonstrably dead.
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing = read_json(LOCK, {})
        if pid_alive(existing.get("pid")):
            raise SystemExit(f"worker already active: {existing}")
        LOCK.unlink(missing_ok=True)
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    handle = os.fdopen(fd, "w", encoding="utf-8")
    json.dump({"worker_id": worker_id, "pid": os.getpid(), "started_at": now()}, handle)
    handle.flush()
    return handle


def acquire_artifact_lock(partial: Path, worker_id: str):
    lock_path = Path(str(partial) + ARTIFACT_LOCK_SUFFIX)
    existing = read_json(lock_path, {})
    if pid_alive(existing.get("pid")):
        raise DownloadError(f"ARTIFACT_ALREADY_OWNED:{partial}")
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing = read_json(lock_path, {})
        if pid_alive(existing.get("pid")):
            raise DownloadError(f"ARTIFACT_ALREADY_OWNED:{partial}")
        lock_path.unlink(missing_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    handle = os.fdopen(fd, "w", encoding="utf-8")
    json.dump({"worker_id": worker_id, "pid": os.getpid(), "started_at": now()}, handle)
    handle.flush()
    return lock_path, handle


def release_artifact_lock(lock: tuple[Path, Any] | None) -> None:
    if not lock:
        return
    lock_path, handle = lock
    try:
        handle.close()
    finally:
        lock_path.unlink(missing_ok=True)


def release_lock(handle: Any | None = None) -> None:
    if handle is not None:
        handle.close()
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


def quarantine_partial(item: dict[str, Any], partial: Path, *, reason: str, compute_hash: bool = True) -> Path:
    actual_bytes = partial.stat().st_size
    actual_sha256 = sha256(partial) if compute_hash else None
    quarantined = partial.with_name(partial.name + f".invalid-{int(time.time())}-{uuid.uuid4().hex[:8]}")
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


def open_download_response(
    item: dict[str, Any],
    *,
    offset: int,
    previous_identity: dict[str, str | None] | None = None,
    opener: Callable[..., Any] | None = None,
) -> tuple[Any, dict[str, str | None]]:
    headers = {"Accept-Encoding": "identity"}
    if offset > 0:
        headers["Range"] = f"bytes={offset}-"
        identity = previous_identity or {}
        if identity.get("etag"):
            headers["If-Range"] = str(identity["etag"])
        elif identity.get("last_modified"):
            headers["If-Range"] = str(identity["last_modified"])
    request = urllib.request.Request(item["url"], headers=headers, method="GET")
    opener = opener or urllib.request.urlopen
    try:
        response = opener(request, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code in {408, 425, 429} or exc.code >= 500:
            raise TransientDownloadError(f"HTTP_{exc.code}") from exc
        raise DownloadProtocolError(f"HTTP_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise TransientDownloadError(str(exc)) from exc
    try:
        identity = validate_response(
            response,
            offset=offset,
            expected_bytes=int(item["bytes"]),
            previous_identity=previous_identity,
        )
    except Exception:
        close = getattr(response, "close", None)
        if close:
            close()
        raise
    return response, identity


def stream_response(
    response: Any,
    destination: Path,
    *,
    offset: int,
    expected_bytes: int,
    status: dict[str, Any] | None = None,
) -> int:
    current = offset
    destination.parent.mkdir(parents=True, exist_ok=True)
    mode = "ab" if offset else "wb"
    last_status_at = 0.0
    try:
        with destination.open(mode) as handle:
            while True:
                if stop_requested():
                    raise DownloadStopped("STOP_REQUESTED")
                try:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                    raise TransientDownloadError(str(exc)) from exc
                if not chunk:
                    break
                # Check before writing. A remote body can never make the
                # partial exceed the authoritative manifest length.
                if current + len(chunk) > expected_bytes:
                    raise OversizeTransfer(
                        f"WRITE_WOULD_EXCEED_EXPECTED:{current}+{len(chunk)}>{expected_bytes}"
                    )
                handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
                current += len(chunk)
                actual_disk = destination.stat().st_size
                if actual_disk != current:
                    raise DownloadError(f"DURABLE_SIZE_DISAGREEMENT:{actual_disk}!={current}")
                if status is not None and time.monotonic() - last_status_at >= HEARTBEAT_SECONDS:
                    update_status(
                        status,
                        downloaded_bytes=current,
                        actual_disk_bytes=actual_disk,
                        resume_offset=current,
                        tracked_disk_disagreement=False,
                    )
                    last_status_at = time.monotonic()
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
    return current


def transfer_once(
    item: dict[str, Any],
    destination: Path,
    *,
    offset: int,
    previous_identity: dict[str, str | None] | None = None,
    opener: Callable[..., Any] | None = None,
    status: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str | None]]:
    response, identity = open_download_response(
        item,
        offset=offset,
        previous_identity=previous_identity,
        opener=opener,
    )
    record_artifact_identity(item, identity)
    current = stream_response(
        response,
        destination,
        offset=offset,
        expected_bytes=int(item["bytes"]),
        status=status,
    )
    return current, identity


def download(item: dict[str, Any], status: dict[str, Any], *, opener: Callable[..., Any] | None = None) -> bool:
    final = Path(item["path"])
    partial = Path(str(final) + ".part")
    final.parent.mkdir(parents=True, exist_ok=True)
    label = item["label"]
    defer_terminal = bool(item.get("defer_model_terminal"))
    register_manifest_item(item)
    set_model_state(item["model"], "RETRY_PENDING" if partial.exists() else "METADATA_RESOLVED", label=label)
    lock = acquire_artifact_lock(partial, str(status.get("worker_id", os.getpid())))
    try:
        if final_is_verified(item, final):
            mark_manifest(item, "INTEGRITY_VERIFIED", actual_sha256=item["sha256"], actual_bytes=final.stat().st_size)
            set_model_state(item["model"], "DOWNLOADING" if defer_terminal else "INTEGRITY_VERIFIED", label=label)
            log({"model": item["model"], "label": label, "file": item["file"], "state": "INTEGRITY_VERIFIED", "bytes": final.stat().st_size, "sha256": item["sha256"], "note": "already verified"})
            return True

        if partial.exists() and partial.stat().st_size > item["bytes"]:
            quarantine_partial(item, partial, reason="PARTIAL_LARGER_THAN_EXPECTED")
            set_model_state(item["model"], "RETRY_PENDING", label=label, error="PARTIAL_LARGER_THAN_EXPECTED")

        for attempt in range(1, MAX_INTEGRITY_RETRIES + 2):
            if stop_requested():
                raise DownloadStopped("STOP_REQUESTED")
            set_model_state(item["model"], "DOWNLOADING", label=label)
            current = partial.stat().st_size if partial.exists() else 0
            identity = artifact_identity(item)
            status.update({
                "current_model": label, "current_source": item["model"], "current_file": item["file"],
                "expected_bytes": item["bytes"], "retry_number": attempt, "downloaded_bytes": current,
                "actual_disk_bytes": current, "resume_offset": current,
                "tracked_disk_disagreement": False,
                "percentage": round(current * 100 / item["bytes"], 2), "state": "DOWNLOADING", "last_error": None,
                "source_etag": identity.get("etag"), "source_last_modified": identity.get("last_modified"),
            })
            atomic_json(STATUS, {**status, "last_heartbeat": now()})
            try:
                current, identity = transfer_once(
                    item, partial, offset=current, previous_identity=identity, opener=opener, status=status,
                )
            except ResumeNotHonored as exc:
                # Never append an HTTP 200 body to an existing partial. Try a
                # separate zero-based temporary file instead.
                log({"model": item["model"], "label": label, "file": item["file"], "state": "RANGE_NOT_HONORED", "attempt": attempt, "resume_offset": current, "error": str(exc)})
                restart = partial.with_name(partial.name + f".restart-{uuid.uuid4().hex[:10]}")
                try:
                    fresh_current, identity = transfer_once(item, restart, offset=0, previous_identity={}, opener=opener, status=status)
                    current = fresh_current
                    if current != item["bytes"]:
                        raise TransientDownloadError(f"SHORT_FRESH_TRANSFER:{current}")
                    actual = sha256(restart)
                    if actual.lower() != item["sha256"].lower():
                        raise DownloadProtocolError("FRESH_TRANSFER_HASH_MISMATCH")
                    if partial.exists() and partial.stat().st_size:
                        quarantine_partial(item, partial, reason="REPLACED_AFTER_HTTP_200_RESUME", compute_hash=False)
                    os.replace(restart, partial)
                except DownloadStopped:
                    raise
                except Exception:
                    if restart.exists():
                        quarantine_partial(item, restart, reason="FAILED_FRESH_RESTART", compute_hash=False)
                    raise
            except ArtifactIdentityChanged as exc:
                current = partial.stat().st_size if partial.exists() else 0
                log({"model": item["model"], "label": label, "file": item["file"], "state": "REMOTE_IDENTITY_CHANGED", "attempt": attempt, "bytes": current, "error": str(exc)})
                if partial.exists() and partial.stat().st_size:
                    quarantine_partial(item, partial, reason="REMOTE_IDENTITY_CHANGED", compute_hash=False)
                clear_artifact_identity(item)
                continue
            except DownloadStopped:
                raise
            except OversizeTransfer as exc:
                current = partial.stat().st_size if partial.exists() else 0
                if partial.exists() and partial.stat().st_size:
                    quarantine_partial(item, partial, reason="REMOTE_BODY_EXCEEDS_EXPECTED", compute_hash=False)
                set_model_state(item["model"], "RETRY_PENDING", label=label, error="REMOTE_BODY_EXCEEDS_EXPECTED")
                log({"model": item["model"], "label": label, "file": item["file"], "state": "RETRY_PENDING", "attempt": attempt, "bytes": current, "expected_bytes": item["bytes"], "error": str(exc)})
                continue
            except (TransientDownloadError, DownloadProtocolError, DownloadError) as exc:
                current = partial.stat().st_size if partial.exists() else 0
                set_model_state(item["model"], "RETRY_PENDING", label=label, error=str(exc))
                log({"model": item["model"], "label": label, "file": item["file"], "state": "RETRY_PENDING", "attempt": attempt, "bytes": current, "expected_bytes": item["bytes"], "error": str(exc)})
                continue

            current = partial.stat().st_size if partial.exists() else 0
            if current != item["bytes"]:
                set_model_state(item["model"], "RETRY_PENDING", label=label, error="SHORT_TRANSFER")
                log({"model": item["model"], "label": label, "file": item["file"], "state": "RETRY_PENDING", "attempt": attempt, "bytes": current, "expected_bytes": item["bytes"], "error": "SHORT_TRANSFER"})
                continue
            actual = sha256(partial)
            if actual.lower() != item["sha256"].lower():
                quarantine_partial(item, partial, reason="SIZE_OR_HASH_MISMATCH")
                set_model_state(item["model"], "RETRY_PENDING", label=label, error="SIZE_OR_HASH_MISMATCH")
                log({"model": item["model"], "label": label, "file": item["file"], "state": "RETRY_PENDING", "attempt": attempt, "bytes": current, "expected_bytes": item["bytes"], "sha256": actual, "expected_sha256": item["sha256"], "error": "SIZE_OR_HASH_MISMATCH"})
                continue
            os.replace(partial, final)
            mark_manifest(item, "INTEGRITY_VERIFIED", actual_sha256=actual, actual_bytes=current)
            set_model_state(item["model"], "DOWNLOADING" if defer_terminal else "INTEGRITY_VERIFIED", label=label)
            log({"model": item["model"], "label": label, "file": item["file"], "state": "INTEGRITY_VERIFIED", "bytes": current, "sha256": actual, "attempt": attempt})
            update_status(status, state="INTEGRITY_VERIFIED", downloaded_bytes=current, actual_disk_bytes=current, resume_offset=current, percentage=100, retry_number=attempt, last_error=None)
            return True
        set_model_state(item["model"], "FAILED_RETRY_EXHAUSTED", label=label, error="MAX_INTEGRITY_RETRIES")
        update_status(status, state="FAILED_RETRY_EXHAUSTED", last_error="MAX_INTEGRITY_RETRIES")
        log({"model": item["model"], "label": label, "file": item["file"], "state": "FAILED_RETRY_EXHAUSTED", "attempts": MAX_INTEGRITY_RETRIES + 1})
        return False
    finally:
        release_artifact_lock(lock)


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    worker_id = f"download-worker-{uuid.uuid4().hex[:12]}"
    lock_handle = acquire_lock(worker_id)
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
    status: dict[str, Any] = {"worker_id": worker_id, "pid": os.getpid(), "started_at": now(), "last_heartbeat": now(), "current_model": None, "current_source": None, "current_file": None, "current_path": None, "downloaded_bytes": 0, "actual_disk_bytes": 0, "resume_offset": 0, "tracked_disk_disagreement": False, "expected_bytes": 0, "percentage": 0, "retry_number": 0, "state": "STARTING", "last_error": None, "next_model": queue[0]["label"] if queue else None, "queue_summary": queue_summary(manifest), "remaining_download_bytes": estimate_remaining_bytes(manifest, queue), "stop_requested": False}
    atomic_json(STATUS, status)
    log({"event": "WORKER_STARTED", "worker_id": worker_id, "pid": os.getpid(), "queue_length": len(queue)})
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, request_stop)
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
                update_status(status, state="QUEUED", current_model=label, current_source=item["model"], current_file=item["file"], current_path=str(item["path"]), queue_summary=queue_summary(ensure_frozen_queue(read_json(MANIFEST, {}))))
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
                if stop_requested():
                    raise DownloadStopped("STOP_REQUESTED")
                time.sleep(HEARTBEAT_SECONDS)
                update_status(status, state="WAITING_METADATA", current_model=None, current_file=None, next_model=pending, queue_summary=summary)
        return 0
    except DownloadStopped as exc:
        update_status(status, state="STOPPED", stop_requested=True, last_error=str(exc), actual_disk_bytes=status.get("actual_disk_bytes", 0), resume_offset=status.get("actual_disk_bytes", 0))
        log({"event": "WORKER_STOPPED", "worker_id": worker_id, "pid": os.getpid(), "reason": str(exc), "current_model": status.get("current_model"), "current_path": status.get("current_path"), "durable_local_bytes": status.get("actual_disk_bytes", 0), "retry_number": status.get("retry_number", 0)})
        return 0
    finally:
        release_lock(lock_handle)


if __name__ == "__main__":
    raise SystemExit(main())
