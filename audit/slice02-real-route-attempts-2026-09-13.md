# Slice 02 — real-route attempts from user recordings

Evidence class: `REAL_LOCAL_MODEL` for ASR/Qwen execution; no successful
`REAL_LOCAL_END_TO_END` Apply trace was produced in this attempt set.

## Inputs

The user supplied five new local recordings under a private local recordings
directory (path redacted for publication):

| File | Bytes | SHA-256 | Audar Q4 observation |
|---|---:|---|---|
| `Recording (2).m4a` | 130,262 | `ede1282a1770c6ecc5f308867600243f457488b71c7c36e3695c6020bf35920d` | private transcript redacted; physical-action request |
| `Recording (3).m4a` | 170,663 | `680e60403a6d0ca891ce59f39b40cf48f0f1d6890594fc23057ae138850cc6b3` | profanity/no sandbox request |
| `Recording (4).m4a` | 254,792 | `5fb4a6967be38de43d0b5005d0faad6f8f601ccecd9b7c1e3815f72c089cde7d` | request to open Wikipedia (external action) |
| `Recording (5).m4a` | 441,797 | `f7baaf1bc15352ce409548c801d9c9f7ce1f58177e271f823aa68759c47f6659a` | discussion/no direct sandbox request |
| `Recording (6).m4a` | 254,550 | `d42a5c290090f7916d9b520649e383770c28ab298c8893e2008a9a5edfe9b85a` | request involving a person and tomorrow at 6 PM |

The original files remain private and outside Git. Non-WAV inputs are converted
to a temporary 16 kHz mono WAV solely for the local Audar runtime and cleaned
up asynchronously when Windows releases multimedia handles.

## Real route attempt

Recording (2) was uploaded through the application and run as:

`real audio → Audar Turbo Q4 → Qwen3.8-27B Q6_K_L → JSON emulation → strict ToolProposal validation`

The job was non-blocking and reached Qwen locally. The final status was:

`failed`

with exact application error:

`HTTPException:422: UNKNOWN_TOOL`

This is retained as a negative case. The utterance requests a physical action
(bring water), while the sandbox intentionally exposes only safe local tools
(`create_note_draft`, `create_reminder_draft`, `add_list_items`, draft revision/
cancellation, and clarification). No external or physical-world tool was
invented, and strict validation was not weakened.

The prior pre-normalization attempt on the same recording failed with extra
echoed context fields (`source_text` and related envelope data). The narrow
normalization now strips only those known non-action envelope keys; the rerun's
remaining `UNKNOWN_TOOL` failure proves the action mismatch is genuine rather
than an envelope parsing defect.

## Runtime boundary hardening

During a bounded read-only pass over older local recordings, Windows' default
`cp1252` subprocess decoding produced `UnicodeDecodeError` for Arabic llama.cpp
output and left `stdout` unset. The Audar and llama.cpp subprocess adapters now
request UTF-8 with replacement for diagnostics/output, and the Audar completion
parser treats empty output as an empty transcript. The fix was re-exercised on
`Eng17.m4a` and `FusHa.m4a`; both now return string transcripts locally without
changing the strict action contract.

## Gate status

- Real STT: proven on the supplied recordings.
- Real Qwen generation: reached and measured locally (CPU; Q6_K_L; JSON emulation).
- Strict ToolProposal: correctly rejected the unsupported tool.
- Proposal preview/Apply/readback: **not reached** for these recordings.
- Duplicate Apply and stale-proposal proof: **not reached** for these recordings.
- Human-reviewed references: `HUMAN_SAUDI_EVIDENCE = PENDING`.

To complete the Apply proof without changing the safety contract, record an
utterance that directly requests a supported local operation, for example:

private supported-list example (transcript redacted)

Then review the verbatim transcript and expected `add_list_items` arguments in
the Seed Saudi Speech Set UI. Do not label the current physical/external-action
recordings as successful sandbox actions.

## Follow-up recordings 7–12

The same Audar Q4 bridge transcribed six additional local recordings. Hashes,
durations, and outputs are retained here so these observations remain separate
from human-reviewed gold labels:

| File | Duration (s) | SHA-256 | Audar Q4 transcript / observation |
|---|---:|---|---|
| `Recording (7).m4a` | 9.088 | `b73e1765bd616b792a0185869d44919350a4733ea982415789b56bbe810a79f6` | private transcript redacted; mixed list/note wording; clarification required |
| `Recording (8).m4a` | 14.379 | `85a631def5988f9cad0c664db7a2fa4d16f206cbada17040f77842472ca434dc` | private transcript redacted; note intent, content boundary ambiguous; phone-like span redacted |
| `Recording (9).m4a` | 9.344 | `a45d181e8c2aa0098a34149d7b63fd77dc779e6036beef2a48d51902dd4212e0` | private transcript redacted; external group/invite request |
| `Recording (10).m4a` | 12.011 | `fe076ee72dfdc4bdadc42e04a29894c043a2b04c37fda2aee1bdc4626d48ba8a` | private transcript redacted; draft request with missing content |
| `Recording (11).m4a` | 9.408 | `978a220b7376c342f795274bf65e1e616a95e78782afbecdcdd88f01be37bee0` | private transcript redacted; no supported sandbox action |
| `Recording (12).m4a` | 6.101 | `ca2150ac429b77c276f72f862f9e265f439d208c3990bdbf63973d36e6a8d4e0` | private transcript redacted; calculation/save request outside the current tool set |

