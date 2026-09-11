import json
from datetime import datetime, timedelta, timezone

import pytest

from app.engine import Engine, apply_to_sandbox, validate_tool_proposal
from app.main import default_recipes
from app.policy import PolicyViolation, assert_dispatch_allowed, validate_loopback_url
from app.providers import AudarMtmdAdapter, LlamaCppAdapter, LocalArtifactRegistry
from app.schemas import Recipe, RunStatus, ToolProposal
from app.model_registry import ARTIFACT_STATES, scan_models
from app.download_status import read_worker_status
from tools.download_worker import queue_complete_allowed


def test_zero_spend_policy_blocks_remote_even_if_environment_has_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-authorize-dispatch")
    with pytest.raises(PolicyViolation, match="REMOTE_DISPATCH_BLOCKED"):
        assert_dispatch_allowed("openai")
    with pytest.raises(PolicyViolation, match="REMOTE_DISPATCH_BLOCKED"):
        assert_dispatch_allowed("humain")


def test_local_endpoint_allowlist_rejects_cloud_and_credential_urls():
    assert validate_loopback_url("http://127.0.0.1:11434").allowed
    assert not validate_loopback_url("https://api.example.com").allowed
    assert not validate_loopback_url("http://token@127.0.0.1:11434").allowed
    assert not validate_loopback_url("http://192.168.1.30:11434").allowed


def test_direct_local_adapters_require_a_verified_artifact(tmp_path):
    weight = tmp_path / "candidate.gguf"
    weight.write_bytes(b"not a model")
    manifest = tmp_path / "manifest.json"
    path = str(weight).replace("\\", "\\\\")
    manifest.write_text(f'{{"models":[{{"id":"bad","provider":"llama_cpp_local","roles":["function_call"],"artifacts":[{{"path":"{path}","sha256":"sha256:not-the-real-digest"}}]}}]}}', encoding="utf-8")
    adapter = LlamaCppAdapter(LocalArtifactRegistry(str(manifest)))
    assert adapter.status()["available"] is False
    with pytest.raises(PolicyViolation):
        assert_dispatch_allowed("llama_cpp_local", artifact_verified=False)


def test_audar_provider_is_local_only_and_absent_until_manifest_and_runtime_exist(tmp_path):
    adapter = AudarMtmdAdapter(LocalArtifactRegistry(str(tmp_path / "missing.json")))
    binding = adapter.binding()
    assert binding.available is False
    assert "manifest" in (binding.unavailable_reason or "")
    assert_dispatch_allowed("audar_mtmd_local", artifact_verified=True)


def test_recipe_graph_rejects_unknown_stage_and_preserves_independent_stages():
    direct, staged = default_recipes()
    assert direct.graph == ["function_call"]
    assert staged.graph == ["actionize", "function_call"]
    body = direct.model_dump(mode="json")
    body["graph"] = ["transcribe", "made_up_stage"]
    with pytest.raises(ValueError, match="UNKNOWN_PIPELINE_STAGE"):
        Recipe.model_validate(body)


def test_artifact_scanner_is_passive_and_reports_not_installed_without_auto_activation(tmp_path):
    scanned = scan_models([tmp_path])
    assert scanned
    assert all(entry["artifact_state"] in ARTIFACT_STATES for entry in scanned)
    assert all(entry["auto_activation"] is False for entry in scanned)
    assert next(entry for entry in scanned if entry["id"] == "AUDAR_TURBO_Q4_LOCAL_BRIDGE")["artifact_state"] == "NOT_INSTALLED"


def test_download_worker_status_distinguishes_stale_from_stopped(tmp_path):
    status = tmp_path / "worker-status.json"
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    status.write_text(json.dumps({"pid": 999999, "state": "DOWNLOADING", "last_heartbeat": old}), encoding="utf-8")
    assert read_worker_status(status)["effective_state"] == "STALE"
    status.write_text(json.dumps({"pid": 999999, "state": "QUEUE_COMPLETE", "last_heartbeat": old}), encoding="utf-8")
    assert read_worker_status(status)["effective_state"] == "STOPPED"


