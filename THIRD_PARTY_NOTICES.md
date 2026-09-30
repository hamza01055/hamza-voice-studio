# Third-party notices

This file lists third-party components used by Hamza Voice Studio. It is a starting point
for compliance review, not legal advice. Before distributing binaries, regenerate the full
dependency licence lists (e.g. `pip-licenses`, `npx license-checker`) and include the
licence texts required by each component.

## Downloaded at the user's request (not shipped in the repository)

| Component | Licence | Notes |
|---|---|---|
| Kokoro-82M v1.0 weights (`hexgrad/Kokoro-82M`, sherpa-onnx export) | Apache-2.0 | LICENSE file is included in the archive and kept in the model folder. |
| eSpeak-NG data (`espeak-ng-data/` inside the Kokoro archive) | GPL-3.0-or-later | Phoneme data for the eSpeak-NG library used by sherpa-onnx. |
| OpenAI Whisper weights (optional) | MIT | Only if the user installs a Whisper model. |

## Python runtime dependencies (`backend/requirements.txt`)

| Package | Licence |
|---|---|
| sherpa-onnx, sherpa-onnx-core | Apache-2.0 (bundles ONNX Runtime — MIT, and eSpeak-NG — **GPL-3.0-or-later**, and piper-phonemize — MIT) |
| FastAPI, Starlette, Pydantic, pydantic-settings, Uvicorn | MIT / BSD-3-Clause |
| SQLAlchemy, Alembic | MIT |
| python-multipart | Apache-2.0 |
| NumPy | BSD-3-Clause |
| soundfile (bundles libsndfile) | BSD-3-Clause (libsndfile: LGPL-2.1) |
| psutil | BSD-3-Clause |

**GPL note:** sherpa-onnx links eSpeak-NG (GPL-3.0-or-later). Distributing the application
together with this runtime may bring GPL obligations for the combined work. Options: keep the
source available under compatible terms, obtain legal advice, or replace the G2P front-end.

## Frontend / desktop (npm)

React, React DOM (MIT), TanStack Query (MIT), Radix UI primitives (MIT), lucide-react (ISC),
clsx (MIT), Tailwind CSS (MIT), Vite (MIT), Electron (MIT; bundles Chromium — BSD-style and
others, see Electron's `LICENSES.chromium.html`).

## External tools (installed by the user, not bundled)

FFmpeg / ffprobe — LGPL-2.1+ or GPL-2.0+ depending on the build. The application invokes the
user's installed binaries as separate processes.
