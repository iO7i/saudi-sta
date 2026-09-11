# Slice 02 — real local STT stage comparison

Evidence class: `REAL_LOCAL_MODEL`. This is a measured local runtime smoke
comparison, not a representative Saudi benchmark and not a leaderboard claim.

## Shared input

- Audio: `D:\models\whisper\FusHa.wav`
- Human reference: not yet entered in `SEED_HUMAN_EVAL`; therefore quality winner is `INSUFFICIENT_HUMAN_EVIDENCE`.
- Runtime: llama.cpp mtmd CLI, pinned Windows CPU x64 b10909, executable SHA-256 `88ec60c377e51c734c4c89e495a23946485674602f6126c79a01ce24240e2f9f`.
- Generation: temperature 0; Arabic transcription system prompt; local-only environment flags; no network endpoint.

## Candidates

| Candidate | Decoder SHA-256 | Projector SHA-256 | Observed transcript | Wall time (load + inference) |
|---|---|---|---|---:|
| `AUDAR_TURBO_Q4_LOCAL_BRIDGE` | `c55e3c28225ef6e9b56906a6463af62d34ed417803c45f3b7b20f463af2e8cf4` | `190459e806938175711779847eb62ea609cd78b8d2ec06fb96a94d69ab37a9be` | `<REDACTED_PRIVATE_TRANSCRIPT>` | ~2.5 s |
| `AUDAR_TURBO_Q8_LOCAL` | `0a91ab40f6a30db06c4186e2f621f504f4625ba6058e639cc09f1cbefded10d2` | `190459e806938175711779847eb62ea609cd78b8d2ec06fb96a94d69ab37a9be` | `<REDACTED_PRIVATE_TRANSCRIPT>` | 5635.41 ms PowerShell wall |
| `AUDAR_FLASH_Q8_LOCAL` | `1b01c707fcf162ef8e844a89f0833bd0d005933342e0c37fa8da164497a9fb38` | `73f06fc82a009b4a9d6c825782a3676cb553402b3a5ecc27ae77a92caa6b7fa9` | `<REDACTED_PRIVATE_TRANSCRIPT>` after native `language Arabic<asr_text>` prefix normalization | 6650.47 ms PowerShell wall |
| `WHISPER_LARGE_V3` | external manifest; two FP32 shards | n/a | `<REDACTED_PRIVATE_TRANSCRIPT>` | cold load ~4685.79 ms; inference ~12732.57 ms |

The three Audar candidates agree on this utterance. No candidate is declared a
general quality winner from this one audio sample. The application retains raw
output, normalized transcript, timing/segment fields when genuinely returned,
native signals (currently unavailable for these mtmd outputs), hashes, runtime,
and failure status per candidate.

## Next evidence needed

The human recording workflow now supplies scenario prompts and a side-by-side
review path. After human references are entered, the same stage tournament can
compute WER/CER and the speech error taxonomy without majority-voting model
outputs into truth.
