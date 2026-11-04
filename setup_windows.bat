@echo off
setlocal
cd /d "%~dp0"
echo SignalDesk v1.0 - Windows Setup
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher 'py' fehlt. Installiere Python 3.10 oder neuer.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto failed
echo.
echo Setup abgeschlossen. Ollama bei Bedarf separat installieren:
echo https://ollama.com/download/windows
echo danach: ollama pull qwen3:8b
echo SignalDesk laeuft auch im Regelmodus ohne Ollama.
pause
exit /b 0
:failed
echo Setup fehlgeschlagen - bitte die Fehlermeldung oben lesen.
pause
exit /b 1
