# Audar Turbo Q4 bridge download plan

Preflight source: Hugging Face model API for `audarai/Audar-ASR-V1-Turbo`.

- Repository: `audarai/Audar-ASR-V1-Turbo`
- Revision: `371428bea487c7aec82b27dc21f8d4324002e98e`
- License metadata: `other` (the repository card must be reviewed before redistribution or commercial use)
- Destination root: `${MODEL_ROOT}/audar/Audar-ASR-V1-Turbo/`
- Transfer budget: approximately 2,000,000,000 decimal bytes
- Planned transfer: 1,924,208,768 bytes (1.924 GB / 1.792 GiB)
- Scope: exactly the two pinned files below; no repository-wide download.

| filename | bytes | SHA-256 | role |
|---|---:|---|---|
| `Audar-ASR-V1-Turbo-Q4_K_M.gguf` | 1,282,434,912 | `c55e3c28225ef6e9b56906a6463af62d34ed417803c45f3b7b20f463af2e8cf4` | Q4_K_M decoder |
| `mmproj-Audar-ASR-V1-Turbo.gguf` | 641,773,856 | `190459e806938175711779847eb62ea609cd78b8d2ec06fb96a94d69ab37a9be` | BF16 audio projector |

The download is eligible to start because the exact combined byte count is below the stated budget. Files will be finalized only after byte-count and SHA-256 verification; partial files remain marked as partial and are not eligible for inference.
