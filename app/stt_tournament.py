"""Measured, stage-only local transcription comparisons.

This module deliberately keeps speech evidence separate from DEMO_RULES and
from complete STA route reports.  It never chooses a universal winner when no
human reference exists.
"""

from __future__ import annotations

import difflib
import hashlib
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


def _edit_counts(reference_tokens: list[str], hypothesis_tokens: list[str]) -> dict[str, int]:
    """Return deterministic Levenshtein edit counts for an evaluation report."""
    rows = len(reference_tokens) + 1
    cols = len(hypothesis_tokens) + 1
    distance: list[list[tuple[int, int, int, int]]] = [[(0, 0, 0, 0) for _ in range(cols)] for _ in range(rows)]
    for i in range(1, rows):
        distance[i][0] = (i, 0, i, 0)
    for j in range(1, cols):
        distance[0][j] = (j, 0, 0, j)
    for i, reference_token in enumerate(reference_tokens, 1):
        for j, hypothesis_token in enumerate(hypothesis_tokens, 1):
            if reference_token == hypothesis_token:
                distance[i][j] = distance[i - 1][j - 1]
                continue
            substitution = distance[i - 1][j - 1]
            deletion = distance[i - 1][j]
            insertion = distance[i][j - 1]
            choices = [
                (substitution[0] + 1, substitution[1] + 1, substitution[2], substitution[3]),
                (deletion[0] + 1, deletion[1], deletion[2] + 1, deletion[3]),
                (insertion[0] + 1, insertion[1], insertion[2], insertion[3] + 1),
            ]
            # Prefer substitutions, then deletions, then insertions on ties so
            # repeated reports remain stable across Python versions.
            distance[i][j] = min(choices, key=lambda item: (item[0], -item[1], -item[2], -item[3]))
    _, substitutions, deletions, insertions = distance[-1][-1]
    return {"substitutions": substitutions, "deletions": deletions, "insertions": insertions}


def _kind(token: str) -> str:
    if any(char.isdigit() for char in token) or token in {"صباح", "مساء", "ونص", "ثلاثة", "خمسة", "عشرين"}:
        return "number"
    if any("a" <= char.lower() <= "z" for char in token):
        return "code_switch"
    if token in {"لا", "مو", "ما", "ليس", "بس"}:
        return "negation"
    return "word"


def _is_proper_name(token: str) -> bool:
    return token in {"محمد", "أحمد", "خالد", "سارة", "Sarah", "Ahmed", "Mohammed", "Khalid"}


def _is_correction_marker(token: str) -> bool:
    return token in {"لا", "بدل", "خلها", "خليها", "صحح", "التصحيح"}


def _metric_text(text: str) -> str:
    """Normalize whitespace only; preserve Arabic, digits, negation, and code switching."""
    return " ".join(str(text).strip().split())


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
                if any(_is_proper_name(token) for token in combined):
                    kinds.append("proper_name")
                if any(_is_correction_marker(token) for token in combined):
                    kinds.append("correction")
                kinds = sorted(set(kinds))
                regions.append({"left_candidate": left_id, "right_candidate": right_id, "operation": tag,
                                "left_tokens": left_tokens, "right_tokens": right_tokens,
                                "kinds": kinds, "number_disagreement": "number" in kinds,
                                "code_switch_disagreement": "code_switch" in kinds,
                                "negation_disagreement": "negation" in kinds,
                                "proper_name_disagreement": "proper_name" in kinds,
                                "correction_disagreement": "correction" in kinds,
                                "human_reference_region": human_reference is not None})
    counts = {"word_span": 0, "number": 0, "proper_name": 0, "negation": 0, "correction": 0, "code_switch": 0}
    for region in regions:
        counts["word_span"] += 1
        for category, kind in (("number", "number_disagreement"), ("proper_name", "proper_name_disagreement"),
                               ("negation", "negation_disagreement"), ("correction", "correction_disagreement"),
                               ("code_switch", "code_switch_disagreement")):
            counts[category] += int(region[kind])
    return {"candidate_count": len(texts), "regions": regions, "counts": counts,
            "human_reference_authoritative": human_reference is not None, "majority_vote_used": False,
            "calibrated_correctness": None}


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
        if any(_is_proper_name(token) for token in ref + hyp):
            kinds.add("proper_name")
        if any(_is_correction_marker(token) for token in ref + hyp):
            kinds.add("correction")
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
        if "proper_name" in kinds:
            labels.add("NAME_ERROR")
        if "correction" in kinds:
            labels.add("CORRECTION_ERROR")
    return sorted(labels)


