"""Planned local model laboratory registry and explicit-root artifact scanner.

The scanner is deliberately passive: it never downloads, loads, executes, or
activates a model.  Runtime and capability certification remain separate
operator actions.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ARTIFACT_STATES = (
    "NOT_INSTALLED",
    "ARTIFACT_PRESENT",
    "INTEGRITY_VERIFIED",
    "RUNTIME_LOAD_VERIFIED",
    "CAPABILITY_CERTIFIED",
)


def _artifact(path: str, *, bytes_: int | None = None, sha256: str | None = None) -> dict[str, Any]:
    return {"path": path, "expected_bytes": bytes_, "sha256": sha256}


# This is the frozen laboratory plan.  Unknown legal permissions stay UNKNOWN.
PLANNED_MODELS: list[dict[str, Any]] = [
    {
        "id": "AUDAR_TURBO_Q4_LOCAL_BRIDGE", "family": "Audar-ASR-V1-Turbo", "stage": ["transcribe"],
        "source_repository": "audarai/Audar-ASR-V1-Turbo", "revision": "371428bea487c7aec82b27dc21f8d4324002e98e",
        "precision": "Q4_K_M", "runtime": "llama.cpp mtmd", "local_or_hosted": "LOCAL",
        "license_id": "audarai-community-license-v1.0", "license_source": "https://www.audarai.com/license/audarai-community-license-v1.0/",
        "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN",
        "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0,
        "artifact_root": "audar/Audar-ASR-V1-Turbo", "artifacts": [
            _artifact("Audar-ASR-V1-Turbo-Q4_K_M.gguf", bytes_=1282434912, sha256="c55e3c28225ef6e9b56906a6463af62d34ed417803c45f3b7b20f463af2e8cf4"),
            _artifact("mmproj-Audar-ASR-V1-Turbo.gguf", bytes_=641773856, sha256="190459e806938175711779847eb62ea609cd78b8d2ec06fb96a94d69ab37a9be"),
        ], "verified_capabilities": ["transcribe"], "unverified_claims": ["Gulf dialects", "code-switching"],
        "runtime_certified": True, "capability_certified": True, "evidence_notes": "Q4 local bridge; NOT_REFERENCE_PRECISION; no leaderboard parity claim.",
    },
    {
        "id": "AUDAR_TURBO_Q8_LOCAL", "family": "Audar-ASR-V1-Turbo", "stage": ["transcribe"],
        "source_repository": "audarai/Audar-ASR-V1-Turbo", "revision": "371428bea487c7aec82b27dc21f8d4324002e98e",
        "precision": "Q8_0", "runtime": "llama.cpp mtmd", "local_or_hosted": "LOCAL",
        "license_id": "audarai-community-license-v1.0", "license_source": "https://www.audarai.com/license/audarai-community-license-v1.0/",
        "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0,
        "artifact_root": "audar/Audar-ASR-V1-Turbo", "decoder_filename": "Audar-ASR-V1-Turbo-Q8_0.gguf", "artifacts": [
            _artifact("Audar-ASR-V1-Turbo-Q8_0.gguf", bytes_=2165034848, sha256="0a91ab40f6a30db06c4186e2f621f504f4625ba6058e639cc09f1cbefded10d2"),
            _artifact("mmproj-Audar-ASR-V1-Turbo.gguf", bytes_=641773856, sha256="190459e806938175711779847eb62ea609cd78b8d2ec06fb96a94d69ab37a9be"),
        ], "verified_capabilities": ["transcribe"], "unverified_claims": ["Arabic transcription"],
        "runtime_certified": True, "capability_certified": True, "evidence_notes": "Distinct Q8 candidate; shares the verified BF16 projector. Runtime-certified against the same local audio in Slice 02.",
    },
    {
        "id": "AUDAR_FLASH_Q8_LOCAL", "family": "Audar-ASR-V1-Flash", "stage": ["transcribe"],
        "source_repository": "audarai/Audar-ASR-V1-Flash", "revision": "54274d39245beba38f30048128e231d4176bd91d", "precision": "Q8_0", "runtime": "llama.cpp mtmd", "local_or_hosted": "LOCAL",
        "license_id": "audarai-open-license-v1.0", "license_source": "https://www.audarai.com/license/audarai-open-license-v1.0/",
        "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0,
        "artifact_root": "audar/Audar-ASR-V1-Flash", "decoder_filename": "Audar-ASR-V1-Flash-Q8_0.gguf", "artifacts": [
            _artifact("Audar-ASR-V1-Flash-Q8_0.gguf", bytes_=639442784, sha256="1b01c707fcf162ef8e844a89f0833bd0d005933342e0c37fa8da164497a9fb38"),
            _artifact("mmproj-Audar-ASR-V1-Flash.gguf", bytes_=378575424, sha256="73f06fc82a009b4a9d6c825782a3676cb553402b3a5ecc27ae77a92caa6b7fa9"),
        ], "verified_capabilities": ["transcribe"], "unverified_claims": ["realtime transcription"],
        "runtime_certified": True, "capability_certified": True, "evidence_notes": "Runtime-certified against the same local audio in Slice 02; no speed generalization from one utterance.",
    },
    {
        "id": "WHISPER_LARGE_V3", "family": "Whisper Large v3", "stage": ["transcribe"], "source_repository": "openai/whisper-large-v3", "revision": "06f233fe06e710322aca913c1bc4249a0d71fce1", "precision": "FP32", "runtime": "Transformers CPU", "local_or_hosted": "LOCAL",
        "license_id": "Apache-2.0", "license_source": "https://huggingface.co/openai/whisper-large-v3", "commercial_status": "PERMISSIVE", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0,
        "artifact_root": "whisper/whisper-large-v3", "artifacts": [
            _artifact("model.fp32-00001-of-00002.safetensors", bytes_=4993448880, sha256="08e0005225b3dbaf55dd13ac62926cc7e02c1025d66fa375e6fb305ff79cd4f9"),
            _artifact("model.fp32-00002-of-00002.safetensors", bytes_=1180663192, sha256="630ca774672856d2e0e39a702e590f635a1cfc5726a64b6578ab46dd367369a9"),
        ], "verified_capabilities": ["transcribe"], "runtime_certified": True, "capability_certified": True, "unverified_claims": [], "evidence_notes": "Existing independently verified Slice 02 model; exact artifact hashes recorded.",
    },
    {
        "id": "COHERE_TRANSCRIBE_ARABIC_07_2026", "family": "Cohere Transcribe Arabic 07-2026", "stage": ["transcribe"], "source_repository": "CohereLabs/cohere-transcribe-arabic-07-2026", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_ASR", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "cohere/Transcribe-Arabic-07-2026", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["Arabic transcription"], "evidence_notes": "Planned; not installed."},
    {
        "id": "OMNIASR_LLM_7B", "family": "Meta omniASR-LLM-7B", "stage": ["transcribe"], "source_repository": "facebook/omniASR-LLM-7B", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_ASR", "local_or_hosted": "LOCAL", "license_id": "Apache-2.0", "license_source": "https://huggingface.co/facebook/omniASR-LLM-7B", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "meta/omniASR-LLM-7B", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["multilingual transcription"], "evidence_notes": "Planned; license identifier requires local card verification before use."},
    {
        "id": "FIRERED_VAD", "family": "FireRedVAD", "stage": ["vad"], "source_repository": "FireRedTeam/FireRedVAD", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_VAD", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "UNKNOWN", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "firered/FireRedVAD", "artifacts": [_artifact("VAD/model.pth.tar", bytes_=2368049, sha256="63f4fb1b00a6b8607c118dd48efc18d5e40d67d99b7bf9aa7a8d61540cf23d71"), _artifact("Stream-VAD/model.pth.tar", bytes_=2283513, sha256="ec88a8ae8ac5f004cdbd20c1eac4a9e9d12067c3d51ac5b141afa1f921fb59c9"), _artifact("AED/model.pth.tar", bytes_=2370097, sha256="ad08a4e05b58ca328154e158d24cff57a2fe796ceabb63bb701544c3f7d4f7ad")], "verified_capabilities": [], "unverified_claims": ["voice activity detection"], "evidence_notes": "Weights integrity verified; runtime/capability certification remains pending and no simulated VAD output is exposed."},
    {
        "id": "AUDAR_DIARIZATION_V1", "family": "Audar-Diarization-V1", "stage": ["diarization"], "source_repository": "audarai/Audar-Diarization-V1", "revision": "230e5afed3f87637c12c8fb819dd0be9b1ddf6cb", "precision": "BF16", "runtime": "SPECIALIST_DIARIZATION", "local_or_hosted": "LOCAL", "license_id": "audarai-community-license-v1.0", "license_source": "https://www.audarai.com/license/audarai-community-license-v1.0/", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "audar/Audar-Diarization-V1", "artifacts": [_artifact("model.safetensors", bytes_=471103752, sha256="86444dd50d63cad3875ef3aab679ebc842466511c49753f9869b8e4ad5395cba")], "verified_capabilities": [], "unverified_claims": ["speaker diarization"], "evidence_notes": "Artifact integrity verified; runtime/capability certification remains pending."},
    {
        "id": "LIVEKIT_TURN_DETECTOR_V1_MINI", "family": "LiveKit Turn Detector v1-mini", "stage": ["turn_detection"], "source_repository": "livekit/turn-detector", "revision": "fba34c38ad5d30a63ebb83a9e6bf271cf4c91d67", "precision": "INT8_ONNX", "runtime": "ONNX Runtime CPU", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "https://huggingface.co/livekit/turn-detector", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "livekit/turn-detector-v1-mini", "artifacts": [_artifact("model_quantized.onnx", bytes_=165035487, sha256="4e685767c3643b0363c9f826a98325683f29e9c7d550162c8e8740ba33aa31aa")], "verified_capabilities": [], "unverified_claims": ["audio turn detection"], "evidence_notes": "Pinned artifact and SHA-256 resolved from the existing download manifest; ONNX load is separately probed, but completed/pause/continuation capability remains pending until the tokenizer/protocol bundle is present."},
    {
        "id": "QWEN3_8_27B_Q6_K_L", "family": "Qwen3.8-27B", "stage": ["summarize", "actionize", "function_call"], "source_repository": "Qwen/Qwen3.8-27B (GGUF conversion)", "revision": None, "precision": "Q6_K_L", "runtime": "llama.cpp", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "UNKNOWN", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "qwen/Qwen3.8-27B-Q6_K_L", "artifacts": [_artifact("Qwen3.8-27B-UD-Q6_K_L.gguf", bytes_=24193919904, sha256="121355b4c7422771da25adc74090e3c90138f77ce5c92d348687d47824ec80f4")], "verified_capabilities": [], "unverified_claims": ["multilingual tools", "structured output"], "evidence_notes": "Pinned artifact metadata; certification begins only after the scanner observes the final artifact as integrity-verified."},
    {
        "id": "BTL4_Q6_K_L", "family": "BTL-4", "stage": ["summarize", "actionize", "function_call"], "source_repository": "BTL-4 GGUF conversion", "revision": None, "precision": "Q6_K_L", "runtime": "llama.cpp", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "UNKNOWN", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "btl/BTL-4-Q6_K_L", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["function calling"], "evidence_notes": "Planned conversion; official upstream and license are not yet locally verified."},
    {
        "id": "GRANITE_4_1_30B_Q6_K", "family": "IBM Granite 4.1-30B", "stage": ["summarize", "actionize", "function_call", "verify"], "source_repository": "ibm-granite/granite-4.1-30b (GGUF conversion)", "revision": None, "precision": "Q6_K", "runtime": "llama.cpp", "local_or_hosted": "LOCAL", "license_id": "Apache-2.0", "license_source": "https://huggingface.co/ibm-granite", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "ibm/Granite-4.1-30B-Q6_K", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["structured output", "tool selection"], "evidence_notes": "Planned conversion; not installed."},
    {
        "id": "QWEN3_OMNI_30B_A3B_INSTRUCT", "family": "Qwen3-Omni-30B-A3B-Instruct", "stage": ["transcribe", "actionize", "function_call"], "source_repository": "Qwen/Qwen3-Omni-30B-A3B-Instruct", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_OMNI", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "qwen/Qwen3-Omni-30B-A3B-Instruct", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["direct audio interpretation"], "evidence_notes": "Planned; omni route disabled until runtime certification."},
    {
        "id": "AUDAR_TTS_V1_TURBO", "family": "Audar-TTS-V1-Turbo + NeuCodec", "stage": ["synthesize"], "source_repository": "audarai/Audar-TTS-V1-Turbo", "revision": None, "precision": "Q8_0", "runtime": "SPECIALIST_TTS", "local_or_hosted": "LOCAL", "license_id": "audarai-community-license-v1.0", "license_source": "https://www.audarai.com/license/audarai-community-license-v1.0/", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "audar/Audar-TTS-V1-Turbo", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["Arabic speech synthesis"], "evidence_notes": "Planned; NeuCodec artifact must be pinned separately."},
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _passive_download_artifacts(root: Path, plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Read final-path metadata from the downloader manifest only.

    The scanner never constructs, opens, stats, hashes, renames, or otherwise
    touches a temporary ``.part`` path.  A verified manifest entry is accepted
    only when its final path exists and has the declared byte count.
    """
    manifest_path = root / "_downloads" / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        body = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(body, dict):
        return {}
    label = f"{plan.get('id', '')} {plan.get('family', '')}".lower()
    if "qwen3_8_27b" not in label and "qwen3.8-27b" not in label:
        return {}
    found: dict[str, dict[str, Any]] = {}
    for queue_entry in body.get("queue", []):
        if not isinstance(queue_entry, dict):
            continue
        queue_label = " ".join((str(queue_entry.get("model", "")), str(queue_entry.get("candidate_id", "")))).lower()
        if "qwen3.8-27b" not in queue_label and "qwen38_27b" not in queue_label:
            continue
        for file_entry in queue_entry.get("files", []):
            if not isinstance(file_entry, dict) or not file_entry.get("path") or not file_entry.get("sha256"):
                continue
            found[str(file_entry["sha256"]).lower()] = file_entry
            found[str(file_entry.get("name", "")).lower()] = file_entry
    return found


