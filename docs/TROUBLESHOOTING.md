# Troubleshooting

Logs: `<data dir>/logs/api.log` and `worker.log` (Settings → Privacy & data shows the data dir).
Logs contain IDs and error codes, never your script text.

| Symptom | Cause | Fix |
|---|---|---|
| "Open the studio from its launcher" | The page was opened without the session token. | Use the link printed by `scripts/start` (it contains `#token=…`), or the desktop app. A new token is created on every launch. |
| "FFmpeg and ffprobe are required…" / MP3 export or voice upload fails | FFmpeg missing from PATH. | Install FFmpeg (Windows: `winget install Gyan.FFmpeg`) and restart the studio. `ffmpeg -version` must work in a new terminal. |
| No GPU used | The bundled sherpa-onnx runtime is CPU-only. | Expected. The Models page shows "Device used: CPU". Kokoro runs faster than real time on most modern CPUs; see BENCHMARKS.md for measured numbers. |
| Insufficient VRAM / GPU runtime missing | Not applicable to the current engines (CPU). | A future GPU engine will report this on the Models page. |
| Slow generation | Few CPU cores, other heavy programs, long segments. | Close other apps; keep segments to a paragraph; set `HVS_INFERENCE_THREADS` to your physical core count. Progress is per sentence. |
| "Not enough free disk space" (HTTP 507) | Install needs download + extracted size. | Free space or set `HVS_MODELS_DIR` to another drive. |
| Download failed / interrupted | Network problem. | Press Retry install; the partial file is resumed. |
| "failed its integrity check" | Corrupt or tampered download. | The file was deleted; retry. If it repeats, check proxy/antivirus interference. |
| "Files missing" on a model | Model folder was edited/deleted. | Remove and reinstall the model. |
| Permission errors writing data | Data dir not writable (e.g. redirected profile). | Set `HVS_DATA_DIR` to a writable folder. |
| "Port … is already in use" | Another program uses 8765. | The launcher picks a free port automatically; with `--strict-port` choose another with `--port`. |
| Voice upload rejected: "could not be decoded" | Not audio, corrupt, or unsupported codec. | Convert to WAV/FLAC/MP3 and retry. |
| Voice upload rejected: silent/too short/too long | Recording quality checks. | Record 5–20 s of clear speech from one speaker; trim long silences. |
| Job shows "Interrupted" | The worker or app stopped during the job. | Press Retry in the Jobs page. Jobs are re-queued once automatically. |
| Worker keeps crashing | Model files corrupt or out of memory. | Check `worker.log`; reinstall the model; close memory-heavy apps. After 5 crashes/minute the supervisor stops restarting; restart the studio. |
| Cancel doesn't stop instantly | Kokoro can only stop between sentences. | Wait a few seconds; the job ends as Cancelled and no take is saved. |
| Export failed "no selected take" | Some segments have no take selected. | Generate/select takes, or enable "Skip segments without a selected take". |
| Export failed "duration did not match" | FFmpeg produced an invalid file. | The file was discarded; retry. Check FFmpeg version. |
| "Text changed since take" badge | You edited the text after generating. | Generate a new take; the old one is kept and marked as made from older text. |
| Live updates reconnecting | The service restarted or stopped. | It reconnects automatically; reload the page if the service was restarted. |
