from __future__ import annotations

import json
import platform
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .engine import Engine, apply_to_sandbox, recipe_hash
from .schemas import Recipe, RunStatus, ToolProposal, TournamentStart


SPEECH_ERROR_LABELS = {"SUBSTITUTION", "DELETION", "INSERTION", "NUMBER_ERROR", "NAME_ERROR", "CODE_SWITCH_ERROR", "NEGATION_ERROR", "CORRECTION_ERROR"}
ACTION_ERROR_LABELS = {"WRONG_INTENT", "WRONG_TOOL", "WRONG_ARGUMENT", "MISSING_ARGUMENT", "INVENTED_ARGUMENT", "IGNORED_CORRECTION", "IGNORED_NEGATION", "UNNECESSARY_CLARIFICATION", "MISSED_CLARIFICATION"}


def _fixture_cases() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parent.parent / "fixtures" / "authored_smoke.json"
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def _matches_expected(proposal: dict[str, Any], expected: dict[str, Any]) -> bool:
    if proposal.get("status") != expected["status"] or proposal.get("tool_name") != expected["tool_name"]:
        return False
    return all(proposal.get("arguments", {}).get(key) == value for key, value in expected.get("arguments", {}).items())


def _levenshtein(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for index, item in enumerate(left, 1):
        current = [index]
        for other_index, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[other_index] + 1, previous[other_index - 1] + (item != other)))
        previous = current
    return previous[-1]


def _wer(reference: str, hypothesis: str) -> float | None:
    words = reference.split()
    return _levenshtein(words, hypothesis.split()) / len(words) if words else None


def _cer(reference: str, hypothesis: str) -> float | None:
    chars = list(reference.replace(" ", ""))
    return _levenshtein(chars, list(hypothesis.replace(" ", ""))) / len(chars) if chars else None


def _action_errors(expected: dict[str, Any], proposal: dict[str, Any] | None, critical_spans: list[dict[str, str]]) -> list[str]:
    if not proposal:
        return ["WRONG_INTENT"]
    labels: list[str] = []
    needs_clarification = bool(expected.get("requires_clarification"))
    actual_status = proposal.get("status")
    if needs_clarification and actual_status != RunStatus.NEEDS_CLARIFICATION.value:
        labels.append("MISSED_CLARIFICATION")
    elif not needs_clarification and actual_status == RunStatus.NEEDS_CLARIFICATION.value:
        labels.append("UNNECESSARY_CLARIFICATION")
    elif proposal.get("status") != expected.get("status"):
        labels.append("WRONG_INTENT")
    if proposal.get("tool_name") != expected.get("tool_name"):
        labels.append("WRONG_TOOL")
    desired, actual = expected.get("arguments", {}), proposal.get("arguments", {})
    # A human reference may deliberately require clarification without prescribing
    # wording. In that case the status/tool, not fabricated exact question text, is scored.
    if desired or not needs_clarification:
        if set(desired) - set(actual):
            labels.append("MISSING_ARGUMENT")
        if set(actual) - set(desired):
            labels.append("INVENTED_ARGUMENT")
        if any(desired[key] != actual[key] for key in set(desired) & set(actual)):
            labels.append("WRONG_ARGUMENT")
    span_labels = {str(span.get("label", "")) for span in critical_spans}
    if "NEGATION_ERROR" in span_labels and not _matches_expected(proposal, expected):
        labels.append("IGNORED_NEGATION")
    if "CORRECTION_ERROR" in span_labels and not _matches_expected(proposal, expected):
        labels.append("IGNORED_CORRECTION")
    return sorted(set(label for label in labels if label in ACTION_ERROR_LABELS))


def _speech_errors(reference: str, hypothesis: str, critical_spans: list[dict[str, str]]) -> list[str]:
    if reference == hypothesis:
        return []
    labels = ["SUBSTITUTION"]
    folded = hypothesis.casefold()
    for span in critical_spans:
        text, label = str(span.get("text", "")), str(span.get("label", ""))
        if text and text.casefold() not in folded and label in SPEECH_ERROR_LABELS:
            labels.append(label)
    return sorted(set(labels))


