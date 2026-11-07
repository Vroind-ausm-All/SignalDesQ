@echo off
rem SignalDesk - Sicherung wiederherstellen.
rem Sicherungsdatei (signaldesk-....sqlite3 oder .sdenc) per Maus auf diese Datei ziehen.
rem Der aktuelle Stand wird vorher automatisch gesichert.
if "%~1"=="" (
  echo.
  echo  Bitte eine Sicherungsdatei auf diese Datei ziehen, z. B. aus %USERPROFILE%\.akquise-tool\backups
  echo.
  pause
  exit /b 1
)
call "%~dp0SignalDesk_starten.bat" --restore "%~1"
