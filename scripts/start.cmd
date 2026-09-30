@echo off
rem Start Hamza Voice Studio (double-click). Close this window to stop the studio.
cd /d "%~dp0..\backend"
"..\.venv\Scripts\python.exe" -m app.run %*