class TournamentManager:
    """Bounded whole-route evaluator. Human labels remain evaluator-side and never enter model prompts."""

    def __init__(self, engine: Engine, recipe_getter: Callable[[str], dict[str, Any] | None], save_report: Callable[[dict[str, Any]], None], seed_case_getter: Callable[[], list[dict[str, Any]]], recording_path_getter: Callable[[str], Path | None], speech_adapter: Any) -> None:
        self.engine, self.recipe_getter, self.save_report = engine, recipe_getter, save_report
        self.seed_case_getter, self.recording_path_getter, self.speech_adapter = seed_case_getter, recording_path_getter, speech_adapter
        self.jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _dataset(self, request: TournamentStart) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if request.dataset_id == "AUTHORED_SMOKE_FIXTURE":
            return _fixture_cases()[:request.case_limit], {"dataset_id": request.dataset_id, "evidence_type": "AUTHORED_SMOKE_FIXTURE", "warning": "Authored smoke fixtures are not human gold, representative data, or STT evidence."}
        all_cases = self.seed_case_getter()
        return all_cases[:request.case_limit], {"dataset_id": request.dataset_id, "evidence_type": "HUMAN_REVIEWED", "warning": "SEED_HUMAN_EVAL is a local seed set, not representative of Saudi Arabia.", "case_count_available": len(all_cases)}

    def preflight(self, request: TournamentStart) -> dict[str, Any]:
        if len(request.recipe_ids) > 6:
            raise ValueError("AT_MOST_SIX_CANDIDATE_ROUTES")
        cases, dataset = self._dataset(request)
        candidates, excluded = [], []
        for recipe_id in list(dict.fromkeys(request.recipe_ids)):
            raw = self.recipe_getter(recipe_id)
            if not raw:
                excluded.append({"recipe_id": recipe_id, "reason": "RECIPE_NOT_FOUND"})
                continue
            try:
                recipe = Recipe.model_validate(raw)
                self.engine.validate_recipe(recipe)
                if request.dataset_id == "SEED_HUMAN_EVAL" and "transcribe" not in recipe.bindings:
                    raise ValueError("SEED_HUMAN_EVAL_REQUIRES_A_REAL_TRANSCRIBE_BINDING")
            except ValueError as exc:
                excluded.append({"recipe_id": recipe_id, "reason": str(exc)})
                continue
            text_stages = int(recipe.summary_branch) + 1 + int(recipe.action_mode == "TWO_STAGE")
            stt_stages = int(request.dataset_id == "SEED_HUMAN_EVAL")
            candidates.append({"recipe_id": recipe.id, "name": recipe.name, "stages_per_case": text_stages + stt_stages, "text_stages_per_case": text_stages, "stt_stages_per_case": stt_stages, "evidence_type": sorted({binding.execution_mode.value for binding in recipe.bindings.values()}), "recipe_version": recipe.version, "recipe_hash": recipe_hash(recipe)})
        upper_bound = sum(candidate["stages_per_case"] * len(cases) for candidate in candidates)
        outcome = "NO_HUMAN_SEED_CASES" if request.dataset_id == "SEED_HUMAN_EVAL" and not cases else "NO_ELIGIBLE_ROUTE" if not candidates else "ONLY_ONE_CANDIDATE" if len(candidates) == 1 else None
        if upper_bound > request.total_call_cap:
            outcome = "CALL_CAP_EXCEEDED"
        return {"outcome": outcome or "READY_TO_START", "mode": request.mode, "dataset": dataset, "candidates": candidates, "excluded_candidates": excluded, "case_count": len(cases), "case_limit": request.case_limit, "candidate_limit": 6, "concurrency": 1, "upper_bound_calls": upper_bound, "upper_bound_local_stage_invocations": upper_bound, "call_cap": request.total_call_cap, "remote_calls": 0, "quality_floor": request.quality_floor, "requires_explicit_start": True, "timing_protocol": "A cold load is the first load for an artifact in the process. Subsequent cases are warm. Whole-route wall time is retained for every case; failures remain in the denominator."}

    def start(self, request: TournamentStart) -> dict[str, Any]:
        plan = self.preflight(request)
        if not request.confirmed:
            return {**plan, "outcome": "AWAITING_EXPLICIT_START"}
        if plan["outcome"] in {"NO_ELIGIBLE_ROUTE", "NO_HUMAN_SEED_CASES", "CALL_CAP_EXCEEDED"}:
            return plan
        job_id = str(uuid.uuid4())
        with self._lock:
            self.jobs[job_id] = {"id": job_id, "status": "RUNNING", "plan": plan, "cancel_requested": False, "report": None}
        threading.Thread(target=self._execute, args=(job_id, request), daemon=True).start()
        return {"id": job_id, "status": "RUNNING", "plan": plan}

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            job["cancel_requested"] = True
            if job["status"] == "RUNNING":
                job["status"] = "CANCEL_REQUESTED"
            return self._public_job(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self.jobs.get(job_id)
            return self._public_job(job) if job else None

    @staticmethod
    def _public_job(job: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in job.items() if key != "cancel_requested"}

    def _run_case(self, recipe: Recipe, case: dict[str, Any], human_seed: bool) -> dict[str, Any]:
        started = time.perf_counter()
        transcription: dict[str, Any] | None = None
        try:
            if human_seed:
                path = self.recording_path_getter(case["recording_id"])
                if not path:
                    raise ValueError("LOCAL_RECORDING_MISSING")
                transcription = self.speech_adapter.transcribe(recipe.bindings["transcribe"], path)
                source = transcription["text"]
                expected, provenance = case["expected"], case["provenance"]
                spans = provenance.get("critical_spans", [])
                existing_spans = [span for span in spans if span.get("text")]
                stt = {"reference": case["reviewed_transcript"], "hypothesis": source, "wer": _wer(case["reviewed_transcript"], source), "cer": _cer(case["reviewed_transcript"], source), "critical_span_accuracy": sum(int(str(span["text"]).casefold() in source.casefold()) for span in existing_spans) / max(1, len(existing_spans)), "errors": _speech_errors(case["reviewed_transcript"], source, spans), "signals": transcription.get("signals", {})}
            else:
                source, expected, provenance, stt = case["text"], case["expected"], {}, None
            result = self.engine.run(recipe, source, "2026-09-11T09:00:00+03:00")
            proposal = result.outputs["proposal"]
            action_errors = _action_errors(expected, proposal, provenance.get("critical_spans", [])) if human_seed else ([] if _matches_expected(proposal, expected) else ["WRONG_ARGUMENT"])
            success, sandbox_verified = not action_errors, None
            if proposal["status"] == RunStatus.READY.value:
                isolated = {"notes": [], "reminders": [], "lists": {}, "applied_proposal_ids": []}
                _, state = apply_to_sandbox(isolated, ToolProposal.model_validate(proposal))
                sandbox_verified = state == "APPLIED"
                success = success and sandbox_verified
            durations = dict(result.stage_durations_ms)
            if transcription:
                durations["transcribe"] = transcription.get("latency_ms")
            resources = list(result.outputs.get("resource_measurements", []))
            if transcription and transcription.get("resource_measurement"):
                resources.append({"role": "transcribe", **transcription["resource_measurement"]})
            return {"case_id": case["id"], "outcome": proposal["status"], "success": success, "sandbox_verified": sandbox_verified, "duration_ms": (time.perf_counter() - started) * 1000, "stage_durations_ms": durations, "proposal": proposal, "transcription": transcription, "stt": stt, "action_errors": action_errors, "resource_measurements": resources, "error": None}
        except Exception as exc:
            return {"case_id": case["id"], "outcome": "FAILED", "success": False, "sandbox_verified": False, "duration_ms": (time.perf_counter() - started) * 1000, "stage_durations_ms": {}, "proposal": None, "transcription": transcription, "stt": None, "action_errors": ["WRONG_INTENT"], "resource_measurements": [], "error": f"{type(exc).__name__}:{str(exc)[:180]}"}

    def _execute(self, job_id: str, request: TournamentStart) -> None:
        cases, dataset = self._dataset(request)
        plan, human_seed, routes, cancelled = self.preflight(request), request.dataset_id == "SEED_HUMAN_EVAL", [], False
        for candidate in plan["candidates"]:
            with self._lock:
                if self.jobs[job_id]["cancel_requested"]:
                    cancelled = True
                    break
            recipe = Recipe.model_validate(self.recipe_getter(candidate["recipe_id"]))
            per_case = []
            for case in cases:
                with self._lock:
                    if self.jobs[job_id]["cancel_requested"]:
                        cancelled = True
                        break
                per_case.append(self._run_case(recipe, case, human_seed))
            routes.append(self._route_result(recipe, candidate, cases, per_case))
            if cancelled:
                break
        report = {"id": job_id, "status": "CANCELLED" if cancelled else "COMPLETED", "mode": request.mode, "evidence_type": f"{dataset['evidence_type']} + route-specific execution evidence", "dataset_id": request.dataset_id, "dataset_warning": dataset["warning"], "runtime": {"python": platform.python_version(), "platform": platform.system(), "machine": platform.machine()}, "hardware_summary": "Machine-local preflight stored separately; no sensitive identifiers included.", "quality_floor": request.quality_floor, "routes": routes, "selection": self._select(request.mode, routes, request.quality_floor) if not cancelled else {"outcome": "CANCELLED"}, "remote_calls": 0, "retry_count": 0, "cache_protocol": "No stage-output cache. Model residency may make later cases warm; model-load metrics are retained.", "confidence_diagnostics": {"calibrated_correctness": None, "note": "Native signals are observational only; no calibrated confidence mapping is fitted."}}
        if not cancelled:
            self.save_report(report)
        with self._lock:
            self.jobs[job_id]["status"], self.jobs[job_id]["report"] = report["status"], report

    @staticmethod
    def _route_result(recipe: Recipe, candidate: dict[str, Any], cases: list[dict[str, Any]], per_case: list[dict[str, Any]]) -> dict[str, Any]:
        successes = sum(item["success"] for item in per_case)
        attempted, failures = len(per_case), len(per_case) - successes
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        metrics: list[dict[str, Any]] = []
        errors: dict[str, int] = {}
        for item in per_case:
            for stage, duration in item["stage_durations_ms"].items():
                if isinstance(duration, (int, float)):
                    totals[stage], counts[stage] = totals.get(stage, 0) + duration, counts.get(stage, 0) + 1
            metrics.extend(item["resource_measurements"])
            for label in item.get("action_errors", []) + (item.get("stt") or {}).get("errors", []):
                errors[label] = errors.get(label, 0) + 1
        stt_items = [item["stt"] for item in per_case if item.get("stt")]
        available_wer = [item["wer"] for item in stt_items if item["wer"] is not None]
        available_cer = [item["cer"] for item in stt_items if item["cer"] is not None]
        resource = max((int(item.get("artifact_bytes") or 0) for item in metrics), default=None)
        durations = [item["duration_ms"] for item in per_case]
        return {"recipe_id": recipe.id, "name": recipe.name, "evidence_type": "DEMO_RULES" if all(item == "DEMO_RULES" for item in candidate["evidence_type"]) else "REAL_LOCAL_MODEL", "recipe_version": recipe.version, "recipe_hash": candidate["recipe_hash"], "bindings": [binding.model_dump(mode="json") for binding in recipe.bindings.values()], "cases_attempted": attempted, "successes": successes, "failures": failures, "completion_coverage": attempted / len(cases) if cases else 0, "task_quality": successes / len(cases) if cases else 0, "failure_rate": failures / len(cases) if cases else 0, "marginal_provider_cost_usd": 0.0, "resource_footprint_bytes": resource, "mean_end_to_end_latency_ms": sum(durations) / len(durations) if durations else None, "stage_duration_totals_ms": totals, "stage_duration_means_ms": {stage: total / counts[stage] for stage, total in totals.items()}, "stt_metrics": {"mean_wer": sum(available_wer) / len(available_wer) if available_wer else None, "mean_cer": sum(available_cer) / len(available_cer) if available_cer else None, "critical_span_accuracy": sum(item["critical_span_accuracy"] for item in stt_items) / len(stt_items) if stt_items else None}, "error_taxonomy": errors, "resource_measurements": metrics, "per_case": per_case, "timing_note": "Real local measurements. Failed routes remain in the quality and completion denominator."}

    @staticmethod
    def _select(mode: str, routes: list[dict[str, Any]], quality_floor: float) -> dict[str, Any]:
        if not routes:
            return {"outcome": "NO_ELIGIBLE_ROUTE"}
        if mode == "Manual":
            return {"outcome": "MANUAL", "recommendation": None, "reason": "The selected bindings and recipe run exactly as chosen; no optimizer override."}
        eligible = [route for route in routes if route["task_quality"] >= quality_floor and route["completion_coverage"] == 1]
        if not eligible:
            return {"outcome": "NO_ROUTE_MEETS_FLOOR", "reason": "Quality or completion gate was not met; failed routes are not treated as fast."}
        resource = lambda route: route["resource_footprint_bytes"] if route["resource_footprint_bytes"] is not None else float("inf")
        latency = lambda route: route["mean_end_to_end_latency_ms"] if route["mean_end_to_end_latency_ms"] is not None else float("inf")
        if mode == "Performance":
            ordered, reason = sorted(eligible, key=lambda route: (-route["task_quality"], latency(route), resource(route))), "Highest end-to-end task correctness; latency then resource footprint break ties."
        elif mode == "Speed":
            ordered, reason = sorted(eligible, key=lambda route: (latency(route), -route["task_quality"], resource(route))), "Lowest observed end-to-end wall-clock latency among routes meeting the quality floor."
        else:
            ordered, reason = sorted(eligible, key=lambda route: (-route["task_quality"], resource(route), latency(route))), "All-local provider monetary inference cost is 0. Quality rank, resource footprint, then latency break the zero-cost tie."
        winner = ordered[0]
        ties = [route["recipe_id"] for route in ordered if route["task_quality"] == winner["task_quality"] and resource(route) == resource(winner) and abs(latency(route) - latency(winner)) < 0.000001]
        return {"outcome": "TIE" if len(ties) > 1 else "RECOMMENDED", "recommendation": winner["recipe_id"], "ties": ties, "reason": reason, "scope": "Evidence is limited to the named dataset and retained case-level results."}
