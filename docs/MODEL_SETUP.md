# Model setup

Models are installed from the **Models** page. Nothing is downloaded without your approval;
the confirmation shows the exact artifact URL, size, weight licence and destination.

| Model | Download | Installed | Purpose | Status |
|---|---|---|---|---|
| Kokoro 82M v1.0 (`kokoro-multi-lang-v1_0`) | 334 MB (349,906,910 B) | ~384 MB | Speech generation, 53 built-in voices | Verified with real inference |
| Whisper tiny (`whisper-tiny-sherpa`) | 111 MB | ~160 MB | Transcription | Integrated, not yet verified |
| Whisper base (`whisper-base-sherpa`) | 198 MB | ~290 MB | Transcription | Integrated, not yet verified |

## How installation works

1. Disk space is checked (download + installed size + 10 %).
2. The archive is downloaded to `models/.partial/` (HTTP Range resume after interruption).
3. The sha256 is checked against the pinned value (Kokoro). For Whisper the checksum is
   recorded, because upstream does not publish one.
4. The archive is extracted safely into `models/.staging-*`, required files are checked, and
   the folder is moved into place atomically as `models/<model-id>/` with a
   `.hvs-install.json` manifest.
5. Interrupted installs are cleaned up at next start; partial downloads are resumed.

Remove a model from the Models page (refused while a job uses it). Projects and audio are kept.

## Offline use

After a model is installed nothing needs the network. Generation, transcription, export and
the UI all run on `127.0.0.1`. You can also copy a `models/<model-id>` folder (including its
`.hvs-install.json`) from another machine; it is detected at startup if its manifest matches
the pinned revision and checksum.

## Manual installation (air-gapped machines)

Download the artifact URL shown in the Models page on another machine, verify the sha256
listed in `MODEL_LICENSES.md`, then either (a) put the archive into `models/.partial/` with
its original file name and click Install (the complete file is detected and only verified +
extracted), or (b) let a connected machine install it and copy the resulting folder.

## Storing models elsewhere

Set `HVS_MODELS_DIR` (e.g. `D:\VoiceModels`) before starting.

## Adding another engine (developers)

1. Implement `TTSAdapter`/`ASRAdapter` in `backend/app/engines/` with honest `capabilities()`.
2. Add a registry entry with pinned artifact URL + sha256, code and weight licences,
   commercial status, verified vs experimental languages.
3. Register the factory in `ADAPTER_FACTORIES`.
4. Add `tests/real/…` smoke tests and update `MODEL_LICENSES.md` and `BENCHMARKS.md`.
5. If it needs PyTorch or conflicting dependencies, run it in its own worker environment.
