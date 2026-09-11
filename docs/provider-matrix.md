# Provider matrix

## Slice 02 local-baseline addition

| Provider / adapter | State | Capability provenance | Runtime decision |
|---|---|---|---|
| Transformers Whisper from a verified external artifact manifest | Implemented if verified local artifact exists | `VERIFIED_LOCAL` only after every declared file digest matches | CPU-only direct local inference; its output is stored separately from a human transcript correction |
| llama-cpp-python from a verified GGUF manifest | Implemented if verified local artifact exists | `VERIFIED_LOCAL` only after GGUF digest and runtime checks pass | Direct in-process local inference; no HTTP relay, model pull, or provider fallback |
| HUMAIN Voice | Visible but disabled | `BLOCKED_HOSTED_PROVIDER` | Preferred future hosted voice option; `NOT EXECUTED — ZERO_SPEND_LOCAL` |
| OpenAI | Visible but disabled | `BLOCKED_HOSTED_PROVIDER` | Optional future provider; `NOT EXECUTED — ZERO_SPEND_LOCAL` |

An artifact being present does not certify role eligibility by itself. The Slice 02
catalog exposes a role only after the local runtime and artifact integrity checks
pass; runtime exercises are then recorded in a real local run.

Checked 2026-09-11. These sources were read for interface boundaries only; no inference, account, model pull, SDK installation, or provider configuration change occurred.

| Provider / adapter | State in Slice 01 | Capability provenance | Runtime decision |
| --- | --- | --- | --- |
| `DEMO_RULES` | Implemented and tested | Documented application behavior | Available deterministic reference path; not ML or ASR |
| Ollama local | Implemented conditionally | Verified local only after tags + local file/digest manifest + operator cloud-disable confirmation | No CLI/runtime discovered in this environment; no model used |
| faster-whisper local | Optional adapter boundary | Unknown until an existing runtime/model directory passes checks | Runtime/weights missing here; returns `UNAVAILABLE_LOCAL_MODEL` |
| HUMAIN Voice | Disabled integration entry | Contract details intentionally unknown here | Preferred future provider, currently not executable |
| OpenAI text/audio | Disabled integration entry | Function-calling concepts documented; no live contract serializer | Blocked by policy even with a key |

## Checked contracts and implementation decisions

- [Ollama list models](https://docs.ollama.com/api/tags) documents local `GET /api/tags` and model metadata including a digest. The adapter uses it only after an operator configured an allowed loopback server; it never calls a pull endpoint.
- [Ollama chat](https://docs.ollama.com/api/chat) documents `POST /api/chat`, JSON-schema `format`, tools, and a response that may include `thinking` and `tool_calls`. The adapter requests structured output, validates it, and intentionally discards `thinking`.
- [Ollama FAQ](https://docs.ollama.com/faq) documents cloud-disable settings (`disable_ollama_cloud` / `OLLAMA_NO_CLOUD`) and default loopback binding. The app does not claim to inspect server configuration or enforce an OS network sandbox; it requires an explicit operator confirmation and records its own locality checks.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) is retained as the optional local STT boundary. The adapter accepts only an explicit existing directory, checks the installed runtime signature for local-files-only behavior, and does not instantiate a shorthand model name.
- [HUMAIN Voice](https://voice.humain.com/) was consulted, but this slice has no authenticated request serializer or claimed model/capability details. Its entry stays disabled.
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) and [OpenAI API docs](https://developers.openai.com/api/docs/) were consulted to keep future function-calling and audio boundaries conceptually separate. This slice intentionally makes no OpenAI request and does not treat a key as permission.

## Current local discovery result

Ollama remains unavailable on PATH and no Qalam speech runtime is used. The external
Whisper manifest now passes both shard digest checks, and the Transformers adapter
has executed one real local audio inference; evidence is retained in
`audit/slice02-real-local-smoke.md`. Qwen text artifacts remain unverified and are
not admitted to the catalog. `DEMO_RULES` is visibly separate from real local-model
and authored-fixture evidence.
