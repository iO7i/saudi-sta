from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .policy import PolicyViolation, assert_dispatch_allowed, validate_loopback_url
from .schemas import CapabilityProvenance, ExecutionMode, Role, RoleBinding


OFFICIAL_SOURCES = {
    "ollama_tags": "https://docs.ollama.com/api/tags",
    "ollama_chat": "https://docs.ollama.com/api/chat",
    "ollama_locality": "https://docs.ollama.com/faq",
    "faster_whisper": "https://github.com/SYSTRAN/faster-whisper",
    "openai_function_calling": "https://developers.openai.com/api/docs/guides/function-calling",
    "openai_audio": "https://developers.openai.com/api/docs/",
    "humain_voice": "https://voice.humain.com/",
}


class LocalModelUnavailable(RuntimeError):
    pass


class LocalArtifactRegistry:
    """Reads an operator-created local manifest; it never discovers or downloads weights."""

    def __init__(self, manifest_path: str | None = None) -> None:
        configured = manifest_path or os.getenv("SAUDI_STA_LOCAL_MODEL_MANIFEST")
        configured_many = os.getenv("SAUDI_STA_LOCAL_MODEL_MANIFESTS")
        default_paths = [Path("D:/saudi-sta-models/saudi-sta-local-models.json"), Path("D:/models/whisper/saudi-sta-local-models.json"), Path("D:/models/audar/Audar-ASR-V1-Turbo/saudi-sta-audar-q4-manifest.json"), Path("D:/models/_downloads/manifest.json")]
        raw_paths = ([configured] if configured else []) + ([item for item in configured_many.split(os.pathsep) if item] if configured_many else [])
        if not raw_paths:
            raw_paths.extend(str(path) for path in default_paths if path.is_file())
        self.manifest_paths = list(dict.fromkeys(raw_paths))
        self.manifest_path = self.manifest_paths[0] if self.manifest_paths else None
        self._hash_cache: dict[str, tuple[int, int, str]] = {}

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    def entries(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for manifest in self.manifest_paths:
            path = Path(manifest)
            if not path.is_file():
                continue
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            entries = body.get("models", []) if isinstance(body, dict) else []
            result.extend(entry for entry in entries if isinstance(entry, dict))
            if isinstance(body, dict):
                result.extend(self._download_entries(body))
        return result

    @staticmethod
    def _download_entries(body: dict[str, Any]) -> list[dict[str, Any]]:
        """Adapt passive downloader metadata into the normal local GGUF manifest.

        Only the final artifact paths from the manifest are retained.  The
        downloader's temporary ``.part`` path is intentionally never opened,
        stat'ed, hashed, or returned to callers.
        """
        adapted: list[dict[str, Any]] = []
        for queued in body.get("queue", []):
            if not isinstance(queued, dict):
                continue
            model = str(queued.get("model", ""))
            candidate = str(queued.get("candidate_id", ""))
            label = " ".join((model, candidate)).lower()
            if "qwen3.8-27b" not in label and "qwen38_27b" not in label:
                continue
            artifacts: list[dict[str, Any]] = []
            statuses: list[str] = []
            for file_entry in queued.get("files", []):
                if not isinstance(file_entry, dict) or not file_entry.get("path") or not file_entry.get("sha256"):
                    continue
                # file_entry["path"] is the verified final path.  No partial
                # path is constructed or touched here.
                artifacts.append({
                    "path": str(file_entry["path"]),
                    "bytes": int(file_entry.get("bytes", 0)),
                    "sha256": str(file_entry["sha256"]),
                    "remote_oid": file_entry.get("remote_oid"),
                })
                if file_entry.get("status"):
                    statuses.append(str(file_entry["status"]))
            if not artifacts:
                continue
            adapted.append({
                "id": "QWEN3_8_27B_Q6_K_L",
                "provider": "llama_cpp_local",
                "family": "Qwen3.8-27B",
                "roles": ["summarize", "actionize", "function_call", "verify"],
                "revision": queued.get("revision"),
                "quantization": "Q6_K_L",
                "artifacts": artifacts,
                "download_state": "INTEGRITY_VERIFIED" if statuses and all(item == "INTEGRITY_VERIFIED" for item in statuses) else (statuses[0] if statuses else "PLANNED"),
                "source": queued.get("source"),
                "evidence": "PASSIVE_DOWNLOAD_MANIFEST_METADATA",
            })
        return adapted

    def verify(self, entry: dict[str, Any]) -> tuple[bool, str | None, list[dict[str, Any]]]:
        artifacts = entry.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            return False, "artifact list is required", []
        verified: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                return False, "invalid artifact entry", verified
            path = Path(str(artifact.get("path", "")))
            declared = artifact.get("sha256")
            if not path.is_file() or not isinstance(declared, str):
                return False, f"missing artifact: {path.name or 'unnamed'}", verified
            stat = path.stat()
            cache_key = str(path.resolve())
            cached = self._hash_cache.get(cache_key)
            actual = cached[2] if cached and cached[:2] == (stat.st_size, stat.st_mtime_ns) else self._sha256(path)
            self._hash_cache[cache_key] = (stat.st_size, stat.st_mtime_ns, actual)
            if actual.lower() != declared.lower():
                return False, f"digest mismatch: {path.name}", verified
            verified.append({"path": str(path), "bytes": stat.st_size, "sha256": actual})
        return True, None, verified

    def entry(self, model_key: str, provider: str) -> dict[str, Any] | None:
        for candidate in self.entries():
            if candidate.get("id") == model_key and candidate.get("provider") == provider:
                return candidate
        return None


class OllamaAdapter:
    """Strictly local Ollama adapter. No pull endpoint exists in this implementation."""

    provider = "ollama_local"

    def __init__(self, base_url: str | None = None, artifact_manifest_path: str | None = None) -> None:
        self.base_url = base_url or os.getenv("SAUDI_STA_OLLAMA_URL")
        self.artifact_manifest_path = artifact_manifest_path or os.getenv("SAUDI_STA_OLLAMA_ARTIFACT_MANIFEST")
        self.checks: list[dict[str, Any]] = []

    def _manifest(self) -> dict[str, Any]:
        if not self.artifact_manifest_path:
            return {}
        path = Path(self.artifact_manifest_path)
        if not path.is_file():
            self.checks.append({"check": "artifact manifest", "result": "missing"})
            return {}
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.checks.append({"check": "artifact manifest", "result": "invalid"})
            return {}
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    def discover(self) -> list[RoleBinding]:
        self.checks = []
        if not self.base_url:
            self.checks.append({"check": "endpoint", "result": "not configured; no local request attempted"})
            return []
        locality = validate_loopback_url(self.base_url)
        self.checks.append({"check": "endpoint", "result": locality.reason or "passed", "details": locality.checks})
        if not locality.allowed:
            return []
        # A loopback endpoint can relay to cloud. Explicit operator confirmation and a verified file are both required.
        local_only_confirmed = os.getenv("SAUDI_STA_OLLAMA_LOCAL_ONLY_CONFIRMED") == "1"
        if not local_only_confirmed:
            self.checks.append({"check": "local-only server mode", "result": "not confirmed"})
            return []
        try:
            with httpx.Client(timeout=2.0, follow_redirects=False, trust_env=False) as client:
                response = client.get(self.base_url.rstrip("/") + "/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
        except (httpx.HTTPError, ValueError) as exc:
            self.checks.append({"check": "tags discovery", "result": "unavailable", "reason": type(exc).__name__})
            return []
        manifest = self._manifest()
        result: list[RoleBinding] = []
        for model in models:
            name, remote_digest = model.get("name"), model.get("digest")
            entry = manifest.get(name) if name else None
            if not isinstance(entry, dict):
                self.checks.append({"check": "artifact", "model": name, "result": "unverified; no manifest entry"})
                continue
            artifact = Path(str(entry.get("path", "")))
            declared_digest = entry.get("file_sha256")
            if not artifact.is_file() or not isinstance(declared_digest, str) or self._sha256(artifact) != declared_digest:
                self.checks.append({"check": "artifact", "model": name, "result": "file/digest verification failed"})
                continue
            if entry.get("ollama_digest") != remote_digest:
                self.checks.append({"check": "artifact", "model": name, "result": "Ollama digest mismatch"})
                continue
            roles = entry.get("roles", ["summarize", "actionize", "function_call"])
            for role in roles:
                if role not in {"summarize", "actionize", "function_call"}:
                    continue
                result.append(RoleBinding(
                    id=f"ollama:{name}:{role}", provider=self.provider, model_id=name, revision_or_digest=remote_digest,
                    role=Role(role), prompt_version="local-v1", schema_version="sta-v1", execution_mode=ExecutionMode.LOCAL,
                    capability_provenance=CapabilityProvenance.VERIFIED_LOCAL, capabilities=[role, "structured_output"],
                    tool_mode="NATIVE_TOOL_CALL" if bool(entry.get("native_tools", False)) and role == "function_call" else "STRUCTURED_TOOL_EMULATION",
                ))
            self.checks.append({"check": "artifact", "model": name, "result": "verified locally"})
        return result

    def invoke(self, binding: RoleBinding, messages: list[dict[str, str]], *, json_schema: dict[str, Any], tools: list[dict[str, Any]] | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
        assert_dispatch_allowed(self.provider, self.base_url)
        if binding.provider != self.provider or binding.capability_provenance != CapabilityProvenance.VERIFIED_LOCAL:
            raise LocalModelUnavailable("UNAVAILABLE_LOCAL_MODEL: binding is not a verified local artifact")
        if os.getenv("SAUDI_STA_OLLAMA_LOCAL_ONLY_CONFIRMED") != "1":
            raise LocalModelUnavailable("UNAVAILABLE_LOCAL_MODEL: server local-only mode was not confirmed")
        body: dict[str, Any] = {"model": binding.model_id, "messages": messages, "stream": False, "format": json_schema}
        if tools and binding.tool_mode == "NATIVE":
            body["tools"] = tools
        try:
            with httpx.Client(timeout=20.0, follow_redirects=False, trust_env=False) as client:
                response = client.post(self.base_url.rstrip("/") + "/api/chat", json=body)
                response.raise_for_status()
                message = response.json().get("message", {})
        except httpx.HTTPError as exc:
            raise LocalModelUnavailable(f"LOCAL_MODEL_REQUEST_FAILED:{type(exc).__name__}") from exc
        # Intentionally return only content/tool_calls; thinking/reasoning fields never leave the adapter.
        return {"content": message.get("content", ""), "tool_calls": message.get("tool_calls", [])}


class FasterWhisperAdapter:
    provider = "faster_whisper_local"

    def __init__(self, model_dir: str | None = None) -> None:
        self.model_dir_value = model_dir or os.getenv("SAUDI_STA_SPEECH_MODEL_DIR")
        self.model_dir = Path(self.model_dir_value).resolve() if self.model_dir_value else None

    def status(self) -> dict[str, Any]:
        if not self.model_dir or not self.model_dir.is_dir():
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: explicit existing model directory is required"}
        if importlib.util.find_spec("faster_whisper") is None:
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: faster-whisper runtime is not installed"}
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        if "local_files_only" not in inspect.signature(WhisperModel).parameters:
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: runtime lacks local-files-only guarantee"}
        return {"available": True, "reason": None}

    def transcribe(self, audio_path: Path) -> dict[str, Any]:
        status = self.status()
        if not status["available"]:
            raise LocalModelUnavailable(status["reason"])
        assert_dispatch_allowed(self.provider, artifact_verified=True)
        # The import and model construction occur only after a caller supplied a real local directory.
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        model = WhisperModel(str(self.model_dir), device="cpu", compute_type="int8", local_files_only=True)
        segments, info = model.transcribe(str(audio_path), vad_filter=True)
        parts = [{"start": segment.start, "end": segment.end, "text": segment.text} for segment in segments]
        return {"text": "".join(part["text"] for part in parts).strip(), "segments": parts, "language": getattr(info, "language", None)}

    def binding(self) -> RoleBinding:
        status = self.status()
        return RoleBinding(
            id="faster_whisper_local:transcribe:v1", provider=self.provider,
            model_id=str(self.model_dir) if self.model_dir else "no-explicit-model-directory", revision_or_digest=None,
            role=Role.TRANSCRIBE, prompt_version="none", schema_version="sta-v1", execution_mode=ExecutionMode.LOCAL,
            capability_provenance=CapabilityProvenance.VERIFIED_LOCAL if status["available"] else CapabilityProvenance.UNKNOWN,
            capabilities=["transcribe"] if status["available"] else [], available=status["available"],
            unavailable_reason=status["reason"], tool_mode="NONE",
        )


class TransformersWhisperAdapter:
    """Canonical Transformers Whisper runtime, loaded only from hash-verified local files."""

    provider = "transformers_whisper_local"

    def __init__(self, registry: LocalArtifactRegistry) -> None:
        self.registry = registry
        self._loaded_key: str | None = None
        self._pipeline: Any | None = None
        self._load_ms: float | None = None

    def _entries(self) -> list[dict[str, Any]]:
        return [entry for entry in self.registry.entries() if entry.get("provider") == self.provider]

    def _entry_for(self, binding: RoleBinding | None = None) -> dict[str, Any] | None:
        entries = self._entries()
        if binding:
            return self.registry.entry(binding.model_id, self.provider)
        return entries[0] if entries else None

    def status(self, binding: RoleBinding | None = None) -> dict[str, Any]:
        entry = self._entry_for(binding)
        if not entry:
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: verified local Whisper manifest entry is required"}
        if importlib.util.find_spec("transformers") is None or importlib.util.find_spec("torch") is None:
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: transformers and torch runtime are required"}
        valid, reason, artifacts = self.registry.verify(entry)
        if not valid:
            return {"available": False, "reason": f"UNAVAILABLE_LOCAL_MODEL: {reason}"}
        model_dir = Path(str(entry.get("model_dir", "")))
        if not model_dir.is_dir():
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: Whisper model directory is missing"}
        return {"available": True, "reason": None, "artifacts": artifacts, "runtime": "transformers+cpu", "model_dir": str(model_dir)}

    def binding(self) -> RoleBinding:
        entry = self._entry_for()
        status = self.status()
        if not entry:
            return RoleBinding(
                id="transformers_whisper_local:transcribe:v1", provider=self.provider, model_id="no-verified-whisper-manifest",
                role=Role.TRANSCRIBE, prompt_version="whisper-ar-v1", schema_version="sta-v2", generation={},
                execution_mode=ExecutionMode.LOCAL, capability_provenance=CapabilityProvenance.UNKNOWN,
                capabilities=[], available=False, unavailable_reason=status["reason"], tool_mode="NONE",
            )
        return RoleBinding(
            id=f"{self.provider}:{entry['id']}:transcribe", provider=self.provider, model_id=str(entry["id"]),
            revision_or_digest=f"{entry.get('revision') or entry.get('digest') or 'unknown'};{entry.get('artifacts', [{}])[0].get('sha256', 'unknown')}", role=Role.TRANSCRIBE,
            prompt_version="whisper-ar-v1", schema_version="sta-v2",
            generation={"language": "arabic", "task": "transcribe", "return_timestamps": True, "device": "cpu"},
            execution_mode=ExecutionMode.LOCAL,
            capability_provenance=CapabilityProvenance.VERIFIED_LOCAL if status["available"] else CapabilityProvenance.UNKNOWN,
            capabilities=["transcribe", "segment_timestamps"] if status["available"] else [], available=status["available"],
            unavailable_reason=status["reason"], tool_mode="NONE",
            artifact_hashes=[str(item.get("sha256")) for item in status.get("artifacts", []) if item.get("sha256")],
        )

    @staticmethod
    def _decode_audio(audio_path: Path) -> tuple[Any, int]:
        """Decode browser-recorded WebM/WAV locally through PyAV, with no subprocess or network."""
        try:
            import av  # type: ignore[import-not-found]
            import numpy as np  # type: ignore[import-not-found]
        except ImportError as exc:
            raise LocalModelUnavailable("UNAVAILABLE_LOCAL_MODEL: PyAV and NumPy are required for local audio decoding") from exc
        try:
            container = av.open(str(audio_path))
            stream = next((stream for stream in container.streams if stream.type == "audio"), None)
            if stream is None:
                raise LocalModelUnavailable("UNSUPPORTED_LOCAL_AUDIO: no audio stream")
            resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
            chunks = []
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    chunks.append(converted.to_ndarray().reshape(-1))
            for converted in resampler.resample(None):
                chunks.append(converted.to_ndarray().reshape(-1))
            container.close()
            if not chunks:
                raise LocalModelUnavailable("UNSUPPORTED_LOCAL_AUDIO: no decoded samples")
            return np.concatenate(chunks).astype("float32", copy=False), 16000
        except LocalModelUnavailable:
            raise
        except Exception as exc:
            raise LocalModelUnavailable(f"UNSUPPORTED_LOCAL_AUDIO_DECODE:{type(exc).__name__}") from exc

    def _load(self, entry: dict[str, Any]) -> bool:
        key = str(entry["id"])
        if self._pipeline is not None and self._loaded_key == key:
            return False
        started = time.perf_counter()
        try:
            import torch  # type: ignore[import-not-found]
            # Transformers 5.x imports the optional distributed DTensor symbol,
            # while the supported CPU inference path here uses no distributed tensors.
            # Keep this compatibility shim narrow and local to model loading.
            try:
                import torch.distributed.tensor as torch_tensor  # type: ignore[import-not-found]
                if not hasattr(torch_tensor, "DTensor"):
                    torch_tensor.DTensor = object  # type: ignore[attr-defined]
            except ImportError:
                pass
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline  # type: ignore[import-not-found]
            model_dir = str(entry["model_dir"])
            model = AutoModelForSpeechSeq2Seq.from_pretrained(model_dir, torch_dtype=torch.float32, use_safetensors=True, variant="fp32", local_files_only=True)
            processor = AutoProcessor.from_pretrained(model_dir, local_files_only=True)
            self._pipeline = pipeline(
                "automatic-speech-recognition", model=model, tokenizer=processor.tokenizer,
                feature_extractor=processor.feature_extractor, torch_dtype=torch.float32, device=-1,
            )
            self._loaded_key = key
            self._load_ms = (time.perf_counter() - started) * 1000
            return True
        except Exception as exc:
            self._pipeline, self._loaded_key = None, None
            raise LocalModelUnavailable(f"LOCAL_WHISPER_LOAD_FAILED:{type(exc).__name__}") from exc

    def transcribe(self, binding: RoleBinding, audio_path: Path) -> dict[str, Any]:
        status = self.status(binding)
        if not status["available"]:
            raise LocalModelUnavailable(status["reason"])
        assert_dispatch_allowed(self.provider, artifact_verified=True)
        entry = self._entry_for(binding)
        assert entry is not None
        cold_start = self._load(entry)
        samples, sampling_rate = self._decode_audio(audio_path)
        started = time.perf_counter()
        try:
            from concurrent.futures import ThreadPoolExecutor, TimeoutError

            def run_pipeline() -> dict[str, Any]:
                return self._pipeline(
                    {"array": samples, "sampling_rate": sampling_rate},
                    generate_kwargs={"language": "arabic", "task": "transcribe"}, return_timestamps=True,
                )

            timeout_seconds = float(entry.get("timeout_seconds", 120))
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="saudi-sta-whisper")
            future = executor.submit(run_pipeline)
            try:
                result = future.result(timeout=timeout_seconds)
            except TimeoutError as exc:
                future.cancel()
                raise LocalModelUnavailable("LOCAL_WHISPER_TIMEOUT") from exc
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except LocalModelUnavailable:
            raise
        except Exception as exc:
            raise LocalModelUnavailable(f"LOCAL_WHISPER_INFERENCE_FAILED:{type(exc).__name__}") from exc
        segments = []
        for chunk in result.get("chunks", []):
            timestamp = chunk.get("timestamp") or (None, None)
            segments.append({"start": timestamp[0], "end": timestamp[1], "text": str(chunk.get("text", "")).strip()})
        elapsed = (time.perf_counter() - started) * 1000
        return {
            "text": str(result.get("text", "")).strip(), "segments": segments, "language": "ar",
            "runtime": "transformers+cpu", "cold_start": cold_start, "model_load_ms": self._load_ms if cold_start else 0.0,
            "latency_ms": elapsed, "total_latency_ms": elapsed, "inference_latency_ms": elapsed,
            "provider_diagnostics": {"language": "ar", "runtime": "transformers+cpu"},
            "resource_measurement": {"runtime": "transformers+cpu", "execution_mode": "cpu", "artifact_bytes": sum(item["bytes"] for item in status.get("artifacts", [])), "peak_ram_or_vram": None},
            "signals": {
                "average_log_probability": {"available": False, "value": None},
                "no_speech_probability": {"available": False, "value": None},
                "compression_ratio": {"available": False, "value": None},
                "segment_stability": {"available": False, "value": None},
                "alternative_decoding": {"available": False, "value": None},
            },
        }


class AudarMtmdAdapter:
    """Pinned Audar GGUF + BF16 projector through llama.cpp mtmd.

    The adapter accepts only an operator-written, hash-verified manifest and
    invokes the exact local executable/model paths.  It never uses `-hf`, a
    server endpoint, or an implicit download.
    """

    provider = "audar_mtmd_local"

    def __init__(self, registry: LocalArtifactRegistry) -> None:
        self.registry = registry
        self._loaded_key: str | None = None

    def _entries(self) -> list[dict[str, Any]]:
        return [entry for entry in self.registry.entries() if entry.get("provider") == self.provider]

    def _entry(self, binding: RoleBinding | None = None) -> dict[str, Any] | None:
        entries = self._entries()
        if binding:
            return self.registry.entry(binding.model_id, self.provider)
        return entries[0] if entries else None

    @staticmethod
    def _decoder_artifact(entry: dict[str, Any]) -> Path | None:
        declared = entry.get("decoder_filename")
        artifacts = entry.get("artifacts", [])
        if declared:
            for item in artifacts:
                path = Path(str(item.get("path", "")))
                if path.name == str(declared):
                    return path
        return next((Path(str(item.get("path", ""))) for item in artifacts
                     if str(item.get("path", "")).lower().endswith(".gguf") and "mmproj" not in str(item.get("path", "")).lower()), None)

    @staticmethod
    def _projector_artifact(entry: dict[str, Any]) -> Path | None:
        return next((Path(str(item.get("path", ""))) for item in entry.get("artifacts", [])
                     if "mmproj" in str(item.get("path", "")).lower()), None)

    def status(self, binding: RoleBinding | None = None) -> dict[str, Any]:
        entry = self._entry(binding)
        if not entry:
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: Audar mtmd manifest entry is required"}
        runtime = Path(str(entry.get("runtime_path", "")))
        if not runtime.is_file():
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: llama-mtmd-cli executable is missing"}
        valid, reason, artifacts = self.registry.verify(entry)
        return {"available": valid, "reason": None if valid else f"UNAVAILABLE_LOCAL_MODEL: {reason}", "artifacts": artifacts, "runtime": str(runtime)}

    def binding(self) -> RoleBinding:
        entry = self._entry()
        status = self.status()
        if not entry:
            return RoleBinding(id=f"{self.provider}:transcribe:v1", provider=self.provider, model_id="no-audar-manifest", role=Role.TRANSCRIBE, prompt_version="audar-ar-v1", schema_version="sta-v2", execution_mode=ExecutionMode.LOCAL, capability_provenance=CapabilityProvenance.UNKNOWN, available=False, unavailable_reason=status["reason"])
        artifacts = entry.get("artifacts", [])
        decoder = self._decoder_artifact(entry)
        decoder_hash = next((item.get("sha256") for item in artifacts if decoder and Path(str(item.get("path"))).name == decoder.name), "unknown")
        return RoleBinding(
            id=f"{self.provider}:{entry.get('id', 'AUDAR_TURBO_Q4_LOCAL_BRIDGE')}:transcribe", provider=self.provider,
            model_id=str(entry.get("id", "AUDAR_TURBO_Q4_LOCAL_BRIDGE")), revision_or_digest=f"{entry.get('revision', 'unknown')};{decoder_hash}", role=Role.TRANSCRIBE,
            prompt_version="audar-ar-v1", schema_version="sta-v2", generation={"temperature": 0, "max_tokens": 512, "runtime": "llama.cpp mtmd", "precision": entry.get("precision", "Q4_K_M")},
            execution_mode=ExecutionMode.LOCAL, capability_provenance=CapabilityProvenance.VERIFIED_LOCAL if status["available"] else CapabilityProvenance.UNKNOWN,
            capabilities=["transcribe", "arabic", "code_switching"] if status["available"] else [], available=status["available"], unavailable_reason=status["reason"], tool_mode="NONE",
            artifact_hashes=[str(item.get("sha256")) for item in artifacts if item.get("sha256")],
        )

    def discover(self) -> list[RoleBinding]:
        """Return one independently selectable binding for every verified Audar entry."""
        return [self._binding_for(entry) for entry in self._entries()]

    def _binding_for(self, entry: dict[str, Any]) -> RoleBinding:
        placeholder = RoleBinding(id="placeholder", provider=self.provider, model_id=str(entry.get("id")), role=Role.TRANSCRIBE,
                                  prompt_version="", schema_version="", execution_mode=ExecutionMode.LOCAL,
                                  capability_provenance=CapabilityProvenance.UNKNOWN)
        status = self.status(placeholder)
        artifacts = entry.get("artifacts", [])
        decoder = self._decoder_artifact(entry)
        decoder_hash = next((item.get("sha256") for item in artifacts if decoder and Path(str(item.get("path"))).name == decoder.name), "unknown")
        return RoleBinding(
            id=f"{self.provider}:{entry.get('id', 'unknown')}:transcribe", provider=self.provider,
            model_id=str(entry.get("id", "unknown")), revision_or_digest=f"{entry.get('revision', 'unknown')};{decoder_hash}", role=Role.TRANSCRIBE,
            prompt_version="audar-ar-v1", schema_version="sta-v2", generation={"temperature": 0, "max_tokens": 512, "runtime": "llama.cpp mtmd", "precision": entry.get("precision")},
            execution_mode=ExecutionMode.LOCAL, capability_provenance=CapabilityProvenance.VERIFIED_LOCAL if status["available"] else CapabilityProvenance.UNKNOWN,
            capabilities=["transcribe", "arabic", "code_switching"] if status["available"] else [], available=status["available"], unavailable_reason=status["reason"], tool_mode="NONE",
            artifact_hashes=[str(item.get("sha256")) for item in artifacts if item.get("sha256")],
        )

    @staticmethod
    def _text_from_cli(stdout: str) -> str:
        # llama-mtmd-cli emits diagnostics and the assistant completion. Keep
        # the raw output separately; this conservative parser avoids inventing
        # timestamps or confidence fields.
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        clean = [line for line in lines if not line.startswith(("llama_", "main:", "load_", "ggml_", "system_info", "sampling"))]
        text = (clean[-1] if clean else "").strip()
        # Audar Flash prefixes the completion with a native language marker.
        text = re.sub(r"^language\s+[A-Za-z-]+\s*<asr_text>\s*", "", text, flags=re.IGNORECASE)
        return text.strip()

    def transcribe(self, binding: RoleBinding, audio_path: Path) -> dict[str, Any]:
        status = self.status(binding)
        if not status["available"]:
            raise LocalModelUnavailable(status["reason"])
        assert_dispatch_allowed(self.provider, artifact_verified=True)
        entry = self._entry(binding)
        assert entry is not None
        decoder = self._decoder_artifact(entry)
        projector = self._projector_artifact(entry)
        if not decoder or not projector or not audio_path.is_file():
            raise LocalModelUnavailable("UNAVAILABLE_LOCAL_MODEL: Audar decoder, BF16 projector, and audio are required")
        command = [str(entry["runtime_path"]), "-m", str(decoder), "--mmproj", str(projector), "--audio", str(audio_path), "-sys", "فرّغ الكلام العربي التالي.", "--temp", "0", "-n", str(entry.get("max_tokens", 512))]
        started = time.perf_counter()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False,
                                   env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        try:
            raw, _stderr = process.communicate(timeout=float(entry.get("timeout_seconds", 180)))
            return_code = process.returncode
        except subprocess.TimeoutExpired as exc:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            else:
                process.kill()
            process.communicate()
            raise LocalModelUnavailable("LOCAL_AUDAR_TIMEOUT") from exc
        elapsed = (time.perf_counter() - started) * 1000
        if return_code != 0:
            raise LocalModelUnavailable(f"LOCAL_AUDAR_INFERENCE_FAILED:exit={return_code}")
        return {
            "text": self._text_from_cli(raw), "segments": [], "language": None, "no_speech_probability": None,
            "raw_output": raw, "runtime": "llama.cpp mtmd", "latency_ms": elapsed, "total_latency_ms": elapsed,
            "inference_latency_ms": elapsed, "model_load_ms": None, "cold_start": None,
            "provider_diagnostics": {"return_code": return_code, "stderr": _stderr[-2000:], "runtime_path": str(entry["runtime_path"])},
            "resource_measurement": {"runtime": "llama.cpp mtmd", "execution_mode": "cpu", "artifact_bytes": sum(int(item.get("bytes", 0)) for item in status.get("artifacts", [])), "peak_ram_or_vram": None},
            "signals": {"average_log_probability": {"available": False, "value": None}, "no_speech_probability": {"available": False, "value": None}, "compression_ratio": {"available": False, "value": None}, "segment_stability": {"available": False, "value": None}, "alternative_decoding": {"available": False, "value": None}},
        }


class LlamaCppAdapter:
    """Direct in-process GGUF adapter. It has no network endpoint or provider fallback."""

    provider = "llama_cpp_local"

    def __init__(self, registry: LocalArtifactRegistry) -> None:
        self.registry = registry
        self._model: Any | None = None
        self._loaded_key: str | None = None
        self._load_ms: float | None = None

    def _entry(self, binding: RoleBinding | None = None) -> dict[str, Any] | None:
        entries = [entry for entry in self.registry.entries() if entry.get("provider") == self.provider]
        if binding:
            return self.registry.entry(binding.model_id, self.provider)
        return entries[0] if entries else None

    def status(self, binding: RoleBinding | None = None) -> dict[str, Any]:
        entry = self._entry(binding)
        if not entry:
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: verified local GGUF manifest entry is required"}
        if importlib.util.find_spec("llama_cpp") is None:
            return {"available": False, "reason": "UNAVAILABLE_LOCAL_MODEL: llama-cpp-python runtime is not installed"}
        valid, reason, artifacts = self.registry.verify(entry)
        return {"available": valid, "reason": None if valid else f"UNAVAILABLE_LOCAL_MODEL: {reason}", "artifacts": artifacts if valid else []}

    def discover(self) -> list[RoleBinding]:
        bindings: list[RoleBinding] = []
        for entry in [entry for entry in self.registry.entries() if entry.get("provider") == self.provider]:
            status = self.status(RoleBinding(
                id="placeholder", provider=self.provider, model_id=str(entry.get("id")), role=Role.SUMMARIZE,
                prompt_version="", schema_version="", execution_mode=ExecutionMode.LOCAL, capability_provenance=CapabilityProvenance.UNKNOWN,
            ))
            roles = entry.get("roles", ["summarize", "actionize", "function_call"])
            for role_value in roles:
                if role_value not in {"summarize", "actionize", "function_call", "verify"}:
                    continue
                role = Role(role_value)
                bindings.append(RoleBinding(
                    id=f"{self.provider}:{entry['id']}:{role.value}", provider=self.provider, model_id=str(entry["id"]),
                    revision_or_digest=f"{entry.get('revision') or entry.get('digest') or 'unknown'};{entry.get('artifacts', [{}])[0].get('sha256', 'unknown')}", role=role,
                    prompt_version="qwen-json-v1", schema_version="sta-v2",
                    generation={"temperature": 0, "seed": 7, "max_tokens": 500, "runtime": "llama-cpp-python", "quantization": entry.get("quantization")},
                    execution_mode=ExecutionMode.LOCAL,
                    capability_provenance=CapabilityProvenance.VERIFIED_LOCAL if status["available"] else CapabilityProvenance.UNKNOWN,
                    capabilities=[role.value, "structured_json", "tool_selection"] if status["available"] else [],
                    available=status["available"], unavailable_reason=status["reason"], tool_mode="STRUCTURED_TOOL_EMULATION" if role == Role.FUNCTION_CALL else "NONE",
                    artifact_hashes=[str(item.get("sha256")) for item in status.get("artifacts", []) if item.get("sha256")],
                ))
        return bindings

    def _load(self, entry: dict[str, Any]) -> bool:
        key = str(entry["id"])
        if self._model is not None and self._loaded_key == key:
            return False
        self._model, self._loaded_key = None, None
        started = time.perf_counter()
        try:
            from llama_cpp import Llama  # type: ignore[import-not-found]
            artifact = entry["artifacts"][0]
            self._model = Llama(
                model_path=str(artifact["path"]), n_ctx=int(entry.get("context_window", 4096)),
                n_threads=max(1, min(os.cpu_count() or 4, 8)), n_gpu_layers=0, seed=7, verbose=False,
            )
            self._loaded_key = key
            self._load_ms = (time.perf_counter() - started) * 1000
            return True
        except Exception as exc:
            self._model, self._loaded_key = None, None
            raise LocalModelUnavailable(f"LOCAL_GGUF_LOAD_FAILED:{type(exc).__name__}") from exc

    def load(self, binding: RoleBinding) -> dict[str, Any]:
        """Load exactly the verified binding and return load evidence."""
        status = self.status(binding)
        if not status["available"]:
            raise LocalModelUnavailable(status["reason"])
        assert_dispatch_allowed(self.provider, artifact_verified=True)
        entry = self._entry(binding)
        assert entry is not None
        cold_start = self._load(entry)
        return {"loaded": True, "cold_start": cold_start, "model_load_ms": self._load_ms, "model_id": binding.model_id, "revision_or_digest": binding.revision_or_digest}

    def unload(self) -> None:
        """Release the in-process model so the next call has an explicit cold start."""
        self._model, self._loaded_key, self._load_ms = None, None, None

    @staticmethod
    def _run_with_controls(call: Any, *, timeout_seconds: float | None, cancel_event: threading.Event | None) -> Any:
        if cancel_event and cancel_event.is_set():
            raise LocalModelUnavailable("LOCAL_GGUF_CANCELLED")
        if timeout_seconds is None and cancel_event is None:
            return call()
        from concurrent.futures import ThreadPoolExecutor, TimeoutError

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="saudi-sta-llama")
        future = executor.submit(call)
        deadline = time.monotonic() + timeout_seconds if timeout_seconds is not None else None
        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    raise LocalModelUnavailable("LOCAL_GGUF_CANCELLED")
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                if remaining == 0.0:
                    raise LocalModelUnavailable("LOCAL_GGUF_TIMEOUT")
                try:
                    return future.result(timeout=min(0.1, remaining) if remaining is not None else 0.1)
                except TimeoutError:
                    continue
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _metrics(self, binding: RoleBinding, status: dict[str, Any], *, cold_start: bool, elapsed: float, usage: dict[str, Any], request_type: str, context: dict[str, Any] | None) -> dict[str, Any]:
        completion_tokens = usage.get("completion_tokens")
        return {
            "runtime": "llama-cpp-python", "execution_mode": "cpu", "request_type": request_type,
            "cold_start": cold_start, "model_load_ms": self._load_ms if cold_start else 0.0,
            "inference_latency_ms": elapsed, "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": completion_tokens,
            "tokens_per_second": (completion_tokens / (elapsed / 1000)) if isinstance(completion_tokens, int) and elapsed else None,
            "artifact_bytes": sum(item["bytes"] for item in status.get("artifacts", [])),
            "peak_ram_or_vram": None, "context": context or {},
            "context_window": binding.generation.get("context_window"),
            "reasoning": binding.generation.get("reasoning") or binding.generation.get("reasoning_effort"),
            "model_id": binding.model_id, "revision_or_digest": binding.revision_or_digest,
            "schema_version": binding.schema_version, "prompt_version": binding.prompt_version,
            "artifact_hashes": list(getattr(binding, "artifact_hashes", []) or []),
            "tool_mode": binding.tool_mode,
        }

    def invoke(
        self,
        binding: RoleBinding,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
        cancel_event: threading.Event | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = self.status(binding)
        if not status["available"]:
            raise LocalModelUnavailable(status["reason"])
        assert_dispatch_allowed(self.provider, artifact_verified=True)
        entry = self._entry(binding)
        assert entry is not None
        cold_start = self._load(entry)
        started = time.perf_counter()
        try:
            request: dict[str, Any] = {
                "messages": messages, "temperature": float(binding.generation.get("temperature", 0)),
                "max_tokens": int(binding.generation.get("max_tokens", 500)),
            }
            if binding.tool_mode in {"NATIVE", "NATIVE_TOOL_CALL"} and tools:
                request["tools"] = tools
                request["tool_choice"] = "auto"
            else:
                # Structured emulation is explicit and retained as a different
                # mode from native tool calls; the model is schema-constrained
                # where the selected llama.cpp build supports it.
                request["response_format"] = {"type": "json_object", "schema": json_schema}
            reasoning_format = binding.generation.get("reasoning_format")
            if reasoning_format:
                try:
                    if "reasoning_format" in inspect.signature(self._model.create_chat_completion).parameters:
                        request["reasoning_format"] = reasoning_format
                except (TypeError, ValueError):
                    pass
            response = self._run_with_controls(lambda: self._model.create_chat_completion(**request), timeout_seconds=timeout_seconds, cancel_event=cancel_event)
            content = response["choices"][0]["message"].get("content") or ""
            tool_calls = response["choices"][0]["message"].get("tool_calls", []) or []
            usage = response.get("usage", {})
        except LocalModelUnavailable:
            raise
        except Exception as exc:
            raise LocalModelUnavailable(f"LOCAL_GGUF_INFERENCE_FAILED:{type(exc).__name__}") from exc
        elapsed = (time.perf_counter() - started) * 1000
        return {
            "content": content, "tool_calls": tool_calls,
            "runtime_metrics": self._metrics(binding, status, cold_start=cold_start, elapsed=elapsed, usage=usage, request_type="chat_completion", context=context),
        }

    def complete(
        self,
        binding: RoleBinding,
        prompt: str,
        *,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
        cancel_event: threading.Event | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Raw completion surface for runtimes that do not use chat templates."""
        status = self.status(binding)
        if not status["available"]:
            raise LocalModelUnavailable(status["reason"])
        assert_dispatch_allowed(self.provider, artifact_verified=True)
        entry = self._entry(binding)
        assert entry is not None
        cold_start = self._load(entry)
        started = time.perf_counter()
        try:
            response = self._run_with_controls(
                lambda: self._model.create_completion(prompt=prompt, temperature=float(binding.generation.get("temperature", 0)), max_tokens=int(max_tokens or binding.generation.get("max_tokens", 500))),
                timeout_seconds=timeout_seconds, cancel_event=cancel_event,
            )
        except LocalModelUnavailable:
            raise
        except Exception as exc:
            raise LocalModelUnavailable(f"LOCAL_GGUF_COMPLETION_FAILED:{type(exc).__name__}") from exc
        elapsed = (time.perf_counter() - started) * 1000
        usage = response.get("usage", {})
        return {
            "content": response.get("choices", [{}])[0].get("text", ""),
            "runtime_metrics": self._metrics(binding, status, cold_start=cold_start, elapsed=elapsed, usage=usage, request_type="completion", context=context),
        }


def provider_matrix(ollama: OllamaAdapter, faster_speech: FasterWhisperAdapter, whisper: TransformersWhisperAdapter, audar: AudarMtmdAdapter, text: LlamaCppAdapter) -> list[dict[str, Any]]:
    return [
        {"provider": "DEMO_RULES", "roles": ["summarize", "actionize", "function_call"], "state": "IMPLEMENTED", "evidence": "deterministic reference path, not ML"},
        {"provider": "Ollama", "roles": ["summarize", "actionize", "function_call"], "state": "IMPLEMENTED_IF_VERIFIED_LOCAL", "checks": ollama.checks, "sources": [OFFICIAL_SOURCES["ollama_tags"], OFFICIAL_SOURCES["ollama_chat"], OFFICIAL_SOURCES["ollama_locality"]]},
        {"provider": "faster-whisper", "roles": ["transcribe"], "state": "IMPLEMENTED_IF_EXISTING_LOCAL_RUNTIME", "status": faster_speech.status(), "sources": [OFFICIAL_SOURCES["faster_whisper"]]},
        {"provider": "Transformers Whisper", "roles": ["transcribe"], "state": "IMPLEMENTED_IF_VERIFIED_LOCAL", "status": whisper.status(), "sources": ["https://huggingface.co/openai/whisper-large-v3"]},
        {"provider": "Audar local mtmd candidates", "roles": ["transcribe"], "state": "IMPLEMENTED_IF_VERIFIED_LOCAL", "bindings": [binding.model_dump(mode="json") for binding in audar.discover()], "evidence": "REAL_LOCAL_MODEL; Q4 is NOT_REFERENCE_PRECISION", "sources": ["https://huggingface.co/audarai/Audar-ASR-V1-Turbo", "https://huggingface.co/audarai/Audar-ASR-V1-Flash"]},
        {"provider": "llama.cpp", "roles": ["summarize", "actionize", "function_call"], "state": "IMPLEMENTED_IF_VERIFIED_LOCAL", "status": text.status(), "sources": ["https://github.com/abetlen/llama-cpp-python"]},
        {"provider": "HUMAIN Voice", "roles": ["transcribe", "synthesize"], "state": "DISABLED_ZERO_SPEND_LOCAL", "preferred_provider": True, "currently_executable_provider": False, "sources": [OFFICIAL_SOURCES["humain_voice"]]},
        {"provider": "OpenAI", "roles": ["transcribe", "summarize", "actionize", "function_call"], "state": "DISABLED_ZERO_SPEND_LOCAL", "sources": [OFFICIAL_SOURCES["openai_function_calling"], OFFICIAL_SOURCES["openai_audio"]]},
    ]
