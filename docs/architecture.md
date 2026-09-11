# Architecture · Slice 01

## Execution boundary

`ZERO_SPEND_LOCAL` is a server-side policy, not a UI convention. Every adapter dispatch calls `assert_dispatch_allowed`: OpenAI and HUMAIN are rejected; only `demo_rules`, `ollama_local`, and `faster_whisper_local` are recognized. Local HTTP requires an explicit HTTP loopback allowlist (`127.0.0.1`, `::1`, `localhost`), no credentials in the URL, no redirect following, and no inherited proxy configuration.

An Ollama endpoint is still not automatically trusted: it must have a configured local-only confirmation, a server-discovered model digest, and a separately supplied manifest that proves a local artifact file hash and matching Ollama digest. This is an application check, not an operating-system network sandbox. The app does not change or restart Ollama.

## Data flow

```text
text or managed recording
       │
       ├─ no verified local ASR → UNAVAILABLE_LOCAL_MODEL (manual text remains usable)
       │
       └─ recipe
           ├─ optional original-text summary → supporting spans
           ├─ direct function proposal OR semantic plan → function proposal
           ├─ strict proposal validation
           └─ locally persisted run provenance
                                      │
                              explicit Apply only
                                      │
                        note/reminder draft/list sandbox
```

Original text is always evidence for actionization. A summary is a separate branch and never replaces the transcript. Transcript edits increment a source revision and mark dependent summary/plan/proposal data stale. Applying a stale proposal is rejected.

## Roles, bindings, and recipes

Provider/model artifacts, role bindings, and recipes are separate Pydantic contracts. A binding carries provider, model identifier/digest, role, prompt/schema version, options, execution mode, capability provenance, availability reason, and tool mode. Recipes select bindings independently and declare either `DIRECT` or `TWO_STAGE` actionization plus an optional summary branch.

Reserved but non-operational roles are `acoustic_repair`, `semantic_repair`, `verify`, `respond`, and `synthesize`. They are never represented as successful dummy work.

`JSON_EMULATION` and `NATIVE` function calls are distinct fields. Demo Rules is JSON emulation only. A native tool call is recorded only when an eligible verified local binding returns a provider-native `tool_calls` structure.

## Local persistence and safety

SQLite stores recipes, records, review state, a local sandbox, and reports under `runtime/`; audio has a server-generated UUID filename under `runtime/audio/`. The browser cannot provide a filesystem path. Local mutating endpoints require a loopback Host and, when present, a loopback Origin. UI content is written as text, not injected HTML.

The tool registry is fixed: `create_note_draft`, `create_reminder_draft`, `add_list_items`, `revise_draft`, `cancel_draft`, and typed `request_clarification`. Unknown tools, extra fields, unknown values, duplicate apply, and stale source revisions are rejected. No tool can alter policy, providers, budgets, consent, filesystem, shell, network, or external services.

## Extension boundary

Later adapters may implement a verified local speech runtime, vetted provider contracts, review/import workflows, and calibrated quality estimates. They must preserve the policy gate, role/binding/recipe separation, source revisions, rights records, and measured whole-route evaluation. They must not add automatic remote fallback.
