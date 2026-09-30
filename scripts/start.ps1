# Start the studio on Windows and open it in the default browser.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
& ..\.venv\Scripts\python.exe -m app.run @args
