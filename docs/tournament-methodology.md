# Tournament methodology

The tournament runner evaluates complete versioned recipes, not a hard-coded provider ranking. It has concurrency `1`, at most `6` recipes, at most `30` seed cases, an explicit local-stage cap, no automatic repair, and no unbounded retry. Preflight calculates the upper-bound stage invocations before dispatch and reports zero remote calls.

## Required parity and scoring

Compared recipes must produce their declared required outputs. The named routes are: Direct (`STT → function_call`), Semantic (`STT → actionize → function_call`), and Semantic + summary (the Semantic route plus an independent summary branch). Summary is optional and never fed into function calling when the original transcript is available. The semantic plan is diagnostic, not a way to let a route win by doing less work.

Each authored fixture is passed to a candidate as source text only. A `SEED_HUMAN_EVAL` case first passes its local audio through the recipe's verified STT binding; its human-reviewed reference remains evaluator-side. The evaluator checks proposal fields and isolated sandbox state. Failures/timeouts stay in denominators. Reports retain case-level transcripts, STT WER/CER where a human reference exists, critical spans, structured error labels, raw per-case duration, per-stage timing, and whole-route duration separately.

## Controls

- **Cost:** all local routes report provider monetary inference cost as `0`. Quality, accurately measured resource footprint, then observed latency break that transparent tie. No electricity price is invented.
- **Speed:** minimize observed end-to-end whole-route completion time after the same gate. The report says whether timings were Demo Rules or real local model timings. The 12-case smoke run does not claim p95.
- **Performance:** maximize end-to-end function/action correctness after the execution-policy gate, then use latency/resource tie-breaks. Valid JSON with a wrong tool or argument is wrong.
- **Manual:** stores selected bindings and role locks and deliberately returns no optimizer override.

Outcomes include `NO_ELIGIBLE_ROUTE`, `NO_HUMAN_SEED_CASES`, `CALL_CAP_EXCEEDED`, `ONLY_ONE_CANDIDATE`, `NO_ROUTE_MEETS_FLOOR`, `TIE`, and `RECOMMENDED`. A completed run has narrow evidence only: it cannot claim a generally best Saudi model, statistical significance, or human-evaluated summary quality.

## Evidence partitions

`fixtures/authored_smoke.json` contains 28 `AUTHORED_SMOKE_FIXTURE` cases with development/test partitions. It is not human gold, cannot establish ASR quality, and is not eligible for training. `SEED_HUMAN_EVAL` holds local recordings and explicit human references, with reviewer/session provenance. Demo-route timing/quality remains labeled `DEMO_RULES`; it is never mixed into real local model leaderboards.
