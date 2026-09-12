"""Machine-only pre-Qwen regression coverage.

The adapter test double below is a clearly labelled test fixture.  It never
stands in for runtime certification evidence or a human speech reference.
"""

import hashlib
import json

from app.engine import apply_to_sandbox
from app.model_registry import scan_models
from app.providers import LlamaCppAdapter, LocalArtifactRegistry
from app.qwen_certification import QWEN_CERTIFICATION_CASES, evaluate_qwen_output, qwen_route_experiment_plan
from app.schemas import CapabilityProvenance, ExecutionMode, Role, RoleBinding, ToolProposal
from app.store import Store
from app.stt_tournament import run_stt_tournament


class FakeBinding:
    def __init__(self, name: str, hashes: list[str] | None = None):
        self.id = name
        self.model_id = name
        self.provider = "audar_mtmd_local"
        self.revision_or_digest = f"rev-{name}"
        self.generation = {"precision": name, "runtime": "fixture-runtime"}
        self.available = True
        self.artifact_hashes = hashes or [f"sha256-{name}"]


def test_tournament_preserves_exact_input_and_independent_model_identity(tmp_path):
    audio = tmp_path / "same-input.wav"
    audio.write_bytes(b"same input identity")
    bindings = [FakeBinding("Q4", ["q4-hash"]), FakeBinding("Q8", ["q8-hash"]), FakeBinding("Flash", ["flash-hash"])]

    def transcribe(binding, _path):
        return {"text": "ذكرني 3", "model_load_ms": 4.0, "inference_latency_ms": 5.0, "total_latency_ms": 9.0, "cold_start": binding.id == "Q4", "provider_diagnostics": {"fixture": True}}

    report = run_stt_tournament(audio, bindings, transcribe, human_reference="ذكرني 4", mode="Speed")
    assert report["audio_identity"]["sha256"] == hashlib.sha256(audio.read_bytes()).hexdigest()
    assert {item["model_hash"] for item in report["candidates"]} == {"q4-hash", "q8-hash", "flash-hash"}
    assert all(item["total_latency_ms"] == 9.0 and item["inference_latency_ms"] == 5.0 for item in report["candidates"])
    assert report["candidates"][0]["word_edit_counts"]["substitutions"] == 1
    assert report["aggregates"]["critical_error_counts"]["number"] >= 3


def test_performance_requires_human_reference_and_all_modes_are_explicit(tmp_path):
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"audio")
    bindings = [FakeBinding("slow"), FakeBinding("fast")]
    transcribe = lambda binding, _path: {"text": binding.id, "latency_ms": 10.0 if binding.id == "slow" else 1.0}
    assert run_stt_tournament(audio, bindings, transcribe, mode="Performance")["selection"]["outcome"] == "NO_COMPARABLE_HUMAN_EVIDENCE"
    assert run_stt_tournament(audio, bindings, transcribe, mode="Cost")["selection"]["outcome"] == "MONETARY_TIE"
    assert run_stt_tournament(audio, bindings, transcribe, mode="Manual", manual_binding_id="slow")["selection"]["recommendation"] == "slow"
    assert run_stt_tournament(audio, bindings, transcribe, mode="Speed")["selection"]["recommendation"] == "fast"


def test_qwen_suite_is_exact_and_failed_role_probe_cannot_certify():
    by_id = {case["id"]: case for case in QWEN_CERTIFICATION_CASES}
    assert by_id["saudi_correction"]["text"] == "ذكرني بكرة الساعة ثمانية، لا خلها تسعة"
    assert by_id["saudi_negation"]["text"] == "اكتب رسالة لخالد إني بتأخر بس لا ترسلها"
    assert by_id["saudi_code_switching"]["expected"]["items"] == ["milk", "بيض", "protein bars"]
    failed = evaluate_qwen_output(by_id["saudi_correction"], "function_call", {"content": '{"hour": 8}'})
    passed = evaluate_qwen_output(by_id["saudi_correction"], "function_call", {"content": '{"hour": 9}'})
    assert failed["passed"] is False and passed["passed"] is True
    plan = qwen_route_experiment_plan()
    assert plan["direct"] == ["transcribe", "function_call"]
    assert plan["staged"] == ["transcribe", "actionize", "function_call"]
    assert "original_transcript" in plan["summary_branch"]["source"]


