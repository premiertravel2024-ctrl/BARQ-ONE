@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ROOT=%~dp0"
echo ================================================================
echo BARQ v2.17 - QUICK REACT BUILD CHECK (no EXE created)
echo ================================================================
if not exist "%ROOT%frontend\package-lock.json" (
    echo [ERROR] Missing frontend\package-lock.json - use FULL SOURCE ZIP.
    goto :fail
)
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js/npm not found. Install Node.js 22 LTS.
    goto :fail
)
where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python launcher missing. Install Python 3.11 x64.
    goto :fail
)
py -3.11 "%ROOT%scripts\verify_source_integrity.py"
if errorlevel 1 goto :fail
py -3.11 "%ROOT%scripts\verify_release_consistency.py"
if errorlevel 1 goto :fail
pushd "%ROOT%frontend"
call npm ci --no-audit --no-fund
if errorlevel 1 goto :fail_popped
call npm run test:imports
if errorlevel 1 goto :fail_popped
call npm run test:chat
if errorlevel 1 goto :fail_popped
call npm run build
if errorlevel 1 goto :fail_popped
popd
echo.
echo [PASS] The React UI compiled successfully; you can now run BUILD_BARQ.bat.
echo [NOTE] EXE validation still requires BUILD_BARQ.bat on Windows.
pause
exit /b 0
:fail_popped
popd
:fail
echo.
echo [FAIL] Fix the error above before running the Windows installer builder.
pause
exit /b 1
