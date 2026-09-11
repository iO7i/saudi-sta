from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
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
        default_path = Path("D:/saudi-sta-models/saudi-sta-local-models.json")
        self.manifest_path = configured or (str(default_path) if default_path.is_file() else None)
        self._hash_cache: dict[str, tuple[int, int, str]] = {}

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    def entries(self) -> list[dict[str, Any]]:
        if not self.manifest_path:
            return []
        path = Path(self.manifest_path)
        if not path.is_file():
            return []
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        entries = body.get("models", []) if isinstance(body, dict) else []
        return [entry for entry in entries if isinstance(entry, dict)]

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
                    tool_mode="NATIVE" if bool(entry.get("native_tools", False)) and role == "function_call" else "JSON_EMULATION",
                ))
            self.checks.append({"check": "artifact", "model": name, "result": "verified locally"})
        return result

    def invoke(self, binding: RoleBinding, messages: list[dict[str, str]], *, json_schema: dict[str, Any], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
            result = self._pipeline(
                {"array": samples, "sampling_rate": sampling_rate},
                generate_kwargs={"language": "arabic", "task": "transcribe"}, return_timestamps=True,
            )
        except Exception as exc:
            raise LocalModelUnavailable(f"LOCAL_WHISPER_INFERENCE_FAILED:{type(exc).__name__}") from exc
        segments = []
        for chunk in result.get("chunks", []):
            timestamp = chunk.get("timestamp") or (None, None)
            segments.append({"start": timestamp[0], "end": timestamp[1], "text": str(chunk.get("text", "")).strip()})
        return {
            "text": str(result.get("text", "")).strip(), "segments": segments, "language": "ar",
            "runtime": "transformers+cpu", "cold_start": cold_start, "model_load_ms": self._load_ms if cold_start else 0.0,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "resource_measurement": {"runtime": "transformers+cpu", "execution_mode": "cpu", "artifact_bytes": sum(item["bytes"] for item in status.get("artifacts", [])), "peak_ram_or_vram": None},
            "signals": {
                "average_log_probability": {"available": False, "value": None},
                "no_speech_probability": {"available": False, "value": None},
                "compression_ratio": {"available": False, "value": None},
                "segment_stability": {"available": False, "value": None},
                "alternative_decoding": {"available": False, "value": None},
            },
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
                if role_value not in {"summarize", "actionize", "function_call"}:
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
                    available=status["available"], unavailable_reason=status["reason"], tool_mode="JSON_EMULATION" if role == Role.FUNCTION_CALL else "NONE",
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

    def invoke(self, binding: RoleBinding, messages: list[dict[str, str]], *, json_schema: dict[str, Any], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        status = self.status(binding)
        if not status["available"]:
            raise LocalModelUnavailable(status["reason"])
        assert_dispatch_allowed(self.provider, artifact_verified=True)
        entry = self._entry(binding)
        assert entry is not None
        cold_start = self._load(entry)
        started = time.perf_counter()
        try:
            response = self._model.create_chat_completion(
                messages=messages, temperature=0, max_tokens=int(binding.generation.get("max_tokens", 500)),
                response_format={"type": "json_object"},
            )
            content = response["choices"][0]["message"].get("content") or ""
            usage = response.get("usage", {})
        except Exception as exc:
            raise LocalModelUnavailable(f"LOCAL_GGUF_INFERENCE_FAILED:{type(exc).__name__}") from exc
        elapsed = (time.perf_counter() - started) * 1000
        completion_tokens = usage.get("completion_tokens")
        return {
            "content": content, "tool_calls": [],
            "runtime_metrics": {
                "runtime": "llama-cpp-python", "execution_mode": "cpu", "cold_start": cold_start, "model_load_ms": self._load_ms if cold_start else 0.0,
                "inference_latency_ms": elapsed, "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": completion_tokens,
                "tokens_per_second": (completion_tokens / (elapsed / 1000)) if isinstance(completion_tokens, int) and elapsed else None,
                "artifact_bytes": sum(item["bytes"] for item in status.get("artifacts", [])),
                "peak_ram_or_vram": None,
            },
        }


def provider_matrix(ollama: OllamaAdapter, faster_speech: FasterWhisperAdapter, whisper: TransformersWhisperAdapter, text: LlamaCppAdapter) -> list[dict[str, Any]]:
    return [
        {"provider": "DEMO_RULES", "roles": ["summarize", "actionize", "function_call"], "state": "IMPLEMENTED", "evidence": "deterministic reference path, not ML"},
        {"provider": "Ollama", "roles": ["summarize", "actionize", "function_call"], "state": "IMPLEMENTED_IF_VERIFIED_LOCAL", "checks": ollama.checks, "sources": [OFFICIAL_SOURCES["ollama_tags"], OFFICIAL_SOURCES["ollama_chat"], OFFICIAL_SOURCES["ollama_locality"]]},
        {"provider": "faster-whisper", "roles": ["transcribe"], "state": "IMPLEMENTED_IF_EXISTING_LOCAL_RUNTIME", "status": faster_speech.status(), "sources": [OFFICIAL_SOURCES["faster_whisper"]]},
        {"provider": "Transformers Whisper", "roles": ["transcribe"], "state": "IMPLEMENTED_IF_VERIFIED_LOCAL", "status": whisper.status(), "sources": ["https://huggingface.co/openai/whisper-large-v3"]},
        {"provider": "llama.cpp", "roles": ["summarize", "actionize", "function_call"], "state": "IMPLEMENTED_IF_VERIFIED_LOCAL", "status": text.status(), "sources": ["https://github.com/abetlen/llama-cpp-python"]},
        {"provider": "HUMAIN Voice", "roles": ["transcribe", "synthesize"], "state": "DISABLED_ZERO_SPEND_LOCAL", "preferred_provider": True, "currently_executable_provider": False, "sources": [OFFICIAL_SOURCES["humain_voice"]]},
        {"provider": "OpenAI", "roles": ["transcribe", "summarize", "actionize", "function_call"], "state": "DISABLED_ZERO_SPEND_LOCAL", "sources": [OFFICIAL_SOURCES["openai_function_calling"], OFFICIAL_SOURCES["openai_audio"]]},
    ]
