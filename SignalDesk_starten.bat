@echo off
rem SignalDesk - Ein-Klick-Start fuer Windows.
rem Doppelklick genuegt: richtet beim ersten Mal alles ein und oeffnet danach den Browser.
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title SignalDesk

rem --- ZIP nicht entpackt? (Explorer startet Dateien aus ZIPs in einem Temp-Ordner)
echo "%~dp0" | findstr /i /c:"\AppData\Local\Temp\" >nul
if not errorlevel 1 (
  echo.
  echo  Bitte die ZIP-Datei zuerst entpacken:
  echo  Rechtsklick auf die ZIP-Datei - "Alle extrahieren..." - im entpackten Ordner
  echo  erneut "SignalDesk_starten.bat" doppelklicken.
  echo.
  pause
  exit /b 1
)

rem --- Python 3.10+ suchen (py-Launcher, python, typische Installationsorte)
set "PY="
call :try_python py -3
if not defined PY call :try_python python
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PY call :try_python "%%~D\python.exe"
if not defined PY goto :no_python

:run
%PY% -m sales_tool.bootstrap %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo  SignalDesk wurde mit einem Fehler beendet ^(Code %RC%^). Die Meldung steht oben.
  pause
)
exit /b %RC%

:try_python
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b 0

:no_python
echo.
echo  Fuer SignalDesk wird Python 3.10 oder neuer benoetigt - es ist noch nicht installiert.
echo.
where winget >nul 2>nul
if errorlevel 1 goto :manual_python
choice /c JN /m " Python jetzt automatisch installieren (Microsoft winget, ca. 30 MB)"
if errorlevel 2 goto :manual_python
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PY call :try_python "%%~D\python.exe"
if not defined PY call :try_python py -3
if defined PY (
  echo.
  echo  Python ist installiert. SignalDesk wird jetzt eingerichtet ...
  goto :run
)
echo.
echo  Python wurde installiert, ist aber in diesem Fenster noch nicht sichtbar.
echo  Bitte dieses Fenster schliessen und "SignalDesk_starten.bat" erneut doppelklicken.
pause
exit /b 1

:manual_python
echo  Die Download-Seite wird geoeffnet. Bei der Installation unbedingt
echo  "Add python.exe to PATH" anhaken. Danach diese Datei erneut doppelklicken.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
