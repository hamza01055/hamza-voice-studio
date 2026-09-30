# One-time setup on Windows (PowerShell). Requires Python 3.11 (python.org, "Add to PATH"),
# Node.js 20+ and FFmpeg on PATH. Run:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Warning "ffmpeg not found on PATH (needed for import/export). See docs/SETUP_WINDOWS.md" }
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r backend\requirements-dev.txt
Push-Location frontend
npm ci
npm run build
Pop-Location
Write-Host "Setup complete. Start with: scripts\start.cmd"
