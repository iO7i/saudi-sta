"""Planned local model laboratory registry and explicit-root artifact scanner.

The scanner is deliberately passive: it never downloads, loads, executes, or
activates a model.  Runtime and capability certification remain separate
operator actions.
"""

from __future__ import annotations

import hashlib
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
        ], "verified_capabilities": [], "unverified_claims": ["Arabic transcription", "Gulf dialects", "code-switching"],
        "evidence_notes": "Q4 local bridge; NOT_REFERENCE_PRECISION; no leaderboard parity claim.",
    },
    {
        "id": "AUDAR_TURBO_Q8_LOCAL", "family": "Audar-ASR-V1-Turbo", "stage": ["transcribe"],
        "source_repository": "audarai/Audar-ASR-V1-Turbo", "revision": "371428bea487c7aec82b27dc21f8d4324002e98e",
        "precision": "Q8_0", "runtime": "llama.cpp mtmd", "local_or_hosted": "LOCAL",
        "license_id": "audarai-community-license-v1.0", "license_source": "https://www.audarai.com/license/audarai-community-license-v1.0/",
        "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0,
        "artifact_root": "audar/Audar-ASR-V1-Turbo", "artifacts": [_artifact("Audar-ASR-V1-Turbo-Q8_0.gguf")],
        "shared_artifacts": ["mmproj-Audar-ASR-V1-Turbo.gguf"], "verified_capabilities": [], "unverified_claims": ["Arabic transcription"],
        "evidence_notes": "Future distinct Q8 candidate; may reuse the verified BF16 projector when contract-compatible.",
    },
    {
        "id": "AUDAR_FLASH_Q8_LOCAL", "family": "Audar-ASR-V1-Flash", "stage": ["transcribe"],
        "source_repository": "audarai/Audar-ASR-V1-Flash", "revision": None, "precision": "Q8_0", "runtime": "llama.cpp mtmd", "local_or_hosted": "LOCAL",
        "license_id": "audarai-open-license-v1.0", "license_source": "https://www.audarai.com/license/audarai-open-license-v1.0/",
        "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0,
        "artifact_root": "audar/Audar-ASR-V1-Flash", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["Arabic transcription", "realtime transcription"],
        "evidence_notes": "Planned; exact pinned files are recorded by the download worker when resolved.",
    },
    {
        "id": "WHISPER_LARGE_V3", "family": "Whisper Large v3", "stage": ["transcribe"], "source_repository": "openai/whisper-large-v3", "revision": "06f233fe06e710322aca913c1bc4249a0d71fce1", "precision": "FP32", "runtime": "Transformers CPU", "local_or_hosted": "LOCAL",
        "license_id": "Apache-2.0", "license_source": "https://huggingface.co/openai/whisper-large-v3", "commercial_status": "PERMISSIVE", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0,
        "artifact_root": "whisper/whisper-large-v3", "artifacts": [], "verified_capabilities": ["transcribe"], "unverified_claims": [], "evidence_notes": "Existing independently verified Slice 02 model; external manifest supplies artifact hashes.",
    },
    {
        "id": "COHERE_TRANSCRIBE_ARABIC_07_2026", "family": "Cohere Transcribe Arabic 07-2026", "stage": ["transcribe"], "source_repository": "CohereLabs/cohere-transcribe-arabic-07-2026", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_ASR", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "cohere/Transcribe-Arabic-07-2026", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["Arabic transcription"], "evidence_notes": "Planned; not installed."},
    {
        "id": "OMNIASR_LLM_7B", "family": "Meta omniASR-LLM-7B", "stage": ["transcribe"], "source_repository": "facebook/omniASR-LLM-7B", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_ASR", "local_or_hosted": "LOCAL", "license_id": "Apache-2.0", "license_source": "https://huggingface.co/facebook/omniASR-LLM-7B", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "meta/omniASR-LLM-7B", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["multilingual transcription"], "evidence_notes": "Planned; license identifier requires local card verification before use."},
    {
        "id": "FIRERED_VAD", "family": "FireRedVAD", "stage": ["vad"], "source_repository": "FireRedTeam/FireRedVAD", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_VAD", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "UNKNOWN", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "firered/FireRedVAD", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["voice activity detection"], "evidence_notes": "Planned; runtime installation is separate."},
    {
        "id": "AUDAR_DIARIZATION_V1", "family": "Audar-Diarization-V1", "stage": ["diarization"], "source_repository": "audarai/Audar-Diarization-V1", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_DIARIZATION", "local_or_hosted": "LOCAL", "license_id": "audarai-community-license-v1.0", "license_source": "https://www.audarai.com/license/audarai-community-license-v1.0/", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "audar/Audar-Diarization-V1", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["speaker diarization"], "evidence_notes": "Planned; not installed."},
    {
        "id": "LIVEKIT_TURN_DETECTOR_V1_MINI", "family": "LiveKit Turn Detector v1-mini", "stage": ["turn_detection"], "source_repository": "LiveKit turn detector distribution", "revision": None, "precision": "UNKNOWN", "runtime": "SPECIALIST_TURN_DETECTOR", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "UNKNOWN", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "livekit/turn-detector-v1-mini", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["audio turn detection"], "evidence_notes": "Distribution method requires main-agent runtime review; no fabricated weight URL."},
    {
        "id": "QWEN3_8_27B_Q6_K_L", "family": "Qwen3.8-27B", "stage": ["summarize", "actionize", "function_call"], "source_repository": "Qwen/Qwen3.8-27B (GGUF conversion)", "revision": None, "precision": "Q6_K_L", "runtime": "llama.cpp", "local_or_hosted": "LOCAL", "license_id": "UNKNOWN", "license_source": "UNKNOWN", "commercial_status": "UNKNOWN", "redistribution_status": "UNKNOWN", "teacher_use_status": "UNKNOWN", "training_eligibility": "UNKNOWN", "monetary_marginal_cost": 0, "artifact_root": "qwen/Qwen3.8-27B-Q6_K_L", "artifacts": [], "verified_capabilities": [], "unverified_claims": ["multilingual tools", "structured output"], "evidence_notes": "Planned conversion; lineage and license must be captured before download."},
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
        artifacts = []
        missing = False
        any_present = False
        all_verified = bool(plan.get("artifacts"))
        for spec in plan.get("artifacts", []):
            path = model_dir / spec["path"]
            present = path.is_file()
            any_present = any_present or present
            item = {"path": str(path), "expected_bytes": spec.get("expected_bytes"), "sha256": spec.get("sha256"), "present": present}
            if present:
                actual_bytes = path.stat().st_size
                item["bytes"] = actual_bytes
                item["local_sha256"] = _sha256(path) if spec.get("sha256") else None
                if spec.get("expected_bytes") is not None and actual_bytes != spec["expected_bytes"]:
                    all_verified = False
                    item["integrity"] = "SIZE_MISMATCH"
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
        result.update({"artifact_state": state, "artifact_path": str(model_dir), "artifacts": artifacts, "runtime_certified": False, "capability_certified": False, "auto_activation": False})
        scanned.append(result)
    return scanned

