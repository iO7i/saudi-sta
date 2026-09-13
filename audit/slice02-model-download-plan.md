# Slice 02 local model download plan

Status: reviewed before download on 2026-09-11. This is a machine-local, zero-spend plan.

## Constraints checked

- Monetary budget: zero. Downloads are public model artifacts only. No provider inference endpoint, cloud GPU, billing credential, or deployment is permitted.
- Runtime: CPU-only. No CUDA-capable NVIDIA GPU is available. The integrated GPU is not selected for the initial baseline.
- RAM: 31.12 GiB physical memory. Models run one at a time.
- Storage: D: had 154.12 GiB free at preflight. Model artifacts are outside the repository.
- Git safety: model weights, audio, datasets, databases, credentials, caches, and machine evidence are ignored.

## Existing artifact audit

`${MODEL_ROOT}/whisper/whisper-large-v3` was a partial copy of `openai/whisper-large-v3`. Its existing second shard's SHA-256 was verified against the canonical repository. The first shard was missing, so the model was not executable before this transfer.

## Download plan

| Purpose | Artifact | Pinned repository revision | License | Destination | Size |
|---|---|---|---|---|---:|
| Arabic STT baseline | `openai/whisper-large-v3` / `model.fp32-00001-of-00002.safetensors` | `06f233fe06e710322aca913c1bc4249a0d71fce1` | Apache-2.0 | `${MODEL_ROOT}/whisper/whisper-large-v3` | 4,993,448,880 B |
| Quality-oriented local text/action | `bartowski/Qwen_Qwen3.5-4B-GGUF` / `Qwen_Qwen3.5-4B-Q4_K_M.gguf` | `4168f45a16a1290d65a4ec0fa312ae917a4c15d6` | Apache-2.0 | `${MODEL_ROOT}/qwen35-4b-q4` | 3,013,027,808 B |
| Speed-oriented local text/action | `bartowski/Qwen_Qwen3.5-0.8B-GGUF` / `Qwen_Qwen3.5-0.8B-Q4_K_M.gguf` | `f36b1ea49a332ede8fe5f389bbf5b3575ef71f48` | Apache-2.0 | `${MODEL_ROOT}/qwen35-0.8b-q4` | 579,615,840 B |

Total planned model transfer: **8,586,092,528 B (about 8.00 GiB)**.

The two Qwen artifacts are Apache-2.0 GGUF conversions of Apache-2.0 Qwen releases. They are a quality-versus-speed/resource experiment within one family, not advertised as unrelated model families.

The bounded CPU runtime `llama-cpp-python` 0.3.35 (MIT) was installed into the
project virtual environment from its CPU wheel. It runs GGUF files in-process and
does not start a local model server or contact a hosted inference service.

## Bounds

- Verify the SHA-256 digest after every transfer.
- Do not download vision projections, alternate quantizations, or a general ML stack.
- Stop before another download if free D: storage falls below 120 GiB.
- All runtime loads use local paths. No hosted-model selector may execute under `ZERO_SPEND_LOCAL`.
