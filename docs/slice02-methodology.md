# Slice 02 real-local methodology

The workbench measures complete, named recipes rather than a single global model.
The three explicit recipes are:

- **Direct:** `STT → function_call`
- **Semantic:** `STT → actionize → function_call`
- **Semantic + summary:** `STT → actionize → function_call`, plus an independent
  summary branch. The function call receives the source transcript, not the summary.

Role bindings stay independent: `transcribe`, `summarize`, `actionize`, and
`function_call` may point to different verified local artifacts. A manual recipe is
never changed by the optimizer.

## Evidence separation

`AUTHORED_SMOKE_FIXTURE` only tests deterministic boundary contracts and remains
separate from `SEED_HUMAN_EVAL`. The latter contains local recordings and explicit
human references. A model output is never used as the expected answer for its own
evaluation.

## Metrics

Performance ranks end-to-end proposal correctness after sandbox validation. It also
retains STT WER/CER, critical-span accuracy, schema failures, clarification errors,
and the structured error taxonomy. A valid JSON object with the wrong tool or
arguments is a failure.

Speed records STT, each text stage, and end-to-end wall-clock time for every case.
Failures stay in the completion denominator. Cold/warm model-load details are
retained when a runtime exposes them.

All-local provider monetary inference cost is exactly `0`. Cost mode uses quality,
then accurately observed resource footprint, then latency to break that tie. No
electricity price is invented.

## Confidence

Whisper signals are stored only when returned by the implementation. The initial
Transformers pipeline exposes segment timestamps but not calibrated log-probability,
no-speech, compression-ratio, stability, or alternatives. `calibrated_correctness`
is always `null`. Text-model self-reported confidence is not treated as evidence.

| Signal | Source | Meaning | Available? | Calibrated? | Observed correctness association |
|---|---|---|---|---|---|
| Segment timestamps | Transformers Whisper pipeline | Approximate decoded segment placement | Yes when returned | No | Not fitted |
| Average log probability | Selected pipeline | Decoder likelihood summary | No | No | `null` |
| No-speech probability | Selected pipeline | Speech-presence diagnostic | No | No | `null` |
| Compression ratio | Selected pipeline | Repetition/pathology diagnostic | No | No | `null` |
| Segment stability | Selected pipeline | Agreement across decodes | No | No | `null` |
| Alternative decoding | Selected pipeline | Competing hypotheses | No | No | `null` |
| Text self-report | Local text model | Model statement about itself | Not used | No | `null` |

Automatic selective escalation, pseudo-label promotion, model training, and hosted
providers remain disabled in this slice.
