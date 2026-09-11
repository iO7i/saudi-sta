# Download worker repair evidence — 2026-09-11

## Remote freshness

- Scope: `<PRIVATE_WORKSPACE>`
- Fetch attempted with `git fetch --all --prune --tags`.
- The checkout has no configured Git remote, so current upstream truth could not be proven. This remains `REMOTE_FRESHNESS_BLOCKER`.
- Recovery commit: `6e59afb`.
- Recovery branch: `recovery/download-queue-continuation-20260911`.

## Audar Diarization repair

- Repository: `audarai/Audar-Diarization-V1`
- Pinned revision: `230e5afed3f87637c12c8fb819dd0be9b1ddf6cb`
- Artifact: `model.safetensors`
- Expected bytes: `471103752`
- Expected SHA-256: `86444dd50d63cad3875ef3aab679ebc842466511c49753f9869b8e4ad5395cba`
- Invalid partial SHA-256: `e97c329fde193975344e85e5fa1500870a6beb741921d1f549ea19331312eba2`
- Invalid partial bytes: `482617608`
- Quarantined path: `D:\models\audar\Audar-Diarization-V1\model.safetensors.part.invalid-20260911-221246`
- Fresh transfer completed and was atomically promoted to `INTEGRITY_VERIFIED`.

## Queue semantics and supervision

- `QUEUE_COMPLETE` is allowed only when every frozen item is terminal: `INTEGRITY_VERIFIED`, `BLOCKED_ACCESS`, `BLOCKED_USER_ACTION`, or `FAILED_RETRY_EXHAUSTED`.
- The worker preserves resumable partials, quarantines oversized/hash-invalid partials, uses bounded integrity retries, and never modifies a verified final artifact.
- The supervisor now uses a Windows-safe process liveness check and restarts only a genuinely exited worker, with a bounded restart limit.
- A duplicate-launch incident was reproduced: Windows `os.kill(pid, 0)` returned `WinError 87`, causing false restarts and an oversized LiveKit temporary. The invalid temporary was quarantined; the final LiveKit artifact was subsequently size/hash verified.

## Pinned remaining metadata

- LiveKit `model_quantized.onnx`: `165035487` bytes, SHA-256 `4e685767c3643b0363c9f826a98325683f29e9c7d550162c8e8740ba33aa31aa`, revision `fba34c38ad5d30a63ebb83a9e6bf271cf4c91d67`.
- Qwen3.8 GGUF: `24193919904` bytes, SHA-256 `121355b4c7422771da25adc74090e3c90138f77ce5c92d348687d47824ec80f4`, revision `4ca720788d1e01f1bff70c033e0d0028fd02e502`.
- Granite GGUF: `23684179168` bytes, SHA-256 `182f89335e9b891b799230f496af5bd1f1dfff97e79bab424776b2d65766b53b`, revision `26a44ffe9923eea39af3ad811b56c9b0071e4347`.
- BTL GGUF: `30299748480` bytes, SHA-256 `ff76ac2a57a9330e05d0ada00114bac5c2ebd412deead2771a2d0e49110de658`, revision `799d011b498e3287f514eb463ea04d6624ec945f`.
- Meta OmniASR weights/tokenizer: revisions pinned to `4b0bada258b398cb7e6c5b3a6ed5448fb914385b`; weights are `31205087103` bytes and tokenizer is `87607` bytes.
- Qwen Omni weights: revision `26291f793822fb6be9555850f06dfe95f2d7e695`, all 15 safetensor shard sizes and LFS SHA-256 values are embedded in the worker descriptor.
- Cohere Arabic and NeuCodec remain `BLOCKED_ACCESS` because their authoritative repositories report `gated=auto`.

## Verification

- `25 passed, 1 warning`.
- Live worker state at capture: `DOWNLOADING`.
- Supervisor state at capture: `ACTIVE`.
- `QUEUE_COMPLETE` is impossible while pending items remain.
