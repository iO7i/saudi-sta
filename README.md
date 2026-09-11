# Saudi STA · Slice 01

Saudi STA is a local-first workbench for measuring Saudi Arabic and Arabic/English speech-to-action recipes. Slice 02 adds a verified-local inference boundary, explicit Direct/Semantic/Semantic+summary recipes, a private `SEED_HUMAN_EVAL` recording/review workflow, and real-route tournament methodology. It never falls back to hosted inference.

## Zero-spend quickstart

This project creates no account, uses no cloud inference, pulls no models, and makes no outbound provider call by default.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080`. Use the recorded sample text or type a Saudi Arabic / mixed-language request. The visible `DEMO_RULES` state is a deterministic non-ML reference path, not a model result.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Current capability table

| Capability | Current state | Evidence boundary |
| --- | --- | --- |
| Text → extractive preview | Available | `DEMO_RULES`, review-pending summary |
| Text → semantic plan / tool proposal | Available | `DEMO_RULES`, strict server-side tool validation |
| Local sandbox drafts/lists | Available | Explicit Apply only; no external execution |
| Recording/upload/playback | Available | Stored in local runtime directory; no ASR fallback |
| Verified local Whisper | Available only with an integrity-checked external artifact manifest | CPU local inference; no post-download network access |
| Verified local GGUF text models | Available only with an integrity-checked external artifact manifest | Direct in-process llama.cpp; no local relay/server |
| Speech recognition | Blocked here | Requires an existing verified local runtime and model directory |
| Local Ollama text inference | Implemented conditionally | Requires configured loopback endpoint, verified artifact manifest, and confirmed cloud disablement |
| HUMAIN / OpenAI | Disabled | `ZERO_SPEND_LOCAL` rejects dispatch, even if credentials exist |
| Tournament | Available | 12-case bound, six routes maximum, zero remote calls |

## What the four controls do now

- **Cost** compares known marginal provider costs after the quality/completion gate. Current demo routes tie at `$0`; declared quality and observed latency break the tie.
- **Speed** chooses the lowest measured whole-route latency among routes meeting the same quality gate.
- **Performance** chooses the highest predeclared task-quality score, then latency/cost.
- **Manual** preserves direct role bindings and locks; it never overrides them.

Each control first shows a preflight plan. It cannot start a tournament until the user explicitly presses **Start displayed comparison**.

## Local-model opt-in (no downloads)

The app never assumes a familiar local URL means a local model. If an operator has already installed Ollama and has local artifact files, set all of the following before starting:

- `SAUDI_STA_OLLAMA_URL` to an explicit `http://127.0.0.1:<port>` / `localhost` endpoint.
- `SAUDI_STA_OLLAMA_LOCAL_ONLY_CONFIRMED=1` only after independently confirming the server's cloud-disable setting.
- `SAUDI_STA_OLLAMA_ARTIFACT_MANIFEST` to a local JSON manifest whose model file hashes and Ollama digests match the discovery response.

Only then can discovered role bindings enter the selector. The adapter follows no redirects, ignores proxy environment variables, has no pull method, and hides model `thinking` fields. See [provider matrix](docs/provider-matrix.md).

For optional speech recognition, point `SAUDI_STA_SPEECH_MODEL_DIR` at an already-existing model directory and install nothing automatically. The adapter refuses to run unless the installed `faster-whisper` runtime exposes a local-files-only guarantee.

## Limits

- The provided 28 cases are `AUTHORED_SMOKE_FIXTURE`, not human gold, recordings, population evidence, or STT quality evidence.
- Summaries have span references but remain review-pending and receive no invented semantic-quality score.
- Browser-provided WebM/OGG/MP3/M4A duration is reported by the recorder; WAV duration is checked server-side. All audio is limited to 10 MiB / 300 seconds.
- No automatic learning, silver/gold promotion, remote repair, retries, cloud fallback, sending, calendar integration, or general agent framework exists in this slice.
- `runtime/` contains private records/audio/database and is ignored by Git. Deleting a local record removes the local record and its associated stored derivative; exports already downloaded cannot be recalled.

Read [architecture](docs/architecture.md), [tournament methodology](docs/tournament-methodology.md), [data policy](docs/data-policy.md), [provider matrix](docs/provider-matrix.md), and the [Qalam reuse audit](docs/qalam-reuse-audit.md) before extending the slice.

For Slice 02, also read [local model methodology](docs/slice02-methodology.md), the [seed speech protocol](docs/seed-human-eval.md), and the [external-artifact manifest template](docs/local-model-manifest.example.json). Model weights, private audio, databases, and machine-local evidence are excluded from Git.
