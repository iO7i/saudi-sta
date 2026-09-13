# Slice 02 Direct versus Staged Qwen development comparison — 2026-09-13

This is a bounded development experiment on three real local recordings. It is
not a human-reviewed Saudi benchmark. The source recordings are private and
remain outside Git. Full job/route records are in the local runtime database;
the compact experiment manifest is retained outside Git at
`D:\saudi-sta-slice02-dev-comparison.json`.

## Configuration

- Direct: `audio → AUDAR_TURBO_Q4_LOCAL_BRIDGE → QWEN3.8 function_call`.
- Staged: `audio → AUDAR_TURBO_Q4_LOCAL_BRIDGE → QWEN3.8 actionize → QWEN3.8 function_call`.
- Same pinned Qwen artifact for both: `D:\Qwen3.8-27B-UD-Q6_K_L.gguf`,
  SHA-256 `121355b4c7422771da25adc74090e3c90138f77ce5c92d348687d47824ec80f4`.
- Runtime: llama.cpp `b10909-a2878d30d`, CPU/offline, reasoning off,
  temperature 0, JSON emulation with strict Pydantic validation.
- Six sequential jobs; no remote calls and no automatic retries.

## Results

| Recording | Direct outcome | Direct observation | Staged outcome | Staged observation |
|---|---|---|---|---|
| 14 | COMPLETED | `add_list_items(المقاضي, [البيض])`; 195.2 s wall | FAILED | Qwen semantic plan returned forbidden `status=OK`; strict `SemanticPlan` validation rejected it; 165.2 s |
| 15 | COMPLETED | `add_list_items(المقاضي, [البيض, الحليب])`; 120.2 s wall | FAILED | same strict `status=OK` semantic-plan rejection; 165.2 s |
| 16 | COMPLETED | `add_list_items(المقاضي, [البيض, الحليب])`; 120.2 s wall | FAILED | same strict `status=OK` semantic-plan rejection; 165.1 s |

All six jobs performed real Audar transcription before the Qwen stage. The
direct cases produced strict `REAL_LOCAL_MODEL` proposals with no invented
argument fields. The staged cases were retained as failures; no normalization
weakened the enum or repaired the malformed semantic output.

## Interpretation

For these three development cases, Direct completed 3/3 and Staged completed
0/3 because the actionize stage emitted `OK`, which is outside the declared
contract. There is **NO GENERAL WINNER — DEVELOPMENT CASES ONLY**. This is a
useful stage-boundary failure signal, not a Saudi quality claim. The staged
route must be repaired or re-probed only with a separately versioned prompt in
a later slice; this closeout does not silently relax validation.

The comparison retained end-to-end latency, stage failures, real transcripts,
proposal arguments, route identity, model digest, prompt/schema versions, and
`calibrated_correctness=null`.
