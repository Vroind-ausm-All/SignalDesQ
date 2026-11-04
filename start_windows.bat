@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -m sales_tool
) else (
  echo .venv fehlt. Bitte zuerst setup_windows.bat starten.
  pause
)
