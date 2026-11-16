@echo off
setlocal EnableExtensions DisableDelayedExpansion
echo [BARQ 2.16.1] Live Workspace requires the NEW React build.
echo Old bundled UI would hide the live coding editor.
echo Switching to the full verified build instead.
call "%~dp0BUILD_BARQ.bat"
exit /b %errorlevel%