def configured_roots() -> list[Path]:
    raw = os.getenv("SAUDI_STA_MODEL_ROOTS", r"D:\models")
    return [Path(item).expanduser() for item in raw.split(os.pathsep) if item.strip()]


def scan_models(roots: list[Path] | None = None) -> list[dict[str, Any]]:
    roots = roots or configured_roots()
    scanned: list[dict[str, Any]] = []
    for plan in PLANNED_MODELS:
        result = dict(plan)
        root = next((candidate for candidate in roots if candidate.exists() or candidate.drive), roots[0] if roots else Path("D:/models"))
        model_dir = root / str(plan["artifact_root"])
        passive_artifacts = _passive_download_artifacts(root, plan)
        artifacts = []
        missing = False
        any_present = False
        all_verified = bool(plan.get("artifacts"))
        for spec in plan.get("artifacts", []):
            passive = passive_artifacts.get(str(spec.get("sha256", "")).lower()) or passive_artifacts.get(Path(spec["path"]).name.lower())
            path = Path(str(passive["path"])) if passive else model_dir / spec["path"]
            present = path.is_file()
            any_present = any_present or present
            item = {"path": str(path), "expected_bytes": spec.get("expected_bytes"), "sha256": spec.get("sha256"), "present": present}
            if present:
                actual_bytes = path.stat().st_size
                item["bytes"] = actual_bytes
                manifest_verified = passive and passive.get("status") == "INTEGRITY_VERIFIED" and actual_bytes == int(passive.get("bytes", actual_bytes))
                size_matches = spec.get("expected_bytes") is None or actual_bytes == spec["expected_bytes"]
                item["local_sha256"] = _sha256(path) if spec.get("sha256") and size_matches and not manifest_verified else None
                if not size_matches:
                    all_verified = False
                    item["integrity"] = "SIZE_MISMATCH"
                elif manifest_verified:
                    item["integrity"] = "VERIFIED_BY_DOWNLOAD_MANIFEST"
                elif spec.get("sha256") and item["local_sha256"].lower() != spec["sha256"].lower():
                    all_verified = False
                    item["integrity"] = "HASH_MISMATCH"
                else:
                    item["integrity"] = "VERIFIED" if spec.get("sha256") else "PRESENT_UNVERIFIED"
            else:
                missing = True
                all_verified = False
                item["integrity"] = "MISSING"
            artifacts.append(item)
        if missing or (not artifacts and not model_dir.exists()):
            state = "NOT_INSTALLED"
        elif all_verified:
            state = "INTEGRITY_VERIFIED"
        elif any_present or model_dir.exists():
            state = "ARTIFACT_PRESENT"
        else:
            state = "NOT_INSTALLED"
        result.update({"artifact_state": state, "artifact_path": str(model_dir), "artifacts": artifacts,
                       "runtime_certified": bool(plan.get("runtime_certified", False) and state == "INTEGRITY_VERIFIED"),
                       "capability_certified": bool(plan.get("capability_certified", False) and state == "INTEGRITY_VERIFIED"),
                       "runtime_state": "RUNTIME_LOAD_VERIFIED" if plan.get("runtime_certified") and state == "INTEGRITY_VERIFIED" else "RUNTIME_PENDING",
                       "auto_activation": False})
        scanned.append(result)
    return scanned
