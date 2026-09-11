import io
import os
import tempfile
import time
import wave

os.environ.setdefault("SAUDI_STA_DATA_DIR", tempfile.mkdtemp(prefix="saudi-sta-tests-"))

from fastapi.testclient import TestClient

from app.main import app, store


client = TestClient(app)


def wav_bytes(seconds=1):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\0\0" * 8000 * seconds)
    return stream.getvalue()


def test_browser_journey_run_apply_edit_and_stale_proposal():
    response = client.post("/api/runs", json={"text": "حط milk وقهوة في قائمة المقاضي", "recipe_id": "demo_direct_v1"})
    assert response.status_code == 200
    record = response.json()["record"]
    proposal = record["outputs"]["proposal"]
    assert proposal["status"] == "READY"
    applied = client.post(f"/api/records/{record['id']}/apply", json={"proposal_id": proposal["id"]})
    assert applied.status_code == 200 and applied.json()["status"] == "APPLIED"
    duplicate = client.post(f"/api/records/{record['id']}/apply", json={"proposal_id": proposal["id"]})
    assert duplicate.json()["status"] == "ALREADY_APPLIED"
    edited = client.patch(f"/api/records/{record['id']}/transcript", json={"text": "حط شاي في قائمة المقاضي", "expected_revision": 1})
    assert edited.status_code == 200 and edited.json()["outputs"]["stale"] is True
    stale = client.post(f"/api/records/{record['id']}/apply", json={"proposal_id": proposal["id"]})
    assert stale.status_code == 409


def test_audio_upload_is_application_managed_and_wav_duration_is_verified():
    uploaded = client.post("/api/recordings", files={"file": ("clip.wav", wav_bytes(), "audio/wav")})
    assert uploaded.status_code == 200
    payload = uploaded.json()
    assert payload["duration_source"] == "WAV_SERVER_VERIFIED"
    retrieved = client.get(f"/api/recordings/{payload['recording_id']}")
    assert retrieved.status_code == 200 and retrieved.headers["content-type"].startswith("audio/wav")


def test_mutations_require_local_host_and_recipe_spoofing_is_rejected():
    blocked = client.post("/api/runs", headers={"host": "example.org"}, json={"text": "x"})
    assert blocked.status_code == 403
    recipes = client.get("/api/recipes").json()
    spoofed = recipes[0]
    spoofed["id"] = "spoofed"
    spoofed["bindings"]["summarize"]["provider"] = "openai"
    rejected = client.post("/api/recipes", json=spoofed)
    assert rejected.status_code == 422


def test_tournament_preflight_and_bounded_execution_keep_demo_evidence_separate():
    plan = client.post("/api/tournaments/preflight", json={"mode": "Speed", "recipe_ids": ["demo_direct_v1", "demo_two_stage_v1"], "case_limit": 12, "total_call_cap": 72, "quality_floor": .7, "confirmed": False})
    assert plan.status_code == 200
    assert plan.json()["upper_bound_calls"] == 60
    started = client.post("/api/tournaments/start", json={"mode": "Speed", "recipe_ids": ["demo_direct_v1", "demo_two_stage_v1"], "case_limit": 12, "total_call_cap": 72, "quality_floor": .7, "confirmed": True}).json()
    assert started["status"] == "RUNNING"
    for _ in range(40):
        job = client.get(f"/api/tournaments/{started['id']}").json()
        if job["status"] == "COMPLETED":
            break
        time.sleep(.05)
    assert job["status"] == "COMPLETED"
    assert all(route["evidence_type"] == "DEMO_RULES" for route in job["report"]["routes"])
    assert all(route["task_quality"] == 1 for route in job["report"]["routes"])
    assert job["report"]["remote_calls"] == 0
    assert client.get(f"/api/tournaments/{started['id']}/export.csv").status_code == 200


def test_training_manifest_excludes_unknown_rights_and_auto_promotion():
    manifest = client.get("/api/training-manifest").json()
    assert manifest["automatic_silver_promotion"] is False
    assert all("training_use_not_granted" in entry["reasons"] for entry in manifest["excluded"])


def test_download_worker_status_is_external_and_read_only():
    response = client.get("/api/download-worker")
    assert response.status_code == 200
    assert response.json().get("effective_state") in {"ACTIVE", "STALE", "STOPPED", "FAILED", "DOWNLOADING", "STARTING", "QUEUED"}


def test_seed_scenario_queue_is_prompt_only_and_catalog_keeps_audar_precisions_distinct():
    scenarios = client.get("/api/seed-scenarios")
    assert scenarios.status_code == 200
    payload = scenarios.json()
    assert payload["evidence_type"] == "SCENARIO_PROMPT_ONLY" and payload["count"] >= 30
    catalog = client.get("/api/catalog").json()["bindings"]
    audar = [binding for binding in catalog if binding["provider"] == "audar_mtmd_local"]
    assert {binding["model_id"] for binding in audar} >= {"AUDAR_TURBO_Q4_LOCAL_BRIDGE", "AUDAR_TURBO_Q8_LOCAL", "AUDAR_FLASH_Q8_LOCAL"}