def _critical_transcription_errors(reference: str, hypothesis: str) -> list[dict[str, Any]]:
    """Keep critical semantic categories separate from aggregate WER/CER."""
    reference_tokens, hypothesis_tokens = reference.split(), hypothesis.split()
    errors: list[dict[str, Any]] = []
    matcher = difflib.SequenceMatcher(a=reference_tokens, b=hypothesis_tokens)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ref = reference_tokens[i1:i2]
        hyp = hypothesis_tokens[j1:j2]
        categories: set[str] = set()
        combined = ref + hyp
        if any(_kind(token) == "number" for token in combined):
            categories.add("number")
        if any(_is_proper_name(token) for token in combined):
            categories.add("proper_name")
        if any(_kind(token) == "negation" for token in combined):
            categories.add("negation")
        if any(_is_correction_marker(token) for token in combined):
            categories.add("correction")
        if any(_kind(token) == "code_switch" for token in combined):
            categories.add("code_switch")
        for category in sorted(categories):
            errors.append({"category": category, "operation": tag, "reference_tokens": ref, "hypothesis_tokens": hyp})
    return errors


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_stt_tournament(
    audio_path: Path,
    bindings: list[Any],
    transcribe: Callable[[Any, Path], dict[str, Any]],
    *,
    human_reference: str | None = None,
    mode: str = "Performance",
    manual_binding_id: str | None = None,
) -> dict[str, Any]:
    normalized_reference = _metric_text(human_reference) if human_reference is not None else None
    candidates: list[dict[str, Any]] = []
    for binding in bindings:
        started = time.perf_counter()
        base = {"candidate_id": binding.id, "model_id": binding.model_id, "provider": binding.provider,
                "revision_or_digest": binding.revision_or_digest, "generation": binding.generation,
                "quantization": binding.generation.get("precision"), "runtime": binding.generation.get("runtime"),
                "model_hash": (getattr(binding, "artifact_hashes", None) or [binding.revision_or_digest])[0],
                "artifact_hashes": list(getattr(binding, "artifact_hashes", None) or []),
                "evidence_type": "REAL_LOCAL_MODEL", "status": "FAILED", "transcript": None,
                "latency_ms": None, "total_latency_ms": None, "inference_latency_ms": None,
                "cold_start": None, "model_load_ms": None, "error": None, "diagnostics": {}}
        try:
            if not binding.available:
                raise RuntimeError(binding.unavailable_reason or "UNAVAILABLE_LOCAL_MODEL")
            result = transcribe(binding, audio_path)
            original_transcript = str(result.get("text", ""))
            total_latency = result.get("total_latency_ms", result.get("latency_ms", (time.perf_counter() - started) * 1000))
            base.update({"status": "READY", "transcript": original_transcript,
                         "transcript_original": original_transcript,
                         "transcript_normalized": _metric_text(original_transcript),
                         "latency_ms": total_latency, "total_latency_ms": total_latency,
                         "inference_latency_ms": result.get("inference_latency_ms"),
                         "cold_start": result.get("cold_start"), "model_load_ms": result.get("model_load_ms"),
                         "segments": result.get("segments", []), "signals": result.get("signals", {}),
                         "resource_measurement": result.get("resource_measurement", {}), "raw_output": result.get("raw_output"),
                         "diagnostics": result.get("provider_diagnostics", result.get("diagnostics", {}))})
            if human_reference is not None:
                base.update({"wer": _wer(normalized_reference or "", base["transcript_normalized"]), "cer": _cer(normalized_reference or "", base["transcript_normalized"]),
                              "word_edit_counts": _edit_counts((normalized_reference or "").split(), base["transcript_normalized"].split()),
                              "char_edit_counts": _edit_counts(list((normalized_reference or "").replace(" ", "")), list(base["transcript_normalized"].replace(" ", ""))),
                              "speech_errors": _speech_error_taxonomy(normalized_reference or "", base["transcript_normalized"]),
                              "critical_errors": _critical_transcription_errors(normalized_reference or "", base["transcript_normalized"])})
            else:
                base.update({"wer": None, "cer": None, "word_edit_counts": None, "char_edit_counts": None,
                             "speech_errors": [], "critical_errors": []})
        except Exception as exc:
            base["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
            base["latency_ms"] = (time.perf_counter() - started) * 1000
            base["total_latency_ms"] = base["latency_ms"]
            base["failure_class"] = "TIMEOUT" if isinstance(exc, TimeoutError) else "RUNTIME_FAILURE"
            base.update({"wer": None, "cer": None, "word_edit_counts": None, "char_edit_counts": None,
                         "speech_errors": ["MODEL_FAILURE"], "critical_errors": []})
        candidates.append(base)

    ready = [item for item in candidates if item["status"] == "READY"]
    if mode == "Manual":
        selected = next((item for item in ready if item["candidate_id"] == manual_binding_id), None)
        selection = {"outcome": "MANUAL", "recommendation": selected["candidate_id"] if selected else None,
                     "reason": "The selected STT binding runs exactly as chosen; no optimizer override."}
    elif mode == "Cost":
        secondary = min(ready, key=lambda item: item["latency_ms"] if item["latency_ms"] is not None else float("inf")) if ready else None
        selection = {"outcome": "MONETARY_TIE", "recommendation": None, "secondary_recommendation": secondary["candidate_id"] if secondary else None,
                     "reason": "All selected local models have API monetary cost 0; latency is reported only as a documented secondary criterion."}
    elif mode == "Speed" and human_reference is None:
        winner = min(ready, key=lambda item: item["latency_ms"] if item["latency_ms"] is not None else float("inf")) if ready else None
        selection = {"outcome": "RECOMMENDED" if winner else "NO_ELIGIBLE_CANDIDATE", "recommendation": winner["candidate_id"] if winner else None,
                     "reason": "Lowest measured complete local STT latency; this is a speed result, not a quality claim."}
    elif human_reference is None:
        selection = {"outcome": "NO_COMPARABLE_HUMAN_EVIDENCE", "recommendation": None,
                     "quality_ranking": "INSUFFICIENT_HUMAN_EVIDENCE",
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
            "mode": mode, "audio": str(audio_path),
            "audio_identity": {"path": str(audio_path), "size_bytes": audio_path.stat().st_size if audio_path.is_file() else None,
                               "sha256": _sha256(audio_path)},
            "human_reference": human_reference, "human_reference_original": human_reference,
            "human_reference_normalized": normalized_reference,
            "candidates": candidates, "disagreement": disagreement_regions(candidates, human_reference),
            "selection": selection, "remote_calls": 0, "monetary_api_cost": 0,
            "aggregates": {
                "ready_candidates": len(ready), "mean_wer": sum(ready_wer) / len(ready_wer) if ready_wer else None,
                "mean_cer": sum(ready_cer) / len(ready_cer) if ready_cer else None,
                "mean_latency_ms": sum(ready_latency) / len(ready_latency) if ready_latency else None,
                "speech_error_counts": error_counts,
                "critical_error_counts": {category: sum(1 for item in candidates for error in item.get("critical_errors", []) if error["category"] == category)
                                          for category in ("number", "proper_name", "negation", "correction", "code_switch")},
                "human_reference_authoritative": human_reference is not None,
            },
            "confidence_diagnostics": {"calibrated_correctness": None, "native_signals_only": True}}