Two bounded real routes were then executed with the Q4 transcript and Qwen
Q6_K_L direct function-call recipe. Recording (8) produced a strict,
schema-valid `request_clarification` proposal asking for `note_content`;
Recording (7) produced a strict, schema-valid clarification asking for
`list_name`, the unresolved “سوي كذا” action, and `note_content`. Neither route
was Apply-eligible, so sandbox state was intentionally unchanged. Qwen's raw
responses, artifact hash, runtime, and stage latencies are retained in the
local SQLite route records under the configured runtime data directory.

## Recording 13

`Recording (13).m4a` was added with a private list-request phrase (transcript
redacted). The local file is 162,635 bytes, 6.357479 seconds, and
SHA-256 `c6a175bb1b4947624ab14d0c4a72d69c14518443f9150da83875b1b952e56ff7`.
The first Qwen run reached the model but returned the out-of-contract status
`OK`; strict validation rejected it. The prompt was then versioned to
`qwen-json-v2` with the exact allowed status enum spelled out. A second bounded
attempt exceeded the 330-second harness ceiling and was explicitly cancelled;
it produced no ToolProposal and no sandbox mutation. The confirmed orphaned
Qwen child from that short-lived harness was terminated, and exit-time child
cleanup was added to the adapters.

The same audio was independently transcribed by all three certified Audar
variants. The item words were preserved, but the shopping-list term varied
across variants. The private transcript and exact variants are redacted here;
the disagreement remains recorded as an observed STT error and is not
normalized without a human reference.

## Recordings 14–17 and first complete real Apply trace

Four additional private recordings were inspected with the certified Audar
variants. They remain outside Git and are not treated as human-reviewed gold:

| File | Bytes | Duration (s) | SHA-256 | Observation |
|---|---:|---:|---|---|
| `Recording (14).m4a` | 196,729 | 7.7015 | `2dabfdfca4f12ccdea35add92e508057bcced6adcc2bd2131bf79a91c74e571c` | list request for eggs; all variants preserved the intent |
| `Recording (15).m4a` | 224,128 | 8.7895 | `650f1a03da6ed23a0985e2c7b399dc813476d4dc914d947aa342362fa9eefebc` | unambiguous eggs-and-milk list request; used for Apply proof |
| `Recording (16).m4a` | 199,908 | 7.8295 | `9dd36ddca74e943661a13f6671d33d6333e74f7e42f0734190beda0557a4a922` | list request; all variants preserved eggs, milk, and list context |
| `Recording (17).m4a` | 189,543 | 7.4242 | `60cff5f6b61ba53e34e79e9b85483d40a8a8019b051eca3e24d21b04ebc40644` | list request; Q8/Flash had list-word transcription variants |

Recording (15) was run end-to-end in a fresh local runtime data directory as
recipe `real_audar_turbo_q4_local_bridge_qwen38_27b_q6_k_l_direct_v1`:

`REAL AUDIO → Audar Turbo Q4 → Qwen3.8-27B Q6_K_L → JSON emulation → strict ToolProposal`

The upload hash is `650f1a03da6ed23a0985e2c7b399dc813476d4dc914d947aa342362fa9eefebc`.
The real STT transcript is retained only in the private run record and is
redacted from this public evidence note.

Qwen ran locally with artifact hash
`sha256:121355b4c7422771da25adc74090e3c90138f77ce5c92d348687d47824ec80f4`,
llama.cpp build `b10909-a2878d30d`, prompt `qwen-json-v2`, schema validation,
reasoning disabled, temperature zero, and a 160-token bound. It returned a
strictly valid emulated tool proposal:

```json
{"status":"READY","tool_name":"add_list_items","arguments":{"list_name":"المقاضي","items":["البيض","الحليب"]}}
```

The route record is `c666a6b5-086c-4293-8ebc-3f5f5f551671`; the proposal ID is
`a31f0cb4-6a01-4e56-9b0c-fcc741501a47`. The Qwen stage took 139,199.703 ms
(139,177.189 ms model inference); the route record contains 8,238.770 ms for
the Audar stage. Before Apply, sandbox state was empty. Applying once returned
`APPLIED` and readback showed exactly:

```json
{"lists":{"المقاضي":["البيض","الحليب"]},"notes":[],"reminders":[],"applied_proposal_ids":["a31f0cb4-6a01-4e56-9b0c-fcc741501a47"]}
```

Applying the identical proposal again returned `ALREADY_APPLIED` and did not
duplicate either item. Editing the transcript with `expected_revision: 1`
advanced it to revision 2 and marked prior outputs stale. Re-applying the old
proposal returned HTTP 409 `STALE_PROPOSAL: rerun after transcript edit`.
The append-only Apply evidence records both attempts, before/after sandbox
state, idempotency identity, and the stale revision boundary.

This is the first `REAL_LOCAL_END_TO_END` route with a valid proposal,
deterministic sandbox effect, duplicate-Apply protection, and stale-proposal
rejection. It is technical evidence only; no human-reviewed Saudi reference
has been assigned yet.
