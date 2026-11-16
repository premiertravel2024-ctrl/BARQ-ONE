@echo off
setlocal
cd /d "%~dp0"
echo [BARQ] Downloading the official pinned LibreHardwareMonitor release, verifying SHA256, and preparing files for Setup.
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\install_hardware_monitor.ps1" -InstallOnly
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo [BARQ] Staging failed. No unverified sensors will be bundled.
if "%CODE%"=="0" echo [BARQ] Ready. BUILD_BARQ.bat will include the sensor binaries in the installer.
pause
exit /b %CODE%
