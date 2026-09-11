from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import uuid
import wave
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .engine import Engine, apply_to_sandbox
from .capability_certification import capability_bindings, stage_capability_report
from .download_status import read_worker_status
from .policy import PolicyViolation, allowed_browser_host, allowed_origin
from .providers import AudarMtmdAdapter, FasterWhisperAdapter, LlamaCppAdapter, LocalArtifactRegistry, LocalModelUnavailable, OllamaAdapter, TransformersWhisperAdapter, provider_matrix
from .qwen_certification import qwen_certification_plan
from .model_registry import configured_roots, scan_models
from .schemas import ApplyRequest, Recipe, ReviewUpdate, Role, RoleBinding, RunRequest, RunStatus, SeedHumanCaseCreate, STTTournamentStart, ToolProposal, TournamentStart, TranscriptEdit
from .store import Store
from .stt_tournament import run_stt_tournament
from .seed_scenarios import SEED_SCENARIOS
from .tournament import TournamentManager


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SAUDI_STA_DATA_DIR", str(PROJECT_ROOT / "runtime")))
store = Store(DATA_DIR)
ollama = OllamaAdapter()
artifact_registry = LocalArtifactRegistry()
faster_speech = FasterWhisperAdapter()
speech = TransformersWhisperAdapter(artifact_registry)
audar_speech = AudarMtmdAdapter(artifact_registry)
local_text = LlamaCppAdapter(artifact_registry)
engine = Engine(ollama, local_text)
app = FastAPI(title="Saudi STA Workbench", version="0.1.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")


def demo_binding(role: Role) -> RoleBinding:
    return RoleBinding(
        id=f"demo_rules:{role.value}:v1", provider="demo_rules", model_id="deterministic-saudi-rules-v1", revision_or_digest="source-v1",
        role=role, prompt_version="demo-v1", schema_version="sta-v1", execution_mode="DEMO_RULES",
        capability_provenance="DOCUMENTED", capabilities=[role.value], tool_mode="JSON_EMULATION" if role == Role.FUNCTION_CALL else "NONE",
    )


def default_recipes() -> list[Recipe]:
    return [
        Recipe(
            id="demo_direct_v1", name="Demo Rules · direct function proposal", action_mode="DIRECT", summary_branch=True,
            graph=["summarize", "function_call"], bindings={"summarize": demo_binding(Role.SUMMARIZE), "function_call": demo_binding(Role.FUNCTION_CALL)},
        ),
        Recipe(
            id="demo_two_stage_v1", name="Demo Rules · semantic plan then proposal", action_mode="TWO_STAGE", summary_branch=True,
            graph=["summarize", "actionize", "function_call"], bindings={"summarize": demo_binding(Role.SUMMARIZE), "actionize": demo_binding(Role.ACTIONIZE), "function_call": demo_binding(Role.FUNCTION_CALL)},
        ),
    ]


def local_default_recipes() -> list[Recipe]:
    """Named real routes appear only after each independent binding was exercised by discovery."""
    catalog = {binding.id: binding for binding in current_bindings()}
    stt = speech.binding()
    if not stt.available:
        return []
    candidates = [binding for binding in catalog.values() if binding.provider == "llama_cpp_local" and binding.available]
    by_model: dict[str, dict[str, RoleBinding]] = {}
    for binding in candidates:
        by_model.setdefault(binding.model_id, {})[binding.role.value] = binding
    result: list[Recipe] = []
    for model_id, roles in by_model.items():
        if not {"summarize", "actionize", "function_call"}.issubset(roles):
            continue
        safe_id = "".join(char if char.isalnum() else "_" for char in model_id).strip("_").lower()
        result.extend([
            Recipe(
                id=f"real_{safe_id}_direct_v1", name=f"Real local · {model_id} · Direct STT → function call",
                version="slice02-v1", action_mode="DIRECT", summary_branch=False,
                graph=["transcribe", "function_call"],
                bindings={"transcribe": stt, "function_call": roles["function_call"]}, required_outputs=["proposal"],
            ),
            Recipe(
                id=f"real_{safe_id}_semantic_v1", name=f"Real local · {model_id} · Semantic STT → actionize → function call",
                version="slice02-v1", action_mode="TWO_STAGE", summary_branch=False,
                graph=["transcribe", "actionize", "function_call"],
                bindings={"transcribe": stt, "actionize": roles["actionize"], "function_call": roles["function_call"]}, required_outputs=["proposal"],
            ),
            Recipe(
                id=f"real_{safe_id}_semantic_summary_v1", name=f"Real local · {model_id} · Semantic + summary",
                version="slice02-v1", action_mode="TWO_STAGE", summary_branch=True,
                graph=["transcribe", "summarize", "actionize", "function_call"],
                bindings={"transcribe": stt, "summarize": roles["summarize"], "actionize": roles["actionize"], "function_call": roles["function_call"]},
            ),
        ])
    return result


