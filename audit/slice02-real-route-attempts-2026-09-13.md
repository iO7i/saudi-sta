# Slice 02 — real-route attempts from user recordings

Evidence class: `REAL_LOCAL_MODEL` for ASR/Qwen execution; no successful
`REAL_LOCAL_END_TO_END` Apply trace was produced in this attempt set.

## Inputs

The user supplied five new local recordings under
`<PRIVATE_RECORDINGS_ROOT>`:

| File | Bytes | SHA-256 | Audar Q4 observation |
|---|---:|---|---|
| `Recording (2).m4a` | 130,262 | `ede1282a1770c6ecc5f308867600243f457488b71c7c36e3695c6020bf35920d` | `<REDACTED_PRIVATE_TRANSCRIPT>` |
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

`<REDACTED_PRIVATE_TRANSCRIPT>`

Then review the verbatim transcript and expected `add_list_items` arguments in
the Seed Saudi Speech Set UI. Do not label the current physical/external-action
recordings as successful sandbox actions.

## Follow-up recordings 7–12

The same Audar Q4 bridge transcribed six additional local recordings. Hashes,
durations, and outputs are retained here so these observations remain separate
from human-reviewed gold labels:

| File | Duration (s) | SHA-256 | Audar Q4 transcript / observation |
|---|---:|---|---|
| `Recording (7).m4a` | 9.088 | `b73e1765bd616b792a0185869d44919350a4733ea982415789b56bbe810a79f6` | `<REDACTED_PRIVATE_TRANSCRIPT>` — mixed list/note wording; clarification required |
| `Recording (8).m4a` | 14.379 | `85a631def5988f9cad0c664db7a2fa4d16f206cbada17040f77842472ca434dc` | `ممكن تسجل ملاحظة يعني او تكتب ملاحظة في جوالك اسجل عندك رقم جوالي <REDACTED_PHONE>` — note intent, content boundary ambiguous |
| `Recording (9).m4a` | 9.344 | `a45d181e8c2aa0098a34149d7b63fd77dc779e6036beef2a48d51902dd4212e0` | `<REDACTED_PRIVATE_TRANSCRIPT>` — external group/invite request |
| `Recording (10).m4a` | 12.011 | `fe076ee72dfdc4bdadc42e04a29894c043a2b04c37fda2aee1bdc4626d48ba8a` | `<REDACTED_PRIVATE_TRANSCRIPT>` — draft request with missing content |
| `Recording (11).m4a` | 9.408 | `978a220b7376c342f795274bf65e1e616a95e78782afbecdcdd88f01be37bee0` | `<REDACTED_PRIVATE_TRANSCRIPT>` — no supported sandbox action |
| `Recording (12).m4a` | 6.101 | `ca2150ac429b77c276f72f862f9e265f439d208c3990bdbf63973d36e6a8d4e0` | `<REDACTED_PRIVATE_TRANSCRIPT>` — calculation/save request outside the current tool set |

Two bounded real routes were then executed with the Q4 transcript and Qwen
Q6_K_L direct function-call recipe. Recording (8) produced a strict,
schema-valid `request_clarification` proposal asking for `note_content`;
Recording (7) produced a strict, schema-valid clarification asking for
`list_name`, the unresolved “سوي كذا” action, and `note_content`. Neither route
was Apply-eligible, so sandbox state was intentionally unchanged. Qwen's raw
responses, artifact hash, runtime, and stage latencies are retained in the
local SQLite route records under the configured runtime data directory.

## Recording 13

`Recording (13).m4a` was added with the intended list phrase (`أضف حليب وبيض
إلى قائمة المقاضي`). The local file is 162,635 bytes, 6.357479 seconds, and
SHA-256 `c6a175bb1b4947624ab14d0c4a72d69c14518443f9150da83875b1b952e56ff7`.
The first Qwen run reached the model but returned the out-of-contract status
`OK`; strict validation rejected it. The prompt was then versioned to
`qwen-json-v2` with the exact allowed status enum spelled out. A second bounded
attempt exceeded the 330-second harness ceiling and was explicitly cancelled;
it produced no ToolProposal and no sandbox mutation. The confirmed orphaned
Qwen child from that short-lived harness was terminated, and exit-time child
cleanup was added to the adapters.

The same audio was independently transcribed by all three certified Audar
variants: Q4 and Q8 returned `<REDACTED_PRIVATE_TRANSCRIPT>`, while Flash
returned `<REDACTED_PRIVATE_TRANSCRIPT>`. The item words were preserved, but
the shopping-list word was not. This disagreement is retained as an observed
STT error; it is not normalized into `المقاضي` without a human reference.