def test_download_queue_cannot_complete_with_pending_or_retryable_items():
    assert queue_complete_allowed(["INTEGRITY_VERIFIED", "BLOCKED_ACCESS", "FAILED_RETRY_EXHAUSTED"])
    assert not queue_complete_allowed(["INTEGRITY_VERIFIED", "RETRY_PENDING"])
    assert not queue_complete_allowed(["INTEGRITY_VERIFIED", "QUEUED"])


def test_direct_and_two_stage_recipes_record_different_real_stage_counts():
    direct, two_stage = default_recipes()
    text = "حط milk وقهوة في قائمة المقاضي"
    direct_result = Engine().run(direct, text, "2026-09-11T09:00:00+03:00")
    two_stage_result = Engine().run(two_stage, text, "2026-09-11T09:00:00+03:00")
    assert direct_result.outputs["proposal"]["tool_name"] == "add_list_items"
    assert direct_result.invocation_counts == {"summarize": 1, "function_call": 1}
    assert two_stage_result.outputs["semantic_plan"]["intent"] == "ADD_LIST_ITEMS"
    assert two_stage_result.invocation_counts == {"summarize": 1, "actionize": 1, "function_call": 1}
    assert direct_result.outputs["proposal"]["tool_mode"] == "JSON_EMULATION"


def test_correction_and_ambiguity_are_preserved_instead_of_inventing_meridiem():
    direct, _ = default_recipes()
    proposal = Engine().run(direct, "ذكّرني بكرة الساعة ثمانية، لا خليها تسعة", "2026-09-11T09:00:00+03:00").outputs["proposal"]
    assert proposal["status"] == RunStatus.NEEDS_CLARIFICATION.value
    assert proposal["tool_name"] == "request_clarification"
    assert proposal["arguments"]["missing_fields"] == ["AM/PM"]


def test_negation_does_not_become_a_reminder():
    direct, _ = default_recipes()
    proposal = Engine().run(direct, "لا تسوي تذكير، بس لخّص اللي قلته", "2026-09-11T09:00:00+03:00").outputs["proposal"]
    assert proposal["status"] == RunStatus.NO_ACTION.value
    assert proposal["tool_name"] is None


def test_strict_tool_schema_and_duplicate_apply():
    proposal = ToolProposal.model_validate({
        "id": "proposal-1", "status": "READY", "tool_name": "add_list_items",
        "arguments": {"list_name": "shopping", "items": ["milk"]}, "source_revision": 1,
        "supporting_spans": [], "tool_mode": "JSON_EMULATION", "evidence_type": "DEMO_RULES",
    })
    state = {"notes": [], "reminders": [], "lists": {}, "applied_proposal_ids": []}
    state, status = apply_to_sandbox(state, proposal)
    assert status == "APPLIED" and state["lists"]["shopping"] == ["milk"]
    state, status = apply_to_sandbox(state, proposal)
    assert status == "ALREADY_APPLIED" and state["lists"]["shopping"] == ["milk"]
    invalid = proposal.model_copy(update={"arguments": {"list_name": "shopping", "items": ["milk"], "extra": "no"}})
    with pytest.raises(ValueError, match="TOOL_ARGUMENTS_MUST_MATCH_SCHEMA_EXACTLY"):
        validate_tool_proposal(invalid)


def test_fixture_answer_key_is_not_needed_by_candidate_execution():
    data = json.loads(open("fixtures/authored_smoke.json", encoding="utf-8").read())
    direct, _ = default_recipes()
    case = data["cases"][0]
    proposal = Engine().run(direct, case["text"], "2026-09-11T09:00:00+03:00").outputs["proposal"]
    assert proposal["arguments"]["items"] == ["milk", "قهوة"]


def test_all_authored_smoke_actions_match_the_deterministic_reference_contract():
    data = json.loads(open("fixtures/authored_smoke.json", encoding="utf-8").read())
    direct, _ = default_recipes()
    for case in data["cases"]:
        proposal = Engine().run(direct, case["text"], "2026-09-11T09:00:00+03:00").outputs["proposal"]
        assert proposal["status"] == case["expected"]["status"], case["id"]
        assert proposal["tool_name"] == case["expected"]["tool_name"], case["id"]
        for key, value in case["expected"]["arguments"].items():
            assert proposal["arguments"].get(key) == value, case["id"]
