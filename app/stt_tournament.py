"""Measured, stage-only local transcription comparisons.

This module deliberately keeps speech evidence separate from DEMO_RULES and
from complete STA route reports.  It never chooses a universal winner when no
human reference exists.
"""

from __future__ import annotations

import difflib
import time
from pathlib import Path
from typing import Any, Callable


def _levenshtein(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, item in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (item != other)))
        previous = current
    return previous[-1]


def _wer(reference: str, hypothesis: str) -> float | None:
    words = reference.split()
    return _levenshtein(words, hypothesis.split()) / len(words) if words else None


def _cer(reference: str, hypothesis: str) -> float | None:
    chars = list(reference.replace(" ", ""))
    return _levenshtein(chars, list(hypothesis.replace(" ", ""))) / len(chars) if chars else None


def _kind(token: str) -> str:
    if any(char.isdigit() for char in token) or token in {"صباح", "مساء", "ونص", "ثلاثة", "خمسة", "عشرين"}:
        return "number"
    if any("a" <= char.lower() <= "z" for char in token):
        return "code_switch"
    if token in {"لا", "مو", "ما", "ليس", "بس"}:
        return "negation"
    return "word"


def disagreement_regions(outputs: list[dict[str, Any]], human_reference: str | None = None) -> dict[str, Any]:
    texts = {str(item["candidate_id"]): str(item.get("text", "")) for item in outputs if item.get("status") == "READY"}
    regions: list[dict[str, Any]] = []
    ids = list(texts)
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1:]:
            left, right = texts[left_id].split(), texts[right_id].split()
            matcher = difflib.SequenceMatcher(a=left, b=right)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal":
                    continue
                left_tokens, right_tokens = left[i1:i2], right[j1:j2]
                combined = left_tokens + right_tokens
                kinds = sorted({_kind(token) for token in combined})
                regions.append({"left_candidate": left_id, "right_candidate": right_id, "operation": tag,
                                "left_tokens": left_tokens, "right_tokens": right_tokens,
                                "kinds": kinds, "number_disagreement": "number" in kinds,
                                "code_switch_disagreement": "code_switch" in kinds,
                                "negation_disagreement": "negation" in kinds,
                                "human_reference_region": human_reference is not None})
    return {"candidate_count": len(texts), "regions": regions, "human_reference_authoritative": human_reference is not None,
             "majority_vote_used": False}


def _speech_error_taxonomy(reference: str, hypothesis: str) -> list[str]:
    """Label observable reference differences without turning them into truth."""
    reference_tokens, hypothesis_tokens = reference.split(), hypothesis.split()
    labels: set[str] = set()
    matcher = difflib.SequenceMatcher(a=reference_tokens, b=hypothesis_tokens)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ref = reference_tokens[i1:i2]
        hyp = hypothesis_tokens[j1:j2]
        kinds = {_kind(token) for token in ref + hyp}
        if tag == "replace":
            labels.add("SUBSTITUTION")
        elif tag == "delete":
            labels.add("DELETION")
        elif tag == "insert":
            labels.add("INSERTION")
        if "number" in kinds:
            labels.add("NUMBER_ERROR")
        if "code_switch" in kinds:
            labels.add("CODE_SWITCH_ERROR")
        if "negation" in kinds:
            labels.add("NEGATION_ERROR")
    return sorted(labels)


