# Saudi STA Slice 02 closeout checkpoint — 2026-09-13

## Status

`SLICE_02_TECHNICAL_GREEN` is **not reached** in this checkpoint. The local
route infrastructure is bounded and browser-visible, but the available user
recordings did not produce a proposal for one of the intentionally safe local
sandbox tools, so no real-model Apply/readback proof is claimed.

`SLICE_02_EMPIRICAL_STATUS: HUMAN_RECORDING_REQUIRED`

## Proven in this checkpoint

- Full regression suite: **64 passed**, one existing Starlette deprecation
  warning.
- `node --check static/app.js`: passed.
- `git diff --check`: passed (only Git's LF/CRLF normalization warnings).
- Qwen3.8-27B local CPU generation remains certified for chat and JSON
  emulation under `STRICT_DETERMINISTIC_VALIDATION`; native grammar/tool calls
  remain uncertified.
- The asynchronous local route job exposes queued/running/completed/failed/
  cancelled/timed_out states, propagates cancellation, and publishes a timeout
  immediately when a deadline fires.
- Audar and llama.cpp subprocesses use explicit UTF-8 decoding with replacement
  so Arabic output cannot fail under the Windows cp1252 default. The fix was
  re-exercised on `Eng17.m4a` and `FusHa.m4a`.
- Browser UI loaded at `http://127.0.0.1:8765/` with independent Whisper,
  Audar Q4/Q8/Flash, and Qwen bindings visible; hosted providers remained
  disabled and no remote call was made.

## Real-route result

Recording (2) reached:

`REAL AUDIO → Audar Turbo Q4 → Qwen3.8-27B Q6_K_L → JSON emulation`

Strict validation returned `UNKNOWN_TOOL` for the physical request “bring me
water”. This is retained as a negative real-local result. Recordings (3–6)
were also real-transcribed, but were respectively profanity, an external
Wikipedia request, discussion, and a non-action/ambiguous utterance. No
proposal was applied, and no sandbox state was changed by these attempts.

The detailed hashes, transcripts, and failure evidence are in
`audit/slice02-real-route-attempts-2026-09-13.md`.

## Exact next input needed

Record one natural utterance that directly requests a supported local
operation, for example:

`<REDACTED_PRIVATE_TRANSCRIPT>`

Then review the verbatim transcript and expected list arguments in the Seed
Saudi Speech Set UI. That recording is required before claiming real
ToolProposal Apply/readback, duplicate-Apply idempotency, stale-rejection, or
an empirical Saudi quality winner.

## Safety and spend

- Amount spent: `0`
- Hosted inference calls: `0`
- Cloud resources/deployments: `0`
- Private recordings and model weights remain outside Git.
