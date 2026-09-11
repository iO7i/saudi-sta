# Slice 02 real-local smoke evidence

Recorded 2026-09-11 after the missing Whisper shard was downloaded and verified.

## REAL_LOCAL_MODEL

- Model: `openai/whisper-large-v3`
- Revision: `06f233fe06e710322aca913c1bc4249a0d71fce1`
- License: Apache-2.0
- Runtime: Transformers 4.46.3, PyTorch 2.4.1+cpu, CPU execution
- Artifacts: two verified safetensors shards, 4,993,448,880 B and 1,180,663,192 B
- First shard SHA-256: `08e0005225b3dbaf55dd13ac62926cc7e02c1025d66fa375e6fb305ff79cd4f9`
- Second shard SHA-256: `630ca774672856d2e0e39a702e590f635a1cfc5726a64b6578ab46dd367369a9`
- Audio: local `D:\models\whisper\FusHa.wav`; provenance is not a user-reviewed Saudi seed case
- Output: `<REDACTED_PRIVATE_TRANSCRIPT>`
- Segments: one returned segment, 0.00–3.82 seconds
- Cold model load: approximately 4,686 ms
- Inference latency: approximately 12,733 ms
- Confidence signals: no log-probability/no-speech/compression/stability/alternative signals returned by this pipeline; timestamps only

## Not yet REAL_LOCAL_MODEL

The Qwen3.5 GGUF candidates were planned and their runtime boundary is implemented,
but the first text-model transfer did not complete successfully and no Qwen artifact
is admitted to the local manifest. Therefore no real text/action route or measured
model tournament is claimed by this evidence file. The application continues to
reject unverified text bindings rather than falling back to demo text.

## Evidence separation

- `AUTHORED_SMOKE_FIXTURE`: existing deterministic contract tests only.
- `HUMAN_REVIEWED`: no user-recorded seed case is claimed by this file.
- `DEMO_RULES`: remains explicit and separate.
- `BLOCKED_HOSTED_PROVIDER`: HUMAIN and OpenAI remain disabled under `ZERO_SPEND_LOCAL`.
