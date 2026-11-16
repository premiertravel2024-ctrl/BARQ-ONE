@echo off
setlocal
cd /d "%~dp0"
echo Open installed BARQ, enable voice and computer permissions, then follow each spoken scenario.
py -3.11 scripts\voice_windows_e2e.py --interactive
set "BARQ_RESULT=%ERRORLEVEL%"
echo Report: release\voice-e2e\voice-e2e.md
pause
exit /b %BARQ_RESULT%
