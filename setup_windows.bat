@echo off
rem Kompatibilitaet: Einrichtung ohne Start. Normalerweise genuegt SignalDesk_starten.bat.
call "%~dp0SignalDesk_starten.bat" --setup-only %*
