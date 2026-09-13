# Slice 02 STT stage tournament — Recording 15 — 2026-09-13

Evidence class: `REAL_LOCAL_MODEL`. This is a same-audio local runtime
comparison, not a representative Saudi benchmark and not a human-gold quality
ranking.

## Input

- Source: private `Recording (15).m4a`, uploaded to the local server as a managed
  recording; audio SHA-256 `650f1a03da6ed23a0985e2c7b399dc813476d4dc914d947aa342362fa9eefebc`.
- Duration: 8.789542 seconds.
- Tournament report: `ee850274-2a2b-4b14-955f-ec44556563df`.
- Runtime: pinned local llama.cpp mtmd path, offline, loopback-only server.
- Human reference: not entered; `dataset_id=UNREVIEWED_LOCAL_RECORDING`.

## Observations

| Candidate | Result | Transcript | Complete latency |
|---|---|---|---:|
| `AUDAR_TURBO_Q4_LOCAL_BRIDGE` | READY | `<REDACTED_PRIVATE_TRANSCRIPT>` | 21,092.27 ms |
| `AUDAR_TURBO_Q8_LOCAL` | READY | `<REDACTED_PRIVATE_TRANSCRIPT>؟` | 15,471.78 ms |
| `AUDAR_FLASH_Q8_LOCAL` | READY | `<REDACTED_PRIVATE_TRANSCRIPT>` | 9,037.09 ms |
| `WHISPER_LARGE_V3` | FAILED | unavailable: transformers and torch runtime required | 0.11 ms |

All three Audar outputs preserve the same words. Punctuation differences remain
in the raw and normalized provider records; they were not silently treated as
human truth. The stage report recorded no disagreement regions among ready
outputs, `majority_vote_used=false`, and `calibrated_correctness=null`.

Selection was deliberately `NO_COMPARABLE_HUMAN_EVIDENCE` with
`INSUFFICIENT_HUMAN_EVIDENCE`; Flash is only the observed speed candidate for
this one unreviewed recording, not a general quality winner. Monetary local
inference cost is 0 for every ready candidate.

The full JSON report, including artifact hashes, runtime diagnostics, raw
provider output, and failure status, is retained outside Git at
`D:\saudi-sta-slice02-stt-recording15.json`.
