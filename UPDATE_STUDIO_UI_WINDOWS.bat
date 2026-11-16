@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where npm >nul 2>nul
if errorlevel 1 (
 echo Node.js LTS and npm are required. No files were changed.
 exit /b 2
)
pushd frontend
call npm ci --no-audit --no-fund
if errorlevel 1 (
 echo Dependency installation failed. Existing UI remains unchanged.
 popd
 exit /b 3
)
call npm run build
if errorlevel 1 (
 echo React build failed. Do not claim the new UI was installed.
 popd
 exit /b 4
)
popd
if not exist "web\react\index.html" exit /b 5
echo BARQ Studio UI source built to web\react successfully.
exit /b 0
