@echo off
setlocal
REM Opt-in to BARQ mic listener (always visible in the Windows tray).
wscript.exe "%~dp0START_BARQ_WAKE.vbs"
