# Saudi STA Slice 02 — pre-Qwen milestone evidence

Date: 2026-09-12 (Asia/Riyadh)

Evidence class: local-only machine and browser evidence. This is not a
population-level Saudi benchmark and does not claim a general quality winner.

## Freshness and repository gates

- Checkout: `main`, not detached.
- Local HEAD before the milestone commit: `29bc8f15fbda2b04a5383ef9bd9d59d98416f8ee`.
- No Git remote is configured, so remote freshness cannot be established:
  `REMOTE_FRESHNESS_BLOCKER`.
- No stashes were present.
- Private recordings and runtime state remain outside Git; model weights and
  downloader temporary files are not part of this milestone.

## Verification

- Full suite: **56 passed, 1 warning** (`StarletteDeprecationWarning` for the
  installed `httpx` compatibility path).
- JavaScript syntax: `node --check static/app.js` passed.
- `git diff --check` passed before the milestone commit.

## Runtime-certified speech models

Existing sufficient real-local evidence was reused where it remained valid;
the same input identity and provenance are retained by the current runtime
adapters and tournament report.

| Model | Runtime evidence | Shared real input | Result |
|---|---|---|---|
| Whisper Large v3 | Transformers CPU, pinned revision and two shard hashes in `audit/slice02-real-local-smoke.md` | `${MODEL_ROOT}/whisper/FusHa.wav` | private transcript redacted; cold load ~4,686 ms, inference ~12,733 ms |
| Audar Turbo Q4 | llama.cpp mtmd, decoder/projector hashes in `audit/slice02-audar-q4-real-local-smoke.md` | same input | private transcript redacted; ~2.5 s end-to-end smoke |
| Audar Turbo Q8 | llama.cpp mtmd, decoder/projector hashes in `audit/slice02-stt-stage-tournament.md` | same input | private transcript redacted; 5,635.41 ms measured wall time |
| Audar Flash Q8 | llama.cpp mtmd, decoder/projector hashes in `audit/slice02-stt-stage-tournament.md` | same input | private transcript redacted after native-prefix normalization; 6,650.47 ms measured wall time |

FireRedVAD remains `RUNTIME_PENDING` because the required `cmvn.ark`
artifacts/runtime module are unavailable; no speech boundaries were invented.
Audar Diarization V1 remains `RUNTIME_PENDING` because its runtime config/loader
is unavailable; no diarization quality evidence was synthesized. LiveKit’s ONNX
artifact has load evidence, but its tokenizer/turn protocol is not available, so
completed/pause/continuation capability remains pending and distinct from VAD.

## STT tournament and evaluation

The tournament runs the same audio identity through all successfully bound
Whisper/Audar candidates and stores exact model/artifact hashes, quantization,
runtime, raw and normalized transcripts, cold/warm state, load/inference/total
latency, diagnostics, failures/timeouts, edit counts, and critical error
categories. Disagreements are captured without majority voting and
`calibrated_correctness` remains `null`.

Without a human reference, quality is explicitly
`INSUFFICIENT_HUMAN_EVIDENCE`; Performance returns
`NO_COMPARABLE_HUMAN_EVIDENCE`. Speed may report a narrow result for the
specific measured clip. Local monetary cost is a tie at API cost `0`, with
secondary criteria documented. Manual mode binds Whisper, Audar Q4, Audar Q8,
or Audar Flash directly without optimizer override.

Human-reviewed cases compute WER, CER, substitutions, deletions, insertions,
and separate number/name/negation/self-correction/code-switch critical errors.
Original strings remain alongside normalized strings. The dataset label is
`SEED_HUMAN_EVAL`; no population claim is made.

## Recording and browser evidence

The in-app browser at `http://127.0.0.1:8080/` visibly exercised:

- the 30-case `SEED_HUMAN_EVAL` queue with intent, semantic facts, broad
  outcome, clarification flag, and optional natural phrasing;
- local audio staging, replay, and explicit save;
- saved identity for `FusHa.wav`: SHA-256
  `9c81982b09ee2a762d5bd24d02e9965220e057cb2b21fd6e89af2b676fcc84fe`,
  duration 6.2 s;
- explicit states `RECORDED`, `MODEL_TRANSCRIBED`,
  `HUMAN_TRANSCRIPT_REVIEWED`, and `SEMANTIC_REFERENCE_REVIEWED` in the review
  workflow;
- four STT candidates, Speed/Cost/Performance/Manual selectors, and manual
  binding choices.

The UI keeps original audio/model outputs, human transcript, semantic
reference, expected action, critical spans, and provenance separate. The
microphone permission path was not invoked by automation; local file
upload/replay/save was verified instead.

## Stages, actions, and adapter readiness

The stage graph supports independently bound or omitted/bypassed `vad`,
`turn_detection`, `diarization`, `transcribe`, `summarize`, `actionize`,
`function_call`, `verify`, and `synthesize` stages with explicit state and
provenance. Safe local tools are schema-validated for note/reminder drafts,
revision, cancellation, list additions, and clarification. Proposals require
source revision/spans, tool and arguments, missing fields, and provenance;
unknown tools, unexpected arguments, invented recipients/dates/meridiem, stale
proposals, and duplicate Apply effects are rejected or idempotently suppressed.

The generic llama.cpp/GGUF adapter is ready for completion/chat, system/user
messages, JSON Schema constraints, native tool calls, structured tool
emulation, reasoning/context/timeout/cancellation, load/unload, usage/latency,
and artifact revision/hash provenance. Native tool calls and emulation remain
distinct. Adapter fakes are confined to clearly labeled regression fixtures.

## Qwen handoff readiness

The exact Qwen artifact identity is pinned in code:

- file: `Qwen3.8-27B-UD-Q6_K_L.gguf`
- expected bytes: `24,193,919,904`
- expected SHA-256:
  `121355b4c7422771da25adc74090e3c90138f77ce5c92d348687d47824ec80f4`

The scanner and local manifest adapter only admit the final artifact after a
verified downloader-manifest state; they do not inspect or hash downloader
temporary files. The certification suite is ready for Arabic, Saudi colloquial
Arabic, code switching, summarization, actionization, structured output, tool
selection, argument extraction, correction, negation, clarification, revision,
and cancellation. Failed role probes leave the role uncertified.

Direct and staged experiment recipes are ready:

`STT → function_call`

`STT → actionize → function_call`

The summary branch runs from the original transcript and cannot become the
function-call evidence source. Scoring covers action/argument correctness,
invented fields, correction/negation preservation, clarification, latency, and
failure rate; calibrated correctness remains `null` until human evidence exists.

No Qwen integration or certification was started in this milestone.
