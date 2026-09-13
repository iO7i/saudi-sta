# Detached download worker evidence

The model downloader is intentionally separate from application execution.

- Worker code: `tools/download_worker.py`
- Supervisor: `tools/download_supervisor.py`
- External state: `${MODEL_ROOT}/_downloads/manifest.json`, `worker-status.json`, `download-log.jsonl`, and `worker.lock`
- Model artifacts never enter Git.
- The worker invokes only pinned public file URLs with exact local paths, resumable `.part` files, byte-count checks, and SHA-256 checks.
- The worker does not import the application, load models, run inference, activate routes, or install runtimes.
- `app.download_status.read_worker_status()` classifies a manifest as `ACTIVE`, `STALE`, `STOPPED`, or `FAILED` using both heartbeat age and PID liveness.
- An atomic lock prevents two workers from owning the queue simultaneously. The supervisor waits for the current worker to exit before launching a fresh worker against the same external state.

Current bridge evidence (2026-09-11): Audar Flash decoder and BF16 projector are integrity-verified; FireRedVAD hashed weight artifacts are integrity-verified; Audar Diarization V1 `model.safetensors` is actively resumable; Audar Turbo Q8 is next in the resolved queue. The twelve temporary Audar Flash decoder chunks were deleted only after the assembled file's expected size and SHA-256 were verified.
