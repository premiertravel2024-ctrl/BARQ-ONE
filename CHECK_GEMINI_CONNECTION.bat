@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check_gemini_network.ps1"
set RESULT=%ERRORLEVEL%
echo.
echo Diagnostic exit code: %RESULT%
pause
exit /b %RESULT%
