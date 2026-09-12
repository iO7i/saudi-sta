import threading
import time
import tempfile
import os
import pytest

os.environ.setdefault("SAUDI_STA_DATA_DIR", tempfile.mkdtemp(prefix="saudi-sta-closeout-"))

from fastapi.testclient import TestClient
import app.main as main

from app.jobs import LocalJobManager
from app.engine import Engine, validate_tool_proposal
from app.providers import AudarMtmdAdapter
from app.schemas import CapabilityProvenance, ExecutionMode, Role, RoleBinding


def _wait_for(manager: LocalJobManager, job_id: str, states: set[str], timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job and job["status"] in states:
            return job
        time.sleep(0.01)
    return manager.get(job_id)


def test_local_job_timeout_sets_state_and_signals_worker():
    seen = threading.Event()

    def work(cancel_event):
        cancel_event.wait(2)
        seen.set()
        return {"partial": True}

    manager = LocalJobManager(default_timeout_seconds=0.05)
    job = manager.submit(work, timeout_seconds=0.05)
    finished = _wait_for(manager, job["id"], {"timed_out"})
    assert finished["status"] == "timed_out"
    assert finished["error"] == "LOCAL_JOB_TIMEOUT"
    assert seen.wait(1)


def test_local_job_publishes_timeout_before_non_cooperative_work_returns():
    release = threading.Event()

    def work(_cancel_event):
        release.wait(1)
        return {"late": True}

    manager = LocalJobManager(default_timeout_seconds=0.05)
    job = manager.submit(work, timeout_seconds=0.05)
    finished = _wait_for(manager, job["id"], {"timed_out"})
    assert finished["status"] == "timed_out"
    assert finished["error"] == "LOCAL_JOB_TIMEOUT"
    release.set()
    _wait_for(manager, job["id"], {"timed_out"})


def test_local_job_cancel_and_subsequent_submission_remain_usable():
    started = threading.Event()

    def work(cancel_event):
        started.set()
        cancel_event.wait(2)
        raise RuntimeError("cancelled child")

    manager = LocalJobManager(default_timeout_seconds=5)
    job = manager.submit(work, timeout_seconds=5)
    assert started.wait(1)
    cancelled = manager.cancel(job["id"])
    assert cancelled["cancel_requested"] is True
    finished = _wait_for(manager, job["id"], {"cancelled"})
    assert finished["status"] == "cancelled"

    follow_up = manager.submit(lambda _cancel_event: {"ok": True}, timeout_seconds=1)
    done = _wait_for(manager, follow_up["id"], {"completed"})
    assert done["status"] == "completed"
    assert done["result"] == {"ok": True}


def test_run_job_endpoint_returns_before_slow_local_work_finishes(monkeypatch):
    started = threading.Event()

    def slow_work(_body, *, cancel_event=None, route_timeout_seconds=None):
        started.set()
        cancel_event.wait(2)
        raise ValueError("LOCAL_ROUTE_CANCELLED")

    monkeypatch.setattr(main, "_run_workbench_sync", slow_work)
    client = TestClient(main.app)
    began = time.perf_counter()
    response = client.post("/api/runs/jobs", json={"text": "x", "recipe_id": "demo_direct_v1"})
    assert response.status_code == 200 and (time.perf_counter() - began) < 1
    job_id = response.json()["job_id"]
    assert started.wait(1)
    status = client.get(f"/api/runs/jobs/{job_id}").json()
    assert status["status"] in {"queued", "running"}
    client.post(f"/api/runs/jobs/{job_id}/cancel", json={})
    finished = _wait_for(main.local_jobs, job_id, {"cancelled"})
    assert finished["status"] == "cancelled"


def _qwen_binding():
    return RoleBinding(id="fixture:qwen:function_call", provider="llama_cpp_local", model_id="fixture-qwen", role=Role.FUNCTION_CALL,
                       prompt_version="qwen-json-v1", schema_version="sta-v2", execution_mode=ExecutionMode.LOCAL,
                       capability_provenance=CapabilityProvenance.VERIFIED_LOCAL, tool_mode="JSON_EMULATION")


class _FakeLocalAdapter:
    def __init__(self, content):
        self.content = content

    def invoke(self, binding, messages, **kwargs):
        return {"content": self.content, "tool_calls": [], "runtime_metrics": {"runtime": "fixture"}}


def test_json_emulation_strips_only_known_echo_envelope_and_keeps_strict_tool_schema():
    binding = _qwen_binding()
    engine = Engine(local_text_adapter=_FakeLocalAdapter('{"source_text":"echo","tool_name":"add_list_items","arguments":{"list_name":"shopping","items":["milk"]}}'))
    proposal = engine._function_call(binding, "حط milk", None, "2026-09-13T09:00:00+03:00", 1)
    assert proposal.tool_name == "add_list_items"
    assert proposal.arguments == {"list_name": "shopping", "items": ["milk"]}

    invalid = Engine(local_text_adapter=_FakeLocalAdapter('{"tool_name":"bring_water","arguments":{}}'))
    with pytest.raises(ValueError, match="UNKNOWN_TOOL"):
        validate_tool_proposal(invalid._function_call(binding, "جيب المويه", None, "2026-09-13T09:00:00+03:00", 1))


def test_audar_cli_parser_handles_empty_or_missing_decoded_output():
    assert AudarMtmdAdapter._text_from_cli(None) == ""
    assert AudarMtmdAdapter._text_from_cli("") == ""
