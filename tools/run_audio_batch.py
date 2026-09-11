"""Detached local STT comparison batch for user-provided recordings.

Each recording is submitted independently and the app persists its report
before the next recording begins.  This is deliberately Audar-only for the
first pass so a slow Whisper process cannot prevent useful comparisons from
being retained.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

# Detached launches may receive a different process working directory.  Bind
# imports to this repository explicitly; model/audio paths remain external.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import _run_stt_comparison, store
from app.schemas import STTTournamentStart


Audar_BINDINGS = [
    "audar_mtmd_local:AUDAR_TURBO_Q4_LOCAL_BRIDGE:transcribe",
    "audar_mtmd_local:AUDAR_TURBO_Q8_LOCAL:transcribe",
    "audar_mtmd_local:AUDAR_FLASH_Q8_LOCAL:transcribe",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--log", default=None)
    args = parser.parse_args()
    log_path = Path(args.log) if args.log else None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(value: dict):
        line = json.dumps(value, ensure_ascii=False)
        print(line, flush=True)
        if log_path:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    for recording_id in args.ids:
        recording = store.recording(recording_id)
        if not recording:
            emit({"recording_id": recording_id, "status": "SKIPPED", "error": "RECORDING_NOT_FOUND"})
            continue
        emit({"recording_id": recording_id, "status": "STARTED", "filename": recording["filename"]})
        try:
            report = _run_stt_comparison(STTTournamentStart(recording_id=recording_id, mode="Speed", binding_ids=Audar_BINDINGS))
            emit({"recording_id": recording_id, "status": "COMPLETED", "report_id": report["id"],
                  "candidates": [{"model_id": item["model_id"], "status": item["status"],
                                  "transcript": item.get("transcript"), "latency_ms": item.get("latency_ms"),
                                  "error": item.get("error")} for item in report["candidates"]]})
        except Exception as exc:  # keep later recordings independent
            emit({"recording_id": recording_id, "status": "FAILED", "error": f"{type(exc).__name__}:{str(exc)[:240]}",
                  "traceback": traceback.format_exc(limit=2)})
    emit({"status": "QUEUE_COMPLETE", "count": len(args.ids)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
