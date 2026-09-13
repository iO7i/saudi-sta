# Saudi STA Slice 02 technical closeout — 2026-09-13

## Status

`SLICE_02_TECHNICAL_GREEN`

`SLICE_02_EMPIRICAL_STATUS: HUMAN_RECORDING_REQUIRED`

The technical boundary is now crossed: private real audio entered verified
local Audar speech recognition, Qwen3.8 ran locally on CPU, a strict emulated
tool proposal was validated, and the sandbox effect was explicitly applied and
read back. The only remaining Slice 02 evidence gap is user review of the
recordings and semantic references; no representative Saudi quality claim is
made.

## Proven gates

- Real route: Recording 15 → Audar Turbo Q4 → Qwen3.8 Q6_K_L → strict
  `add_list_items` proposal.
- Apply once: `APPLIED`; readback contained `المقاضي: [البيض, الحليب]`.
- Apply again: `ALREADY_APPLIED`; no duplicate effect.
- Transcript revision 2: old proposal rejected with
  `STALE_PROPOSAL: rerun after transcript edit`.
- Browser: upload, real transcription (private transcript redacted in this
  public note), non-blocking Qwen progress, proposal inspection, Apply/readback,
  idempotency, and stale rejection were exercised
  at loopback `http://127.0.0.1:8765/`.
- Cancellation: live Qwen child PID `34076` was terminated after cancel; no
  llama-cli child remained and `/api/health` remained healthy.
- Timeout policy: route cap 360 seconds; unit tests cover immediate timeout
  publication, cancellation, cleanup, and subsequent-job usability.
- Stage tournament: Q4/Q8/Flash Audar candidates ran on identical Recording 15
  audio; Flash was fastest at 9.04s, Q8 15.47s, Q4 21.09s. Human quality is
  `INSUFFICIENT_HUMAN_EVIDENCE`.
- Direct versus Staged: three real recordings, six sequential jobs. Direct
  completed 3/3; Staged completed 0/3 because its actionizer returned forbidden
  `status=OK`. Validation was not weakened. There is
  `NO GENERAL WINNER — DEVELOPMENT CASES ONLY`.
- Route tournament: three independent Audar→Qwen route recipes entered the
  existing tournament on one authored development case. All produced valid
  local actions; Q4 was selected within that narrow scope. This is route
  mechanics evidence, not human Saudi benchmark evidence.

## Optimization results within measured scope

| Mode | Result | Scope |
|---|---|---|
| Performance | Q4 Direct | one authored route-tournament case; not empirical Saudi quality |
| Speed | Q4 Direct for complete routes; Flash for the isolated STT stage | measured wall time; different scopes are labeled separately |
| Cost | monetary tie at 0; Q4 tie-break recommendation | local API cost only; no electricity price invented |
| Manual | exact selected stage bindings execute without optimizer override | verified by saved recipes and browser binding selection |

## Evidence classification

- `REAL_LOCAL_MODEL`: Audar Q4/Q8/Flash and Qwen Q6_K_L outputs, hashes, runtime
  metrics, and failures.
- `REAL_LOCAL_END_TO_END`: audio→Audar→Qwen→ToolProposal route records and
  browser trace.
- `AUTHORED_SMOKE_FIXTURE`: the one-case route-tournament comparison only.
- `HUMAN_REVIEWED`: none currently; `/api/seed-human-eval` is empty.
- `DEMO_RULES`: retained only for pre-existing deterministic tests/fixtures.
- `BLOCKED_HOSTED_PROVIDER`: HUMAIN and OpenAI remain disabled under
  `ZERO_SPEND_LOCAL`.

## Safety and repository state

- Monetary spend: `0`.
- Hosted inference calls: `0`.
- Cloud resources/deployments: `0`.
- Model weights, recordings, runtime SQLite, and Playwright traces are outside
  Git or ignored. Only hashes/metadata and bounded evidence notes are tracked.
- Full regression: 64 passed, one existing Starlette deprecation warning.
- Static checks: `node --check static/app.js` and `git diff --check` passed.
- The repository has no configured remote, so remote freshness/push cannot be
  established; this is reported as `REMOTE_FRESHNESS_BLOCKER` per workspace
  policy. No push was attempted.

## Evidence locations

- Browser journey: `audit/slice02-browser-closeout-2026-09-13.md`
- STT stage tournament: `audit/slice02-stt-recording15-closeout-2026-09-13.md`
- Direct/Staged experiment: `audit/slice02-direct-vs-staged-2026-09-13.md`
- Cancellation and route tournament: `audit/slice02-runtime-safety-and-route-tournament-2026-09-13.md`
- Full local JSON evidence remains outside Git at
  `${EVIDENCE_ROOT}/saudi-sta-slice02-stt-recording15.json`,
  `${EVIDENCE_ROOT}/saudi-sta-slice02-dev-comparison.json`,
  `${EVIDENCE_ROOT}/saudi-sta-slice02-route-tournament.json`, and
  `${EVIDENCE_ROOT}/saudi-sta-slice02-cancel-evidence.json`.
