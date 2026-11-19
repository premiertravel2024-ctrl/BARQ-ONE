@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ROOT=%~dp0"
echo ================================================================
echo BARQ AI v2.41.14 - Windows Installer Builder
echo ================================================================
echo [INFO] Source folder: "%ROOT%"
if not exist "%ROOT%scripts\build_windows.ps1" (
    echo [ERROR] The scripts folder was not found next to BUILD_BARQ.bat.
    echo [ERROR] Extract the FULL ZIP, not the BAT file alone.
    echo [ERROR] Expected: "%ROOT%scripts\build_windows.ps1"
    echo [INFO] Current directory contents:
    dir /b "%ROOT%"
    pause
    exit /b 1
)
call "%ROOT%BUILD_WINDOWS_EXE.bat"
if errorlevel 1 (echo [ERROR] The BARQ build did not finish.& pause& exit /b 1)
if not exist "%ROOT%release\BARQ_Setup_2.41.14.exe" (echo [ERROR] Missing Setup.exe.& pause& exit /b 2)
if not exist "%ROOT%release\build-ok-v2.41.14.marker" (echo [ERROR] Missing build success marker.& pause& exit /b 3)
echo.
echo [SUCCESS] Installer: "%ROOT%release\BARQ_Setup_2.41.14.exe"
explorer.exe "%ROOT%release"
pause
exit /b 0
