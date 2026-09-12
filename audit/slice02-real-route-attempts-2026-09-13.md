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
