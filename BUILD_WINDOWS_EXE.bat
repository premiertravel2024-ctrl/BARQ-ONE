@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ENTRY=%~dp0"
set "ROOT="
rem Main v2.41.10 layout, anchored to this script's own folder.
if exist "%ENTRY%scripts\build_windows.ps1" set "ROOT=%ENTRY%"
rem Compatibility when a launcher was moved one folder down or a legacy zip was extracted.
if not defined ROOT if exist "%ENTRY%..\scripts\build_windows.ps1" set "ROOT=%ENTRY%..\"
if not defined ROOT if exist "%ENTRY%BARQ_Source\scripts\build_windows.ps1" set "ROOT=%ENTRY%BARQ_Source\"
if not defined ROOT (
    echo [ERROR] Cannot locate scripts\build_windows.ps1 next to the launcher.
    echo [INFO] Launcher folder: "%ENTRY%"
    echo [INFO] The full ZIP must be extracted, not just the BAT file.
    echo [INFO] Expected: scripts\build_windows.ps1 next to BUILD_BARQ.bat.
    echo [INFO] Files next to the launcher:
    dir /b "%ENTRY%"
    echo [INFO] Try extracting the ZIP to C:\BARQ and run BARQ\BUILD_BARQ.bat.
    goto :failed
)
for %%I in ("%ROOT%.") do set "ROOT=%%~fI\"
set "SCRIPT=%ROOT%scripts\build_windows.ps1"
set "VERSION=2.41.10"
echo ================================================================
echo BARQ AI %VERSION% - Windows setup builder
echo Build order: auto-install build tools - React - tests - PyInstaller - EXE check - Inno Setup
echo ================================================================
echo [INFO] Resolved source root: "%ROOT%"
echo [INFO] Using script: "%SCRIPT%"
if not exist "%ROOT%frontend\package.json" (
    echo [ERROR] frontend\package.json is missing - full source not extracted.
    goto :failed
)
if not exist "%ROOT%scripts\installer.iss" (
    echo [ERROR] scripts\installer.iss is missing - full source not extracted.
    goto :failed
)
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%SCRIPT%"
if errorlevel 1 (
    echo [ERROR] Build failed. Read the error ABOVE before trying Inno Setup.
    goto :failed
)
if not exist "%ROOT%release\build-ok-v%VERSION%.marker" (
    echo [ERROR] No success marker was produced. Do not install older builds.
    goto :failed
)
if not exist "%ROOT%release\BARQ_Setup_%VERSION%.exe" (
    echo [ERROR] The installer does not exist. The build did not finish.
    goto :failed
)
echo.
echo [OK] Verified installer: "%ROOT%release\BARQ_Setup_%VERSION%.exe"
echo [OK] Portable ZIP: "%ROOT%release\BARQ_Portable_%VERSION%.zip"
pause
exit /b 0
:failed
echo.
echo IMPORTANT: installer.iss is NOT the build launcher.
echo Do not compile it separately until BARQ.exe has been generated.
echo.
pause
exit /b 1
