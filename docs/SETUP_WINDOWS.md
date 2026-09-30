# Setup on Windows 10/11 (x64)

> **Status:** these steps are written for Windows but **have not yet been executed on a
> Windows machine**. All testing so far ran on Linux x86-64 (see IMPLEMENTATION_STATUS.md).
> The code avoids Linux-only features (paths via `pathlib`, `%LOCALAPPDATA%` data dir,
> no shell invocation, `taskkill` for the desktop shell), but please report any problem.

## 1. Prerequisites

1. **Python 3.11 (64-bit)** from <https://www.python.org/downloads/windows/>. Tick
   "Add python.exe to PATH". The `py` launcher is used by the setup script.
2. **Node.js 20 LTS or newer** from <https://nodejs.org/> (only needed to build the UI).
3. **FFmpeg** (includes `ffprobe`): e.g. `winget install Gyan.FFmpeg`, or download a build,
   unzip it, and add its `bin` folder to PATH. Check in a new terminal: `ffmpeg -version`.
4. ~1.5 GB free disk space (dependencies + the 350 MB Kokoro download, ~400 MB installed).

## 2. Install

```powershell
cd path\to\hamza-voice-studio
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This creates `.venv`, installs pinned Python packages (`backend\requirements-dev.txt`),
installs the UI dependencies (`npm ci`) and builds the UI into `frontend\dist`.

## 3. Start

Double-click `scripts\start.cmd` (or run `scripts\start.ps1`). A console window shows a link
like `http://127.0.0.1:8765/#token=…`, and your browser opens it. **Keep the console window
open**; closing it stops the studio (the worker process stops with it).

If port 8765 is busy, another free port is chosen automatically and printed.

## 4. Install a speech model

Open **Models → Kokoro 82M v1.0 → Install**, review the URL, size (334 MB), licence and
destination, then **Approve download**. After installation the studio works offline.

## 5. Desktop app (optional, experimental)

```powershell
cd desktop
npm install
npm start          # runs Electron against the repo's .venv and frontend\dist
```

Building an installer (`npm run dist:win`) additionally needs a bundled Python runtime in
`desktop\build\python` (the embeddable Python + installed requirements). That packaging
step is not automated or tested yet; the unsigned installer will show a SmartScreen warning.

## Data, backup, uninstall

- Data: `%LOCALAPPDATA%\HamzaVoiceStudio` (database, audio, exports, models, logs).
  Settings → Privacy & data shows the exact path.
- **Backup:** close the studio, copy that folder. **Restore:** copy it back. Models found
  on disk with a valid install manifest are detected automatically at startup.
- **Uninstall:** delete the repository folder (and `.venv`). Your data folder is kept
  unless you delete it yourself.

## Running the tests on Windows

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests            # unit + integration (mock engine)
$env:HVS_REAL_MODELS_DIR="$env:LOCALAPPDATA\HamzaVoiceStudio\models"
.\.venv\Scripts\python.exe -m pytest -m real backend\tests\real  # real Kokoro inference
```

(`test_crash_recovery.py` uses POSIX signals and is skipped on Windows.)
