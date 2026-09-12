import hashlib
import io
import json

import pytest

from tools import download_supervisor
from tools import download_worker


class FakeResponse(io.BytesIO):
    def __init__(self, body, *, status=200, headers=None, url="https://example.test/artifact"):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}
        self.url = url

    def getcode(self):
        return self.status


def item_for(tmp_path, payload, *, etag='"v1"'):
    final = tmp_path / "artifact.bin"
    return {
        "model": "fixture/model",
        "label": "Fixture",
        "candidate_id": "FIXTURE",
        "revision": "fixture-revision",
        "file": final.name,
        "url": "https://example.test/artifact",
        "path": final,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "etag": etag,
    }


def opener_for(response, seen=None):
    def opener(request, timeout=60):
        if seen is not None:
            seen.append(request)
        return response

    return opener


def test_clean_download_writes_only_validated_response(tmp_path):
    payload = b"clean-artifact"
    item = item_for(tmp_path, payload)
    seen = []
    response = FakeResponse(payload, headers={"Content-Length": str(len(payload)), "ETag": '"v1"'})

    current, identity = download_worker.transfer_once(
        item, item["path"], offset=0, opener=opener_for(response, seen)
    )

    assert current == len(payload)
    assert item["path"].read_bytes() == payload
    assert identity["etag"] == '"v1"'
    assert seen[0].get_header("Accept-encoding") == "identity"
    assert seen[0].get_header("Range") is None


def test_resume_uses_actual_filesystem_offset_and_strict_range(tmp_path):
    payload = b"resume-artifact"
    item = item_for(tmp_path, payload)
    item["path"].write_bytes(payload[:6])
    seen = []
    suffix = payload[6:]
    response = FakeResponse(
        suffix,
        status=206,
        headers={
            "Content-Length": str(len(suffix)),
            "Content-Range": f"bytes 6-{len(payload) - 1}/{len(payload)}",
            "ETag": '"v1"',
        },
    )

    current, _ = download_worker.transfer_once(
        item,
        item["path"],
        offset=item["path"].stat().st_size,
        previous_identity={"etag": '"v1"'},
        opener=opener_for(response, seen),
    )

    assert current == len(payload)
    assert item["path"].read_bytes() == payload
    assert seen[0].get_header("Range") == "bytes=6-"
    assert seen[0].get_header("If-range") == '"v1"'


def test_resume_http_200_is_rejected_without_appending(tmp_path):
    payload = b"resume-artifact"
    item = item_for(tmp_path, payload)
    item["path"].write_bytes(payload[:6])
    response = FakeResponse(payload, headers={"Content-Length": str(len(payload)), "ETag": '"v1"'})

    with pytest.raises(download_worker.ResumeNotHonored):
        download_worker.transfer_once(
            item,
            item["path"],
            offset=6,
            previous_identity={"etag": '"v1"'},
            opener=opener_for(response),
        )

    assert item["path"].read_bytes() == payload[:6]


@pytest.mark.parametrize(
    "content_range",
    ["bytes 5-9/10", "bytes 6-9/11", "not-a-range"],
)
def test_resume_rejects_wrong_content_range_before_writing(tmp_path, content_range):
    payload = b"0123456789"
    item = item_for(tmp_path, payload)
    item["path"].write_bytes(payload[:6])
    response = FakeResponse(
        payload[6:],
        status=206,
        headers={"Content-Length": "4", "Content-Range": content_range, "ETag": '"v1"'},
    )

    with pytest.raises(download_worker.DownloadProtocolError):
        download_worker.transfer_once(
            item,
            item["path"],
            offset=6,
            previous_identity={"etag": '"v1"'},
            opener=opener_for(response),
        )

    assert item["path"].read_bytes() == payload[:6]


def test_changed_etag_fails_closed(tmp_path):
    payload = b"etag-artifact"
    item = item_for(tmp_path, payload)
    item["path"].write_bytes(payload[:3])
    response = FakeResponse(
        payload[3:],
        status=206,
        headers={"Content-Length": str(len(payload) - 3), "Content-Range": f"bytes 3-{len(payload)-1}/{len(payload)}", "ETag": '"v2"'},
    )

    with pytest.raises(download_worker.ArtifactIdentityChanged):
        download_worker.transfer_once(
            item,
            item["path"],
            offset=3,
            previous_identity={"etag": '"v1"'},
            opener=opener_for(response),
        )

    assert item["path"].read_bytes() == payload[:3]


def test_accept_encoding_identity_is_required(tmp_path):
    payload = b"encoding-artifact"
    item = item_for(tmp_path, payload)
    response = FakeResponse(payload, headers={"Content-Length": str(len(payload)), "Content-Encoding": "gzip"})

    with pytest.raises(download_worker.DownloadProtocolError, match="CONTENT_ENCODING_NOT_IDENTITY"):
        download_worker.transfer_once(item, item["path"], offset=0, opener=opener_for(response))

    assert not item["path"].exists()