def test_store_apply_is_atomic_and_idempotent(tmp_path):
    store = Store(tmp_path)
    proposal = ToolProposal.model_validate({
        "id": "atomic-1", "status": "READY", "tool_name": "add_list_items",
        "arguments": {"list_name": "shopping", "items": ["milk"]}, "source_revision": 1,
        "supporting_spans": [], "tool_mode": "STRUCTURED_TOOL_EMULATION", "evidence_type": "REAL_LOCAL_MODEL",
    })
    first, first_status = store.apply_sandbox_once(proposal, apply_to_sandbox)
    second, second_status = store.apply_sandbox_once(proposal, apply_to_sandbox)
    assert first_status == "APPLIED"
    assert second_status == "ALREADY_APPLIED"
    assert first["lists"] == second["lists"] == {"shopping": ["milk"]}


def test_passive_qwen_manifest_maps_only_the_final_artifact(tmp_path, monkeypatch):
    final = tmp_path / "Qwen3.8-27B-UD-Q6_K_L.gguf"
    final.write_bytes(b"fixture-final-artifact")
    digest = hashlib.sha256(final.read_bytes()).hexdigest()
    downloads = tmp_path / "_downloads"
    downloads.mkdir()
    (downloads / "manifest.json").write_text(json.dumps({"queue": [{
        "model": "Qwen/Qwen3.8-27B", "candidate_id": "QWEN38_27B_Q6_K_L", "revision": "fixture-rev",
        "files": [{"name": final.name, "path": str(final), "bytes": final.stat().st_size, "sha256": digest, "status": "INTEGRITY_VERIFIED"}],
    }]}), encoding="utf-8")
    import app.model_registry as registry
    monkeypatch.setattr(registry, "PLANNED_MODELS", [{
        "id": "QWEN3_8_27B_Q6_K_L", "family": "Qwen3.8-27B", "stage": ["summarize"], "artifacts": [{"path": final.name, "expected_bytes": final.stat().st_size, "sha256": digest}],
        "artifact_root": "qwen/Qwen3.8-27B-Q6_K_L", "runtime_certified": False, "capability_certified": False,
    }])
    scanned = scan_models([tmp_path])[0]
    assert scanned["artifact_state"] == "INTEGRITY_VERIFIED"
    assert scanned["artifacts"][0]["integrity"] == "VERIFIED_BY_DOWNLOAD_MANIFEST"
    assert scanned["artifacts"][0]["path"] == str(final)


def test_gguf_fixture_keeps_native_and_structured_tool_modes_distinct(monkeypatch, tmp_path):
    weight = tmp_path / "model.gguf"
    weight.write_bytes(b"fixture-weight")
    digest = hashlib.sha256(weight.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"models": [{"id": "fixture", "provider": "llama_cpp_local", "roles": ["function_call"], "artifacts": [{"path": str(weight), "sha256": digest}]}]}), encoding="utf-8")
    adapter = LlamaCppAdapter(LocalArtifactRegistry(str(manifest)))

    class FixtureModel:
        def __init__(self):
            self.requests = []

        def create_chat_completion(self, **request):
            self.requests.append(request)
            return {"choices": [{"message": {"content": '{"status":"READY","tool_name":"create_note_draft","arguments":{}}'}}], "usage": {}}

    fixture_model = FixtureModel()
    adapter._model = fixture_model
    adapter._load = lambda _entry: False
    adapter.status = lambda _binding: {"available": True, "artifacts": [{"bytes": weight.stat().st_size, "sha256": digest}]}
    adapter._entry = lambda _binding: {"id": "fixture", "artifacts": [{"path": str(weight), "sha256": digest}]}
    base = {"id": "fixture:function_call", "provider": "llama_cpp_local", "model_id": "fixture", "role": Role.FUNCTION_CALL, "prompt_version": "fixture", "schema_version": "fixture", "execution_mode": ExecutionMode.LOCAL, "capability_provenance": CapabilityProvenance.VERIFIED_LOCAL}
    emulated = RoleBinding.model_validate({**base, "tool_mode": "STRUCTURED_TOOL_EMULATION"})
    native = RoleBinding.model_validate({**base, "tool_mode": "NATIVE_TOOL_CALL"})
    tools = [{"type": "function", "function": {"name": "create_note_draft", "parameters": {"type": "object"}}}]
    adapter.invoke(emulated, [{"role": "user", "content": "x"}], json_schema={"type": "object"}, tools=tools)
    assert "response_format" in fixture_model.requests[-1] and "tools" not in fixture_model.requests[-1]
    adapter.invoke(native, [{"role": "user", "content": "x"}], json_schema={"type": "object"}, tools=tools)
    assert "tools" in fixture_model.requests[-1] and "response_format" not in fixture_model.requests[-1]