def run_stt_tournament(
    audio_path: Path,
    bindings: list[Any],
    transcribe: Callable[[Any, Path], dict[str, Any]],
    *,
    human_reference: str | None = None,
    mode: str = "Performance",
    manual_binding_id: str | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for binding in bindings:
        started = time.perf_counter()
        base = {"candidate_id": binding.id, "model_id": binding.model_id, "provider": binding.provider,
                "revision_or_digest": binding.revision_or_digest, "generation": binding.generation,
                "quantization": binding.generation.get("precision"), "runtime": binding.generation.get("runtime"),
                "evidence_type": "REAL_LOCAL_MODEL", "status": "FAILED", "transcript": None,
                "latency_ms": None, "cold_start": None, "model_load_ms": None, "error": None}
        try:
            if not binding.available:
                raise RuntimeError(binding.unavailable_reason or "UNAVAILABLE_LOCAL_MODEL")
            result = transcribe(binding, audio_path)
            base.update({"status": "READY", "transcript": result.get("text", ""),
                         "latency_ms": result.get("latency_ms", (time.perf_counter() - started) * 1000),
                         "cold_start": result.get("cold_start"), "model_load_ms": result.get("model_load_ms"),
                         "segments": result.get("segments", []), "signals": result.get("signals", {}),
                         "resource_measurement": result.get("resource_measurement", {}), "raw_output": result.get("raw_output")})
            if human_reference is not None:
                base.update({"wer": _wer(human_reference, base["transcript"]), "cer": _cer(human_reference, base["transcript"]),
                              "speech_errors": _speech_error_taxonomy(human_reference, base["transcript"])})
            else:
                base.update({"wer": None, "cer": None, "speech_errors": []})
        except Exception as exc:
            base["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
            base["latency_ms"] = (time.perf_counter() - started) * 1000
            base.update({"wer": None, "cer": None, "speech_errors": ["MODEL_FAILURE"]})
        candidates.append(base)

    ready = [item for item in candidates if item["status"] == "READY"]
    if mode == "Manual":
        selected = next((item for item in ready if item["candidate_id"] == manual_binding_id), None)
        selection = {"outcome": "MANUAL", "recommendation": selected["candidate_id"] if selected else None,
                     "reason": "The selected STT binding runs exactly as chosen; no optimizer override."}
    elif human_reference is None:
        selection = {"outcome": "INSUFFICIENT_HUMAN_EVIDENCE", "recommendation": None,
                     "reason": "Measured outputs are retained, but no human reference authorizes a quality winner."}
    elif not ready:
        selection = {"outcome": "NO_ELIGIBLE_CANDIDATE", "recommendation": None}
    elif mode == "Speed":
        winner = min(ready, key=lambda item: item["latency_ms"] if item["latency_ms"] is not None else float("inf"))
        selection = {"outcome": "RECOMMENDED", "recommendation": winner["candidate_id"], "reason": "Lowest measured complete local STT latency."}
    else:
        winner = min(ready, key=lambda item: (item["wer"] if item["wer"] is not None else float("inf"), item["cer"] if item["cer"] is not None else float("inf")))
        selection = {"outcome": "RECOMMENDED", "recommendation": winner["candidate_id"], "reason": "Lowest human-referenced WER, then CER."}
    ready_wer = [item["wer"] for item in ready if item.get("wer") is not None]
    ready_cer = [item["cer"] for item in ready if item.get("cer") is not None]
    ready_latency = [item["latency_ms"] for item in ready if item.get("latency_ms") is not None]
    error_counts: dict[str, int] = {}
    for item in candidates:
        for error in item.get("speech_errors", []):
            error_counts[error] = error_counts.get(error, 0) + 1
    return {"evidence_type": "HUMAN_REVIEWED" if human_reference is not None else "REAL_LOCAL_MODEL",
            "mode": mode, "audio": str(audio_path), "human_reference": human_reference,
            "candidates": candidates, "disagreement": disagreement_regions(candidates, human_reference),
            "selection": selection, "remote_calls": 0, "monetary_api_cost": 0,
            "aggregates": {
                "ready_candidates": len(ready), "mean_wer": sum(ready_wer) / len(ready_wer) if ready_wer else None,
                "mean_cer": sum(ready_cer) / len(ready_cer) if ready_cer else None,
                "mean_latency_ms": sum(ready_latency) / len(ready_latency) if ready_latency else None,
                "speech_error_counts": error_counts, "human_reference_authoritative": human_reference is not None,
            },
            "confidence_diagnostics": {"calibrated_correctness": None, "native_signals_only": True}}