def test_catalog_exposes_passive_optional_stage_evidence_and_qwen_waiting_state():
    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    stages = {item["stage"]: item for item in catalog.json()["stage_capabilities"]["stages"]}
    assert set(stages) == {"vad", "turn_detection", "diarization"}
    assert all(item["capability_state"] == "CAPABILITY_PENDING" for item in stages.values())
    qwen = client.get("/api/qwen-certification")
    assert qwen.status_code == 200
    assert qwen.json()["status"] == "WAITING_FOR_QWEN_ARTIFACT"


def test_seed_human_case_is_explicit_and_separate_from_smoke_fixtures():
    uploaded = client.post("/api/recordings", files={"file": ("seed.wav", wav_bytes(), "audio/wav")})
    assert uploaded.status_code == 200
    saved = client.post("/api/seed-human-eval", json={
        "recording_id": uploaded.json()["recording_id"], "reviewed_transcript": "ذكرني الساعة سبعة لا ثمانية",
        "expected_status": "READY", "expected_tool_name": "create_reminder_draft", "expected_arguments": {"hour": 8},
        "critical_spans": [{"text": "ثمانية", "label": "CORRECTION_ERROR"}], "reviewer_identity": "local-reviewer", "recording_session_id": "test-session",
    })
    assert saved.status_code == 200
    listing = client.get("/api/seed-human-eval").json()
    assert listing["evidence_type"] == "HUMAN_REVIEWED"
    assert listing["cases"][-1]["provenance"]["pseudo_labels_used"] is False
    plan = client.post("/api/tournaments/preflight", json={"mode": "Performance", "dataset_id": "SEED_HUMAN_EVAL", "recipe_ids": ["demo_direct_v1"], "case_limit": 1, "total_call_cap": 20, "confirmed": False})
    assert plan.status_code == 200
    assert plan.json()["dataset"]["evidence_type"] == "HUMAN_REVIEWED"
    assert plan.json()["excluded_candidates"][0]["reason"] == "SEED_HUMAN_EVAL_REQUIRES_A_REAL_TRANSCRIBE_BINDING"


def test_review_states_and_model_outputs_remain_separate():
    uploaded = client.post("/api/recordings", files={"file": ("review.wav", wav_bytes(), "audio/wav")})
    assert uploaded.status_code == 200
    run = client.post("/api/runs", json={"text": "حط milk في المقاضي", "recipe_id": "demo_direct_v1", "recording_id": uploaded.json()["recording_id"], "manual_transcript": True})
    record = run.json()["record"]
    assert record["review_state"] == "RECORDED"
    original_proposal = record["outputs"]["proposal"]
    reviewed = client.patch(f"/api/records/{record['id']}/review", json={"label_state": "CANDIDATE", "reviewer_type": "human", "reviewer_identity": "reviewer-1"})
    assert reviewed.json()["review_state"] == "HUMAN_TRANSCRIPT_REVIEWED"
    edited = client.patch(f"/api/records/{record['id']}/transcript", json={"text": "حط شاي في المقاضي", "expected_revision": 1})
    assert edited.json()["original_text"] == "حط milk في المقاضي"
    assert edited.json()["outputs"]["proposal"] == original_proposal
    assert edited.json()["outputs"]["transcript_edit_history"][0]["original_text"] == "حط milk في المقاضي"


def test_original_model_transcript_is_immutable_when_human_text_is_edited():
    record_id = store.save_record("raw source", {"evidence_type": "REAL_LOCAL_MODEL", "transcription": {"text": "الناتج الأصلي", "runtime": "fixture"}})
    edited = client.patch(f"/api/records/{record_id}/transcript", json={"text": "النص البشري المصحح", "expected_revision": 1})
    assert edited.status_code == 200
    payload = edited.json()
    assert payload["review_state"] == "MODEL_TRANSCRIBED"
    assert payload["outputs"]["transcription"]["text"] == "الناتج الأصلي"
    assert payload["outputs"]["transcript_edit_history"][0]["original_text"] == "raw source"


def test_semantic_reference_review_has_an_explicit_state_without_gold_promotion():
    uploaded = client.post("/api/recordings", files={"file": ("semantic.wav", wav_bytes(), "audio/wav")})
    saved = client.post("/api/seed-human-eval", json={
        "recording_id": uploaded.json()["recording_id"], "reviewed_transcript": "حط milk",
        "expected_status": "READY", "expected_tool_name": "add_list_items", "expected_arguments": {"list_name": "shopping", "items": ["milk"]},
        "semantic_reference_reviewed": True, "reviewer_identity": "reviewer-2",
    })
    assert saved.status_code == 200
    case = saved.json()["case"]
    assert case["review_state"] == "SEMANTIC_REFERENCE_REVIEWED"
    assert case["provenance"]["pseudo_labels_used"] is False