for default_recipe in default_recipes():
    existing_default = store.get_recipe(default_recipe.id)
    if not existing_default or existing_default.get("graph") != default_recipe.graph:
        store.save_recipe(default_recipe.model_dump(mode="json"))


def ensure_local_default_recipes() -> None:
    for recipe in local_default_recipes():
        if not store.get_recipe(recipe.id):
            store.save_recipe(recipe.model_dump(mode="json"))


def current_bindings() -> list[RoleBinding]:
    # No automatic discovery during startup. A configured local endpoint is queried only when this catalog is requested.
    audar_bindings = audar_speech.discover() or [audar_speech.binding()]
    return [demo_binding(role) for role in (Role.SUMMARIZE, Role.ACTIONIZE, Role.FUNCTION_CALL)] + [speech.binding()] + audar_bindings + [faster_speech.binding()] + local_text.discover() + ollama.discover() + capability_bindings()


def catalog_by_id() -> dict[str, RoleBinding]:
    return {binding.id: binding for binding in current_bindings()}


def validate_saved_recipe(recipe: Recipe) -> None:
    catalog = catalog_by_id()
    for role, binding in recipe.bindings.items():
        verified = catalog.get(binding.id)
        if not verified or verified.model_dump(mode="json") != binding.model_dump(mode="json"):
            raise HTTPException(422, detail=f"UNVERIFIED_BINDING:{role}. Bindings must come from server-discovered local catalog.")
    try:
        engine.validate_recipe(recipe)
    except (ValueError, PolicyViolation) as exc:
        raise HTTPException(422, detail=str(exc)) from exc


tournaments = TournamentManager(engine, store.get_recipe, store.save_tournament, store.list_seed_human_cases, store.recording_path, speech)


