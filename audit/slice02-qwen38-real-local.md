# Slice 02 — Qwen3.8-27B real local bridge

Date: 2026-09-12 (Asia/Riyadh)

Evidence class: `REAL_LOCAL_MODEL`. This is a local CPU smoke/capability
probe, not a broad benchmark and not a claim about the Qwen family in general.

## Artifact and license

- Source: `unsloth/Qwen3.8-27B-GGUF`
- Revision: `4ca720788d1e01f1bff70c033e0d0028fd02e502`
- File: `D:\\Qwen3.8-27B-UD-Q6_K_L.gguf`
- Bytes: `24,193,919,904`
- SHA-256: `121355b4c7422771da25adc74090e3c90138f77ce5c92d348687d47824ec80f4`
- Precision/quantization: `Q6_K_L`
- License: `Apache-2.0` (metadata retrieved from the authoritative Hugging Face model card/API)
- Monetary inference cost: `0`
- Artifact is outside Git and auto-activation is disabled.

## Runtime and hardware

- Runtime: pinned `llama.cpp` CLI `b10909-a2878d30d`
- Executable: `D:\\models\\runtimes\\llama.cpp\\b10909\\llama-cli.exe`
- Execution: CPU, 8 threads, loopback/offline environment flags, temperature 0,
  reasoning off, no remote endpoint
- Machine: Windows 11 Pro, AMD Ryzen AI 9 365 / Radeon 880M, 31.1 GB RAM
- GPU execution was not used; GPU VRAM was insufficient for this Q6 model.

## Capability probes

### Plain local chat

Prompt requested exactly one short sentence. The model returned:

`local model ready`

This proves the pinned artifact loads and generates locally.

### Structured action JSON emulation

The adapter used `JSON_EMULATION` because the native llama.cpp JSON grammar path
failed on this model's chat template with:

`Unexpected empty grammar stack after accepting piece: <|im_start|>`

No native structured-output capability is claimed. The prompt-only emulation
probe returned an Arabic reminder object containing `create_reminder_draft`,
`hour: 8`, and `needs_clarification: true` for:

`ذكرني الساعة سبعة... لا، ثمانية.`

Observed completion (after JSON extraction) was equivalent to:

```json
{"tool":"create_reminder_draft","arguments":{"time":"8:00"},"needs_clarification":true}
```

This is useful capability evidence but is not yet an apply-eligible sandbox
proposal: it uses the model's `tool` alias and an incomplete `time` argument.
The application now normalizes the harmless alias, then still subjects the
proposal to the strict `ToolProposal`/sandbox schema. Missing required fields
remain a clarification or validation outcome; they are never invented.

Observed end-to-end CLI latency (model load + generation): approximately
`100,934 ms`; CPU generation was very slow (about `0.1 tokens/s` in the
successful plain-chat probe). The raw response is retained in the run record;
the prompt echo is parsed separately from the JSON object.

## Certification state

`INTEGRITY_VERIFIED` and `RUNTIME_LOAD_VERIFIED` are proven. Plain chat and
JSON-emulation generation are locally exercised. Native JSON grammar and native
tool calls remain unverified/unsupported on this exact runtime/template path.
The model is therefore eligible for local text experimentation through explicit
JSON emulation, subject to route latency and strict proposal validation.

`calibrated_correctness`: `null`.