def test_hard_size_ceiling_prevents_oversized_partial(tmp_path):
    payload = b"12345"
    item = item_for(tmp_path, payload)
    response = FakeResponse(payload + b"extra", headers={})

    with pytest.raises(download_worker.OversizeTransfer):
        download_worker.transfer_once(item, item["path"], offset=0, opener=opener_for(response))

    assert item["path"].stat().st_size <= len(payload)


def test_connection_failure_keeps_durable_prefix_for_safe_resume(tmp_path):
    payload = b"connection-artifact"
    item = item_for(tmp_path, payload)

    class FailsAfterPrefix(FakeResponse):
        def __init__(self):
            super().__init__(b"prefix", headers={})
            self.calls = 0

        def read(self, size=-1):
            self.calls += 1
            if self.calls == 1:
                return super().read(size)
            raise TimeoutError("connection dropped")

    with pytest.raises(download_worker.TransientDownloadError):
        download_worker.transfer_once(item, item["path"], offset=0, opener=opener_for(FailsAfterPrefix()))

    assert item["path"].read_bytes() == b"prefix"


def test_stale_status_does_not_change_filesystem_resume_offset(tmp_path):
    payload = b"filesystem-truth"
    item = item_for(tmp_path, payload)
    item["path"].write_bytes(payload[:4])
    seen = []
    response = FakeResponse(
        payload[4:],
        status=206,
        headers={"Content-Length": str(len(payload) - 4), "Content-Range": f"bytes 4-{len(payload)-1}/{len(payload)}", "ETag": '"v1"'},
    )

    download_worker.transfer_once(
        item,
        item["path"],
        offset=item["path"].stat().st_size,
        previous_identity={"etag": '"v1"'},
        opener=opener_for(response, seen),
    )

    assert seen[0].get_header("Range") == "bytes=4-"


def test_artifact_lock_rejects_second_live_writer(tmp_path):
    partial = tmp_path / "artifact.bin.part"
    first = download_worker.acquire_artifact_lock(partial, "worker-one")
    try:
        with pytest.raises(download_worker.DownloadError, match="ARTIFACT_ALREADY_OWNED"):
            download_worker.acquire_artifact_lock(partial, "worker-two")
    finally:
        download_worker.release_artifact_lock(first)


def test_final_size_without_hash_is_not_verified(tmp_path):
    payload = b"expected"
    item = item_for(tmp_path, payload)
    item["path"].write_bytes(b"mismatch")
    assert item["path"].stat().st_size == len(payload)
    assert download_worker.final_is_verified(item, item["path"]) is False


def test_quarantine_preserves_invalid_partial_and_records_evidence(tmp_path, monkeypatch):
    payload = b"invalid-partial"
    item = item_for(tmp_path, payload)
    partial = tmp_path / "artifact.bin.part"
    partial.write_bytes(payload + b"x")
    log_path = tmp_path / "download-log.jsonl"
    monkeypatch.setattr(download_worker, "LOG", log_path)

    quarantined = download_worker.quarantine_partial(item, partial, reason="TEST_INVALID")

    assert not partial.exists()
    assert quarantined.read_bytes() == payload + b"x"
    event = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert event["state"] == "INVALID_PARTIAL_QUARANTINED"
    assert event["expected_sha256"] == item["sha256"]


def test_supervisor_queue_complete_requires_all_frozen_items_terminal(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    monkeypatch.setattr(download_supervisor, "MANIFEST", manifest)
    manifest.write_text(json.dumps({"frozen_queue": [
        {"model": "a", "state": "INTEGRITY_VERIFIED"},
        {"model": "b", "state": "RETRY_PENDING"},
    ]}), encoding="utf-8")
    assert download_supervisor.queue_complete() is False
    manifest.write_text(json.dumps({"frozen_queue": [
        {"model": "a", "state": "INTEGRITY_VERIFIED"},
        {"model": "b", "state": "BLOCKED_ACCESS"},
    ]}), encoding="utf-8")
    assert download_supervisor.queue_complete() is True


def test_supervisor_restart_event_contains_causal_fields(tmp_path, monkeypatch):
    log_path = tmp_path / "supervisor-events.jsonl"
    monkeypatch.setattr(download_supervisor, "SUPERVISOR_LOG", log_path)
    download_supervisor.supervisor_log({
        "event": "WORKER_EXITED",
        "generation_id": "worker-test",
        "pid": 123,
        "exit_code": 1,
        "restart_reason": "WORKER_EXITED_WITH_PENDING_QUEUE",
        "durable_local_bytes": 7,
        "tracked_bytes": 6,
        "retry_number": 2,
        "source": "fixture/model",
        "etag": '"v1"',
        "next_resume_offset": 7,
    })
    event = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert event["restart_reason"] == "WORKER_EXITED_WITH_PENDING_QUEUE"
    assert event["durable_local_bytes"] == 7
    assert event["next_resume_offset"] == 7
