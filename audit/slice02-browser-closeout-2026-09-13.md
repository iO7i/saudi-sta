# Slice 02 browser closeout evidence — 2026-09-13

## Environment

- Browser: Playwright CLI attached to `http://127.0.0.1:8765/`.
- Server: loopback-only Uvicorn process; no hosted provider was configured or
  contacted.
- Input: private `Recording (15).m4a`, converted locally to a temporary 16 kHz
  mono WAV for the browser upload. The browser-visible audio identity was
  `611e34529c886e3fe4c149c7170dbac9d3f879720d4a2620dd0e6c79f70bc9f3`,
  duration 8.7893125 seconds.
- Route: `AUDAR_TURBO_Q4_LOCAL_BRIDGE → QWEN38_27B_Q6_K_L · Direct`.
- Qwen binding: `JSON_EMULATION`, prompt `qwen-json-v2`, llama.cpp build
  `b10909-a2878d30d`, reasoning disabled, temperature 0, 160-token bound.

## Journey

1. Uploaded and saved the real recording through the Workbench UI. The UI
   showed a local audio identity and `8.8s`; the upload did not contact a
   transcription service.
2. Selected the independently bound Audar Q4 transcription model and Qwen
   function-call model. The saved recipe was refreshed once to replace an old
   persisted `qwen-json-v1` binding with the current server-discovered
   `qwen-json-v2` binding; no model artifact or route was changed.
3. Started the route. The UI immediately showed `running · 360s cap` and
   `Local inference is running; the UI remains responsive.`
4. While Qwen was still running, navigated to Model laboratory and back to
   Workbench. Both views loaded. A separate `/api/health` request returned
   `status: ok`, `ZERO_SPEND_LOCAL`, and `remote_inference: blocked` while the
   `llama-cli` child was active.
5. The Workbench rendered `REAL_LOCAL_END_TO_END`, the real Audar transcript
   (redacted in this public note), and the strict
   proposal:

   ```json
   {"status":"READY","tool_name":"add_list_items","arguments":{"list_name":"المقاضي","items":["البيض","الحليب"]}}
   ```

6. Preview showed an empty sandbox. Clicking **Apply** once changed the local
   sandbox to `المقاضي: [البيض, الحليب]` and displayed `APPLIED`.
7. Clicking **Apply** again displayed `ALREADY_APPLIED`; the sandbox list and
   applied-proposal identity did not change.
8. Opened Runs & Review, edited the transcript, and saved revision 2. The UI
   displayed `STALE: rerun required`.
9. Returned to Workbench and attempted the old Apply. The UI displayed
   `STALE_PROPOSAL: rerun after transcript edit`; no second mutation occurred.

## Timing and cleanup

- Audar transcription stage: 9,431.61 ms in the browser route record.
- Qwen function-call stage: 255,777.57 ms; total route remained bounded by the
  configured 360-second job cap.
- The browser remained interactive throughout the slow stage. The server
  health endpoint and view navigation succeeded while the child model process
  was active.
- After completion, no `llama-cli` child remained. The route record retained
  model hashes, raw output, stage graph, bypassed stages, latencies, and
  `REAL_LOCAL_END_TO_END` evidence.

## Browser evidence classification

`REAL_LOCAL_MODEL` and `REAL_LOCAL_END_TO_END`; not a demo-rule result and not
human-reviewed empirical gold. The browser snapshots and console traces were
generated locally by Playwright; private audio remains outside Git.
