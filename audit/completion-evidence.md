# Slice 01 completion evidence

Recorded locally on 2026-09-11. This is an evidence log, not a claim of real-model quality.

## Environment inspection

- Workspace contained only `AGENTS.md`; it is not a Git checkout, so no branch, stash, commit, push, or PR exists.
- Bounded project-scope search found no Qalam/MUSTAMI material.
- Python and Node were present; FastAPI/Uvicorn/Pytest were installed only in the project-local `.venv` after confirming approximately 39 GiB free on C:. No model, GPU, CUDA, container, or model-runtime package was installed.
- `ollama` was not available on PATH. No configured local model artifact or existing local speech model directory was found.

## Executed checks

| Check | Result | Evidence class |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe -m compileall -q app` | Passed | Local static compilation |
| `.\.venv\Scripts\python.exe -m pytest -q` | **13 passed**; one upstream TestClient deprecation warning | Local automated test |
| Browser at `http://127.0.0.1:8080` | Arabic-first workbench loaded; English locale switch loaded | Actual local browser evidence |
| Browser text run | `حط milk وقهوة في قائمة المقاضي` produced `DEMO_RULES`, `JSON_EMULATION`, `READY`, and a typed `add_list_items` proposal with both items | Deterministic baseline, not model inference |
| Browser explicit apply | Sandbox list changed only after pressing Apply | Actual local sandbox behavior |
| Browser Speed preflight | Two demo recipes, 12 cases, upper bound 60/72 calls, concurrency 1, remote calls 0 | Actual local tournament preflight |
| Browser Speed tournament | Completed; both routes showed `DEMO_RULES`, quality 1, coverage 1, failures 0; recommended tested recipe was shown | Deterministic authored-fixture evaluation |
| Browser model selector | Transcribe selector visibly disabled with `UNAVAILABLE_LOCAL_MODEL: explicit existing model directory is required` | Honest blocked integration state |

## Policy checks and limits

Tests verify that remote OpenAI/HUMAIN dispatch is blocked even if an environment key exists, non-loopback/credential URL targets are rejected, tool arguments are strict, stale proposals cannot apply, and fake provider bindings are rejected. The application records its loopback/artifact checks but does **not** claim an operating-system network sandbox.

No hosted inference, provider account, credit, paid resource, model pull/download, GPU installation, deployment, push, hosted CI, commit, or publishing occurred. Ordinary documentation pages and small project-local Python packages were accessed. No recordings, text, credentials, or telemetry were sent to a third party by the application during these checks.

## Result classification

- **Real inference:** none; local Ollama and speech runtime/model artifacts were unavailable.
- **Deterministic baseline:** text summary/action/function proposal and tournament results labeled `DEMO_RULES`.
- **Synthetic fixtures:** `AUTHORED_SMOKE_FIXTURE` expected labels/evaluator data; not human gold or STT evidence.

## Recoverability

This log is stored under the named project path `audit/completion-evidence.md`. Private runtime database/audio/exports remain under ignored `runtime/` and are not archived or published.
