@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo =================================================
echo BARQ v2.30 - FastAPI repair and verified build
echo =================================================
if not exist "%~dp0scripts\repair_fastapi_build.py" (
   echo [ERROR] Repair files not found. Extract this ZIP inside the BARQ source folder.
   pause
   exit /b 2
)
where py >nul 2>&1
if errorlevel 1 (
   echo [ERROR] Install Python 3.11 x64 with Windows Python Launcher ^(py^).
   pause
   exit /b 3
)
py -3.11 "%~dp0scripts\repair_fastapi_build.py" --root "%~dp0"
if errorlevel 1 (
   echo [ERROR] FastAPI source repair/check failed. Build blocked.
   pause
   exit /b 4
)
echo [BARQ] Verified source folder: %~dp0
echo [BARQ] Starting normal release gate. Do NOT compile installer.iss separately.
call "%~dp0BUILD_BARQ.bat"
if errorlevel 1 (
   echo [BARQ ERROR] Build failed. Read full traceback in release\python-tests.log
   if exist "%~dp0release\BARQ_DIAGNOSTICS.zip" echo [BARQ ERROR] Attach release\BARQ_DIAGNOSTICS.zip to diagnose remaining errors.
   pause
   exit /b 5
)
echo [BARQ] Verified build finished.
pause
exit /b 0
