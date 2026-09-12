"""Passive, evidence-backed certification probes for non-ASR stages.

The probes never download or activate a route.  They only inspect artifacts
already present on the configured model volume and, where the local runtime is
available, perform a load-only check.  A load check is intentionally not
promoted to capability certification.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from .schemas import CapabilityProvenance, ExecutionMode, Role, RoleBinding


MODEL_ROOT = Path("D:/models")
DOWNLOAD_MANIFEST = MODEL_ROOT / "_downloads" / "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_entry(candidate_id: str, manifest_path: Path = DOWNLOAD_MANIFEST) -> dict[str, Any]:
    try:
        body = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    for entry in body.get("queue", []):
        if entry.get("candidate_id") == candidate_id:
            return entry
    return {}


def _verify_manifest_files(entry: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    artifacts: list[dict[str, Any]] = []
    if not entry:
        return "NOT_INSTALLED", artifacts
    all_verified = True
    any_present = False
    for spec in entry.get("files", []):
        path = Path(str(spec.get("path", "")))
        item = {"path": str(path), "expected_bytes": spec.get("bytes"), "sha256": spec.get("sha256"), "present": path.is_file()}
        if path.is_file():
            any_present = True
            item["bytes"] = path.stat().st_size
            item["local_sha256"] = _sha256(path)
            if spec.get("bytes") is not None and item["bytes"] != spec["bytes"]:
                item["integrity"] = "SIZE_MISMATCH"
                all_verified = False
            elif spec.get("sha256") and item["local_sha256"].lower() != str(spec["sha256"]).lower():
                item["integrity"] = "HASH_MISMATCH"
                all_verified = False
            else:
                item["integrity"] = "VERIFIED" if spec.get("sha256") else "PRESENT_UNVERIFIED"
        else:
            item["integrity"] = "MISSING"
            all_verified = False
        artifacts.append(item)
    if all_verified and artifacts:
        return "INTEGRITY_VERIFIED", artifacts
    return ("ARTIFACT_PRESENT" if any_present else "NOT_INSTALLED"), artifacts


def _probe_livekit(model_root: Path, manifest_path: Path) -> dict[str, Any]:
    entry = _manifest_entry("LIVEKIT_TURN_DETECTOR_V1_MINI", manifest_path)
    artifact_state, artifacts = _verify_manifest_files(entry)
    result: dict[str, Any] = {
        "stage": "turn_detection", "model_id": "LIVEKIT_TURN_DETECTOR_V1_MINI",
        "provider": "livekit_turn_detector_local", "artifact_state": artifact_state,
        "runtime_state": "RUNTIME_PENDING", "capability_state": "CAPABILITY_PENDING",
        "revision": entry.get("revision"), "source": entry.get("source"), "artifacts": artifacts,
        "evidence": [], "reason": None,
    }
    path = model_root / "livekit" / "turn-detector-v1-mini" / "model_quantized.onnx"
    if artifact_state != "INTEGRITY_VERIFIED":
        result["reason"] = "ARTIFACT_NOT_INTEGRITY_VERIFIED"
        return result
    if importlib.util.find_spec("onnxruntime") is None:
        result["reason"] = "RUNTIME_BLOCKED_ONNX_RUNTIME_NOT_INSTALLED"
        return result
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]

        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        result["runtime_state"] = "RUNTIME_LOAD_VERIFIED"
        result["evidence"].append({
            "check": "onnx_load", "inputs": [{"name": item.name, "type": item.type, "shape": item.shape} for item in session.get_inputs()],
            "outputs": [{"name": item.name, "type": item.type, "shape": item.shape} for item in session.get_outputs()],
        })
        result["reason"] = "CAPABILITY_BLOCKED_TOKENIZER_OR_TURN_PROTOCOL_MISSING"
    except Exception as exc:  # load failure is evidence, not a fabricated capability result
        result["reason"] = f"RUNTIME_LOAD_FAILED:{type(exc).__name__}"
    return result


def _probe_missing_runtime(stage: str, model_id: str, provider: str, model_root: Path, manifest_path: Path, required_files: list[str]) -> dict[str, Any]:
    entry = _manifest_entry(model_id, manifest_path)
    artifact_state, artifacts = _verify_manifest_files(entry)
    missing = [str(model_root / "firered" / "FireRedVAD" / name) for name in required_files if not (model_root / "firered" / "FireRedVAD" / name).is_file()]
    return {
        "stage": stage, "model_id": model_id, "provider": provider,
        "artifact_state": artifact_state, "runtime_state": "RUNTIME_PENDING",
        "capability_state": "CAPABILITY_PENDING", "revision": entry.get("revision"),
        "source": entry.get("source"), "artifacts": artifacts, "missing_runtime_files": missing,
        "reason": "RUNTIME_BLOCKED_MISSING_CONFIG_OR_RUNTIME_MODULE" if missing else "RUNTIME_MODULE_NOT_CONFIGURED",
        "evidence": [],
    }


def _probe_diarization(model_root: Path, manifest_path: Path) -> dict[str, Any]:
    entry = _manifest_entry("AUDAR_DIARIZATION_V1", manifest_path)
    artifact_state, artifacts = _verify_manifest_files(entry)
    required = ["config.yaml", "load_diarizer.py"]
    missing = [str(model_root / "audar" / "Audar-Diarization-V1" / name) for name in required if not (model_root / "audar" / "Audar-Diarization-V1" / name).is_file()]
    return {
        "stage": "diarization", "model_id": "AUDAR_DIARIZATION_V1", "provider": "audar_diarization_local",
        "artifact_state": artifact_state, "runtime_state": "RUNTIME_PENDING", "capability_state": "CAPABILITY_PENDING",
        "revision": entry.get("revision"), "source": entry.get("source"), "artifacts": artifacts,
        "missing_runtime_files": missing, "reason": "RUNTIME_BLOCKED_MISSING_CONFIG_OR_LOADER" if missing else "RUNTIME_MODULE_NOT_CONFIGURED",
        "evidence": [],
    }


def stage_capability_report(model_root: Path = MODEL_ROOT, manifest_path: Path = DOWNLOAD_MANIFEST) -> dict[str, Any]:
    """Return the current honest status of the optional acoustic stages."""
    stages = [
        _probe_missing_runtime("vad", "FIRERED_VAD", "firered_vad_local", model_root, manifest_path, ["VAD/cmvn.ark", "Stream-VAD/cmvn.ark", "AED/cmvn.ark"]),
        _probe_livekit(model_root, manifest_path),
        _probe_diarization(model_root, manifest_path),
    ]
    return {"evidence_type": "REAL_LOCAL_ARTIFACT_PROBE", "auto_activation": False, "stages": stages}


def capability_bindings(model_root: Path = MODEL_ROOT, manifest_path: Path = DOWNLOAD_MANIFEST) -> list[RoleBinding]:
    """Expose optional stage bindings without making unavailable stages selectable."""
    report = stage_capability_report(model_root, manifest_path)
    role_for_stage = {"vad": Role.VAD, "turn_detection": Role.TURN_DETECTION, "diarization": Role.DIARIZATION}
    bindings: list[RoleBinding] = []
    for item in report["stages"]:
        stage = str(item["stage"])
        available = item["capability_state"] == "CAPABILITY_CERTIFIED"
        bindings.append(RoleBinding(
            id=f"{item['provider']}:{item['model_id']}:{stage}", provider=item["provider"], model_id=item["model_id"],
            revision_or_digest=f"{item.get('revision') or 'unknown'};{item.get('artifacts', [{}])[0].get('local_sha256', 'unknown') if item.get('artifacts') else 'unknown'}",
            role=role_for_stage[stage], prompt_version="stage-v1", schema_version="sta-v2",
            execution_mode=ExecutionMode.LOCAL, capability_provenance=CapabilityProvenance.VERIFIED_LOCAL if available else CapabilityProvenance.DISCOVERED,
            capabilities=[stage] if available else [], available=available, unavailable_reason=None if available else item.get("reason"), tool_mode="NONE",
            artifact_hashes=[str(artifact.get("local_sha256") or artifact.get("sha256")) for artifact in item.get("artifacts", []) if artifact.get("local_sha256") or artifact.get("sha256")],
        ))
    return bindings
