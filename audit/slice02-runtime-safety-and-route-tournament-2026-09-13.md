# Slice 02 closeout runtime safety and route tournament — 2026-09-13

## Cancellation and bounded execution

An actual local Qwen route job was submitted for Recording 15 using the
verified Audar Q4 + Qwen Direct recipe. After 25 seconds, while the Qwen child
was active, the local cancel endpoint was called. The job finished as
`cancelled` with `LocalModelUnavailable:LOCAL_GGUF_CANCELLED`; the observed
llama-cli PID was gone at terminal state, and a subsequent `/api/health` call
returned `status=ok`, `ZERO_SPEND_LOCAL`, and `remote_inference=blocked`.

- Job: `0e888efc-1a3e-4670-881c-44778d995110`
- Child PID before cancellation: `34076`
- Child PIDs after terminal state: none
- Evidence manifest: `${EVIDENCE_ROOT}/saudi-sta-slice02-cancel-evidence.json`
- Configured route cap: 360 seconds
- Unit regression coverage also proves immediate timeout publication,
  cooperative cancellation, child cleanup, and subsequent-job usability.

## Complete-route tournament mechanics

Tournament job `618210ab-d72d-452d-be86-a54396110557` admitted three distinct
local route recipes, each bound to a different real Audar STT candidate and the
verified Qwen function role:

| Route | Development cases | Successes | Mean route latency | Scope |
|---|---:|---:|---:|---|
| Audar Turbo Q4 → Qwen Direct | 1 | 1 | 104,483.69 ms | authored fixture, route mechanics |
| Audar Turbo Q8 → Qwen Direct | 1 | 1 | 107,466.73 ms | authored fixture, route mechanics |
| Audar Flash Q8 → Qwen Direct | 1 | 1 | 116,769.49 ms | authored fixture, route mechanics |

All three returned a valid sandbox action. Performance selected the Q4 recipe
within this single authored development case, but this is not human Saudi
quality evidence. The report explicitly says
`AUTHORED_SMOKE_FIXTURE + route-specific execution evidence`; no human
reference or STT quality winner is inferred. Full report:
`${EVIDENCE_ROOT}/saudi-sta-slice02-route-tournament.json`.

Together with the separate real audio route records and the same-audio STT
stage tournament, this proves that complete local route candidates can enter
the existing tournament machinery without `DEMO_RULES` substitution. A
representative Saudi Performance winner remains unavailable until the user
reviews the recordings and semantic references.
