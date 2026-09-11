# Saudi STA Slice 02 — runtime and route continuation

Date: 2026-09-12 Asia/Riyadh

Evidence class: local-only, machine-observed evidence.  This is not a
representative Saudi benchmark and does not claim a general quality winner.

## Freshness gate

- Repository: `<PRIVATE_WORKSPACE>`
- Checkout: `main`, not detached.
- Fetch attempt: completed with exit code 0, but the repository has no Git
  remote configured and no remote-tracking default branch was available.
- Status: `REMOTE_FRESHNESS_BLOCKER`; local `main` must not be described as
  current remote truth.

## Machine checks

- Test suite: 29 passed, 1 existing deprecation warning.
- Browser: local `Saudi STA · Workbench` opened at `http://127.0.0.1:8000/`.
- Browser smoke: direct route executed, local sandbox proposal applied and
  returned `APPLIED`; no hosted inference was contacted.  Run results now
  include explicit stage-route evidence for executed and bypassed stages.
- Seed UI: 30 scenario buttons rendered; recording upload displayed
  `WAV_SERVER_VERIFIED · LOCAL_SPEECH_AVAILABLE` and retained the audio in the
  application-managed private runtime directory.

## Optional speech-stage probes

| Stage | Artifact state | Runtime state | Capability state | Evidence / blocker |
|---|---|---|---|---|
| FireRedVAD | `ARTIFACT_PRESENT` | `RUNTIME_PENDING` | `CAPABILITY_PENDING` | Three weight files hash-verified; the manifest still lists `VAD/cmvn.ark`, `Stream-VAD/cmvn.ark`, and `AED/cmvn.ark` as planned/missing, and no runtime module is configured. |
| LiveKit turn detector v1-mini | `INTEGRITY_VERIFIED` | `RUNTIME_LOAD_VERIFIED` | `CAPABILITY_PENDING` | Pinned revision `fba34c38ad5d30a63ebb83a9e6bf271cf4c91d67`; `model_quantized.onnx` is 165,035,487 bytes with SHA-256 `4e685767c3643b0363c9f826a98325683f29e9c7d550162c8e8740ba33aa31aa`; ONNX input/output metadata loaded; tokenizer/turn-protocol bundle is absent, so completed/pause/continuation behavior is not claimed. |
| Audar Diarization V1 | `ARTIFACT_PRESENT` | `RUNTIME_PENDING` | `CAPABILITY_PENDING` | `model.safetensors` is 471,103,752 bytes and hash-verified; `config.yaml` and `load_diarizer.py` remain planned/missing. |

No VAD, turn-decision, or diarization output was fabricated from an artifact
load.  The three optional stages remain unavailable for route selection.

## STT evidence

The same local `D:\models\whisper\FusHa.wav` was already measured in
`audit/slice02-stt-stage-tournament.md` with Whisper Large v3, Audar Turbo Q4,
Audar Turbo Q8, and Audar Flash Q8.  The three Audar candidates produced the
same observed transcript for that one clip; Whisper produced the same words
without the final punctuation.  The report remains `INSUFFICIENT_HUMAN_EVIDENCE`
for quality selection.  The browser now renders Human, Whisper, and Audar
columns with WER/CER, latency, speech-error labels, disagreements, and
aggregates once a human reference is entered.

## Semantic/action readiness

- The generic local GGUF adapter exposes chat completion and raw completion,
  explicit load/unload, schema-constrained JSON, distinct native-tool and
  JSON-emulation modes, optional reasoning format, cancellation/timeout,
  context metadata, artifact hash identity, load/inference timings, and usage.
- The Qwen certification matrix is ready for correction, negation, Arabic /-
  English code switching, summary-only, and ambiguity cases across
  `summarize`, `actionize`, `function_call`, and `verify`.
- Current API result: `WAITING_FOR_QWEN_ARTIFACT`; no Qwen certification claim
  has been made while the GGUF is incomplete.

## Safety boundary

No verified artifact was modified or redownloaded in this continuation.  The
download worker and supervisor were read only; the downloader owns transfer,
manifest, and heartbeat state, while this implementation owns runtime and
route evidence.  At `2026-09-12 00:28:21 +03:00`, the worker status reported
Qwen at `24,533,727,392 / 24,193,919,904` bytes (`101.4%`) while still marked
`DOWNLOADING`; its process remained present but nearly idle.  This is recorded
as a downloader-side inconsistency and was not corrected here because this
Slice 02 continuation explicitly excludes download-orchestration changes.

The local API was restarted after the earlier hung cold Whisper browser
request and is listening on `127.0.0.1:8000` (server worker PID `3176`).
