# Saudi STA Slice 02 closeout checkpoint — 2026-09-13

## Status

The core real-route gate is now proven for Recording (15): real audio entered,
real Audar STT ran, real Qwen3.8 generated a strict local action proposal, and
the proposal was previewed, applied, read back, de-duplicated, and rejected
after a transcript revision. Full `SLICE_02_TECHNICAL_GREEN` closeout still
requires the remaining browser Apply journey and bounded Direct-vs-Staged plus
route-tournament evidence to be captured explicitly.

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

Follow-up recordings 7–12 were also transcribed locally. Recordings (7) and
(8) reached Qwen through the same direct recipe and both returned strict,
schema-valid `request_clarification` proposals. Recording (8) asks for the
missing note content; Recording (7) contains mixed list/note wording and an
unresolved “do this” phrase. This validates the real route and clarification
behavior, but still does not provide an Apply-eligible proposal.

Recording 13 was then attempted with the explicit list phrase. An initial
prompt-tightened Qwen run exceeded the bounded harness ceiling and was
cancelled. The cancelled short-lived harness left one confirmed Qwen child
orphaned (PID 44368); that exact pinned process was terminated. The local
subprocess adapters now register interpreter-exit child-tree cleanup in
addition to their normal cancellation/timeout kill path, preventing this
harness-exit orphan case from being silently retained.

Recording 15 supplied the first unambiguous supported action. Its complete
`REAL_LOCAL_END_TO_END` trace is archived in
`audit/slice02-real-route-attempts-2026-09-13.md`: Audar Q4 produced the exact
list-request transcript, Qwen returned `add_list_items` with `المقاضي`, `البيض`,
and `الحليب`, Apply returned `APPLIED`, the second identical Apply returned
`ALREADY_APPLIED`, and the old proposal returned HTTP 409 after transcript
revision 2. This proof used JSON emulation with strict deterministic
validation; native grammar and native tool calling remain uncertified.

## Remaining closeout evidence

The remaining empirical gap is human review: review/correct the verbatim
transcripts and expected actions in the Seed Saudi Speech Set UI before claiming
an empirical Saudi quality winner. The remaining technical evidence to capture
is the full browser Apply journey and a bounded Direct-vs-Staged / complete
route-tournament run; these are not inferred from the API trace.

## Safety and spend

- Amount spent: `0`
- Hosted inference calls: `0`
- Cloud resources/deployments: `0`
- Private recordings and model weights remain outside Git.
