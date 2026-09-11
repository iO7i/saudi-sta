# Audar Turbo Q4 local bridge smoke evidence

Date: 2026-09-11 (Asia/Riyadh)

## Artifact and runtime identity

- Candidate: `AUDAR_TURBO_Q4_LOCAL_BRIDGE`
- Evidence class: `REAL_LOCAL_MODEL`
- Precision: `Q4_K_M`
- Benchmark claim: `NOT_REFERENCE_PRECISION`
- Repository: `audarai/Audar-ASR-V1-Turbo`
- Pinned revision: `371428bea487c7aec82b27dc21f8d4324002e98e`
- Decoder: `D:\models\audar\Audar-ASR-V1-Turbo\Audar-ASR-V1-Turbo-Q4_K_M.gguf`
- Decoder bytes: `1,282,434,912`
- Decoder SHA-256: `c55e3c28225ef6e9b56906a6463af62d34ed417803c45f3b7b20f463af2e8cf4`
- Projector: `D:\models\audar\Audar-ASR-V1-Turbo\mmproj-Audar-ASR-V1-Turbo.gguf`
- Projector bytes: `641,773,856`
- Projector SHA-256: `190459e806938175711779847eb62ea609cd78b8d2ec06fb96a94d69ab37a9be`
- Model-weight license identifier: `audarai-community-license-v1.0` (the model card describes research and limited commercial use for qualifying Community Entities; local legal gates remain `UNKNOWN` until reviewed for this repository).
- Runtime: `llama.cpp` Windows CPU x64 build `b10909`, `llama-mtmd-cli.exe`; release ZIP SHA-256 `4d4e3341d94f729d343a8e67e4ab692032645122c99368b88e02868212e639a8`.
- Execution: CPU, projector kept BF16, exact local paths, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, temperature `0`, seed `7`, no network alias or auto-download.

## Same-audio comparison input

- Audio: existing local `D:\models\whisper\FusHa.wav` (the same input used for the verified Whisper smoke).
- Human reference: not yet recorded; this is a real local smoke input, not a human-scored benchmark case.

## Output and timing

- Audar output: `<REDACTED_PRIVATE_TRANSCRIPT>`
- Native segments/timestamps: unavailable from this CLI path and therefore stored as an empty list.
- Native confidence/no-speech signals: unavailable and therefore `null`/unavailable.
- End-to-end wall time observed by the CLI invocation: approximately 2.5 seconds (including local model initialization and one audio encoding batch); the provider adapter records precise wall time per run.
- CLI emitted an experimental-mtmd warning; this is recorded as runtime evidence, not hidden.

## Comparison note

Whisper's earlier output on this same file was `<REDACTED_PRIVATE_TRANSCRIPT>` with one 0.00–3.82 second segment. Audar preserved the same words and added terminal punctuation. With no human reference and one utterance, the result is `INSUFFICIENT_HUMAN_EVIDENCE`, not a universal model ranking.
