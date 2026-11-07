@echo off
rem SignalDesk ohne Internet starten: nichts installieren, keine Abrufe (Offline-Modus fuer diese Sitzung).
call "%~dp0SignalDesk_starten.bat" --offline %*