@app.middleware("http")
async def local_mutation_guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not allowed_browser_host(request.headers.get("host")) or not allowed_origin(request.headers.get("origin")):
            return JSONResponse({"detail": "LOCAL_ORIGIN_REQUIRED"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "execution_policy": "ZERO_SPEND_LOCAL", "remote_inference": "blocked", "data_dir": "local runtime directory"}


@app.get("/api/download-worker")
def download_worker_status() -> dict[str, Any]:
    return read_worker_status()


@app.get("/api/catalog")
def catalog() -> dict[str, Any]:
    bindings = [binding.model_dump(mode="json") for binding in current_bindings()]
    return {
        "execution_policy": "ZERO_SPEND_LOCAL",
        "bindings": bindings,
        "reserved_roles": [role.value for role in (Role.ACOUSTIC_REPAIR, Role.SEMANTIC_REPAIR, Role.VERIFY, Role.RESPOND, Role.SYNTHESIZE)],
        "stage_capabilities": stage_capability_report(),
        "provider_matrix": provider_matrix(ollama, faster_speech, speech, audar_speech, local_text),
        "locality_checks": ollama.checks,
    }


@app.get("/api/models")
def models() -> dict[str, Any]:
    """Passive model-lab inventory; arrival never activates a route."""
    return {"model_root": [str(root) for root in configured_roots()], "auto_activation": False, "models": scan_models()}


@app.get("/api/qwen-certification")
def qwen_certification() -> dict[str, Any]:
    binding = next((item for item in current_bindings() if item.model_id in {"QWEN38_27B_Q6_K_L", "QWEN3_8_27B_Q6_K_L"}), None)
    return qwen_certification_plan(binding)


@app.get("/api/recipes")
def list_recipes() -> list[dict[str, Any]]:
    ensure_local_default_recipes()
    return store.list_recipes()


@app.post("/api/recipes")
def save_recipe(recipe: Recipe) -> dict[str, Any]:
    validate_saved_recipe(recipe)
    store.save_recipe(recipe.model_dump(mode="json"))
    return {"status": "SAVED", "recipe": recipe.model_dump(mode="json")}


@app.get("/api/records")
def list_records() -> list[dict[str, Any]]:
    return store.list_records()


@app.get("/api/records/{record_id}")
def get_record(record_id: str) -> dict[str, Any]:
    record = store.get_record(record_id)
    if not record:
        raise HTTPException(404, "RECORD_NOT_FOUND")
    return record


@app.post("/api/runs")
def run_workbench(body: RunRequest) -> dict[str, Any]:
    recipe_body = store.get_recipe(body.recipe_id)
    if not recipe_body:
        raise HTTPException(404, "RECIPE_NOT_FOUND")
    recipe = Recipe.model_validate(recipe_body)
    validate_saved_recipe(recipe)
    recording_name = None
    if body.recording_id:
        recording = store.recording(body.recording_id)
        if not recording:
            raise HTTPException(404, "RECORDING_NOT_FOUND")
        recording_name = recording["filename"]
    text = body.text.strip()
    if not text and not recording_name:
        raise HTTPException(422, "TEXT_OR_RECORDING_REQUIRED")
    transcription = None
    if not text and recording_name:
        transcribe_binding = recipe.bindings.get("transcribe")
        if transcribe_binding and transcribe_binding.provider in {"transformers_whisper_local", "audar_mtmd_local"} and transcribe_binding.available:
            try:
                adapter = audar_speech if transcribe_binding.provider == "audar_mtmd_local" else speech
                transcription = adapter.transcribe(transcribe_binding, store.recording_path(body.recording_id)) if transcribe_binding.provider == "audar_mtmd_local" else adapter.transcribe(store.recording_path(body.recording_id))
                text = transcription["text"]
            except (LocalModelUnavailable, PolicyViolation) as exc:
                transcription = {"status": "UNAVAILABLE_LOCAL_MODEL", "reason": str(exc)}
    if not text:
        outputs = {
            "evidence_type": "BLOCKED_LOCAL_SPEECH",
            "transcription": {"status": "UNAVAILABLE_LOCAL_MODEL", "reason": "No verified local speech binding is configured. Add a manual transcript to continue."},
            "summary": None, "semantic_plan": None, "proposal": None, "stale": False,
            "reference_timestamp": body.reference_timestamp, "timezone": body.timezone,
        }
    else:
        try:
            result = engine.run(recipe, text, body.reference_timestamp)
            outputs = result.outputs
            if transcription:
                outputs["transcription"] = {"status": "READY", "evidence_type": "REAL_LOCAL_MODEL", **transcription}
            outputs["transcript_origin"] = "LOCAL_ASR" if transcription else ("MANUAL_TRANSCRIPT_ASSOCIATED_WITH_RECORDING" if body.manual_transcript and recording_name else "TEXT_ENTRY")
        except (ValueError, PolicyViolation) as exc:
            raise HTTPException(422, str(exc)) from exc
    record_id = store.save_record(text, outputs, recording_name)
    return {"record_id": record_id, "record": store.get_record(record_id)}


@app.patch("/api/records/{record_id}/transcript")
def edit_transcript(record_id: str, body: TranscriptEdit) -> dict[str, Any]:
    try:
        record = store.edit_transcript(record_id, body.text.strip(), body.expected_revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not record:
        raise HTTPException(404, "RECORD_NOT_FOUND")
    return record


@app.patch("/api/records/{record_id}/review")
def update_review(record_id: str, body: ReviewUpdate) -> dict[str, Any]:
    if body.label_state in {"SILVER", "GOLD"} and body.reviewer_type != "human":
        raise HTTPException(422, "ONLY_HUMAN_REVIEW_CAN_PROMOTE_A_LABEL")
    review = {"reviewer_type": body.reviewer_type, "reviewer_identity": body.reviewer_identity, "promotion_reason": body.promotion_reason}
    record = store.update_review(record_id, review, body.label_state.value)
    if not record:
        raise HTTPException(404, "RECORD_NOT_FOUND")
    return record


@app.delete("/api/records/{record_id}")
def delete_record(record_id: str) -> dict[str, Any]:
    if not store.delete_record(record_id):
        raise HTTPException(404, "RECORD_NOT_FOUND")
    return {"status": "DELETED", "note": "The local record and its associated stored derivative were removed. Prior exports cannot be recalled automatically."}


@app.post("/api/records/{record_id}/apply")
def apply_proposal(record_id: str, body: ApplyRequest) -> dict[str, Any]:
    record = store.get_record(record_id)
    if not record:
        raise HTTPException(404, "RECORD_NOT_FOUND")
    outputs = record["outputs"]
    proposal_body = outputs.get("proposal")
    if outputs.get("stale"):
        raise HTTPException(409, "STALE_PROPOSAL: rerun after transcript edit")
    if not proposal_body or proposal_body.get("id") != body.proposal_id:
        raise HTTPException(404, "PROPOSAL_NOT_FOUND")
    proposal = ToolProposal.model_validate(proposal_body)
    if proposal.source_revision != record["revision"]:
        raise HTTPException(409, "STALE_PROPOSAL")
    try:
        state, status = apply_to_sandbox(store.get_sandbox(), proposal)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    store.save_sandbox(state)
    return {"status": status, "sandbox": state}


@app.get("/api/sandbox")
def sandbox() -> dict[str, Any]:
    return store.get_sandbox()


SUPPORTED_AUDIO = {"audio/wav": ".wav", "audio/x-wav": ".wav", "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a"}
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 300


def wav_duration_seconds(payload: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(payload), "rb") as source:
            return source.getnframes() / source.getframerate()
    except (wave.Error, EOFError):
        return None


@app.post("/api/recordings")
async def upload_recording(file: UploadFile = File(...), duration_seconds: float | None = Form(default=None)) -> dict[str, Any]:
    mime_type = (file.content_type or "").lower()
    if mime_type not in SUPPORTED_AUDIO:
        raise HTTPException(415, "UNSUPPORTED_MEDIA: use WAV, WebM, OGG, MP3, or M4A audio")
    payload = await file.read(MAX_AUDIO_BYTES + 1)
    if not payload or len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "AUDIO_SIZE_LIMIT_EXCEEDED: maximum is 10 MiB")
    verified_duration = wav_duration_seconds(payload) if SUPPORTED_AUDIO[mime_type] == ".wav" else None
    effective_duration = verified_duration if verified_duration is not None else duration_seconds
    if effective_duration is None:
        raise HTTPException(422, "DURATION_REQUIRED_FOR_NON_WAV: recorder must provide a duration; WAV duration is verified server-side")
    if effective_duration <= 0 or effective_duration > MAX_AUDIO_SECONDS:
        raise HTTPException(413, "AUDIO_DURATION_LIMIT_EXCEEDED: maximum is 300 seconds")
    recording_id, filename = store.save_audio(payload, SUPPORTED_AUDIO[mime_type], mime_type, effective_duration)
    speech_available = speech.status()["available"] or any(binding.available for binding in audar_speech.discover())
    return {"recording_id": recording_id, "filename": filename, "duration_seconds": effective_duration, "duration_source": "WAV_SERVER_VERIFIED" if verified_duration is not None else "RECORDER_REPORTED", "asr_status": "LOCAL_SPEECH_AVAILABLE" if speech_available else "UNAVAILABLE_LOCAL_MODEL"}


@app.get("/api/recordings/{recording_id}")
def fetch_recording(recording_id: str) -> FileResponse:
    recording = store.recording(recording_id)
    path = store.recording_path(recording_id)
    if not recording or not path:
        raise HTTPException(404, "RECORDING_NOT_FOUND")
    return FileResponse(path, media_type=recording["mime_type"], filename="recording" + path.suffix)


@app.get("/api/seed-human-eval")
def list_seed_human_eval() -> dict[str, Any]:
    cases = store.list_seed_human_cases()
    return {
        "dataset_id": "SEED_HUMAN_EVAL", "evidence_type": "HUMAN_REVIEWED",
        "case_count": len(cases), "target_case_count": "20-30",
        "representativeness": "A local seed set only; it is not representative of Saudi Arabia.",
        "cases": cases,
    }


@app.get("/api/seed-scenarios")
def list_seed_scenarios() -> dict[str, Any]:
    return {"dataset_id": "SEED_HUMAN_EVAL", "evidence_type": "SCENARIO_PROMPT_ONLY", "count": len(SEED_SCENARIOS), "scenarios": SEED_SCENARIOS}


@app.post("/api/seed-human-eval")
def add_seed_human_eval(body: SeedHumanCaseCreate) -> dict[str, Any]:
    if not store.recording(body.recording_id):
        raise HTTPException(404, "RECORDING_NOT_FOUND")
    expected = {
        "status": body.expected_status.value, "tool_name": body.expected_tool_name,
        "arguments": body.expected_arguments, "requires_clarification": body.requires_clarification,
    }
    provenance = {
        "reviewer_type": "human", "reviewer_identity": body.reviewer_identity,
        "recording_session_id": body.recording_session_id, "critical_spans": body.critical_spans,
        "notes": body.notes, "label_source": "explicit_human_review", "pseudo_labels_used": False,
    }
    try:
        case = store.save_seed_human_case(body.recording_id, body.reviewed_transcript.strip(), expected, provenance)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(409, "RECORDING_ALREADY_HAS_SEED_HUMAN_LABEL") from exc
        raise
    return {"status": "SAVED", "case": case}


def _stt_bindings(binding_ids: list[str]) -> list[RoleBinding]:
    bindings = [binding for binding in current_bindings() if binding.role == Role.TRANSCRIBE and binding.provider in {"transformers_whisper_local", "audar_mtmd_local", "faster_whisper_local"}]
    if binding_ids:
        bindings = [binding for binding in bindings if binding.id in binding_ids]
    return bindings


def _stt_runner(binding: RoleBinding, audio_path: Path) -> dict[str, Any]:
    if binding.provider == "audar_mtmd_local":
        return audar_speech.transcribe(binding, audio_path)
    if binding.provider == "transformers_whisper_local":
        return speech.transcribe(binding, audio_path)
    return faster_speech.transcribe(audio_path)


def _run_stt_comparison(body: STTTournamentStart) -> dict[str, Any]:
    path = store.recording_path(body.recording_id)
    if not path:
        raise HTTPException(404, "RECORDING_NOT_FOUND")
    bindings = _stt_bindings(body.binding_ids)
    if not bindings:
        raise HTTPException(422, "NO_TRANSCRIBE_BINDINGS_AVAILABLE")
    human_reference = next((case["reviewed_transcript"] for case in store.list_seed_human_cases() if case["recording_id"] == body.recording_id), None)
    report = run_stt_tournament(path, bindings, _stt_runner, human_reference=human_reference, mode=body.mode, manual_binding_id=body.manual_binding_id)
    report.update({"id": str(uuid.uuid4()), "recording_id": body.recording_id, "status": "COMPLETED", "dataset_id": "SEED_HUMAN_EVAL" if human_reference else "UNREVIEWED_LOCAL_RECORDING"})
    store.save_tournament(report)
    return report


@app.post("/api/stt-tournaments/start")
def stt_tournament_start(body: STTTournamentStart) -> dict[str, Any]:
    return _run_stt_comparison(body)


@app.get("/api/recordings/{recording_id}/stt-compare")
def stt_compare_recording(recording_id: str) -> dict[str, Any]:
    return _run_stt_comparison(STTTournamentStart(recording_id=recording_id, mode="Performance"))


@app.post("/api/tournaments/preflight")
def tournament_preflight(body: TournamentStart) -> dict[str, Any]:
    try:
        return tournaments.preflight(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/tournaments/start")
def tournament_start(body: TournamentStart) -> dict[str, Any]:
    try:
        return tournaments.start(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/tournaments/{job_id}")
def tournament_status(job_id: str) -> dict[str, Any]:
    job = tournaments.get(job_id)
    if not job:
        saved = store.get_tournament(job_id)
        if saved:
            return {"id": job_id, "status": saved["status"], "report": saved}
        raise HTTPException(404, "TOURNAMENT_NOT_FOUND")
    return job


@app.post("/api/tournaments/{job_id}/cancel")
def tournament_cancel(job_id: str) -> dict[str, Any]:
    job = tournaments.cancel(job_id)
    if not job:
        raise HTTPException(404, "TOURNAMENT_NOT_FOUND")
    return job


@app.get("/api/tournaments/{job_id}/export.json")
def tournament_json(job_id: str) -> JSONResponse:
    report = store.get_tournament(job_id)
    if not report:
        raise HTTPException(404, "REPORT_NOT_FOUND")
    return JSONResponse(report, headers={"Content-Disposition": f'attachment; filename="saudi-sta-{job_id}.json"'})


@app.get("/api/tournaments/{job_id}/export.csv")
def tournament_csv(job_id: str) -> Response:
    report = store.get_tournament(job_id)
    if not report:
        raise HTTPException(404, "REPORT_NOT_FOUND")
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["recipe_id", "name", "evidence_type", "cases_attempted", "successes", "failures", "completion_coverage", "task_quality", "failure_rate", "marginal_provider_cost_usd", "mean_end_to_end_latency_ms"])
    writer.writeheader()
    for route in report["routes"]:
        writer.writerow({key: route.get(key) for key in writer.fieldnames})
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="saudi-sta-{job_id}.csv"'})


@app.get("/api/training-manifest")
def training_manifest() -> dict[str, Any]:
    return store.training_manifest()
