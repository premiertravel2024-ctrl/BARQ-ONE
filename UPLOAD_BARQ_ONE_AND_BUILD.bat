@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
echo =========================================
echo BARQ ONE - Upload source and build Windows installer
 echo =========================================
where git >nul 2>&1 || (echo ERROR: Git is required. Install Git for Windows.& pause & exit /b 1)
if not exist ".github\workflows\windows-build.yml" (echo ERROR: Windows build workflow missing.& pause & exit /b 1)
if not exist "frontend\package-lock.json" (echo ERROR: Frontend lockfile missing.& pause & exit /b 1)
if not exist ".git" git init -b main || (pause & exit /b 1)
git remote get-url origin >nul 2>&1
if errorlevel 1 (git remote add origin https://github.com/premiertravel2024-ctrl/BARQ-ONE.git) else (
  for /f "delims=" %%U in ('git remote get-url origin') do set "OLD_REMOTE=%%U"
  if /I not "!OLD_REMOTE!"=="https://github.com/premiertravel2024-ctrl/BARQ-ONE.git" (
    echo ERROR: Existing git origin is different: !OLD_REMOTE!
    echo Review it manually; refusing to replace the remote.
    pause & exit /b 1
  )
)
git add -A || (pause & exit /b 1)
git diff --cached --quiet
if errorlevel 1 (
  git -c user.name="BARQ Source Upload" -c user.email="barq-source-upload@users.noreply.github.com" commit -m "Integrate BARQ listening room and Windows installer workflow" || (pause & exit /b 1)
)
echo.
echo Pushing main to BARQ-ONE. GitHub sign-in may be requested.
git push -u origin HEAD:main
if errorlevel 1 (echo ERROR: Push failed; inspect Git credentials or remote state.& pause & exit /b 1)
echo.
echo Source pushed. GitHub Actions should run the Windows installer build.
echo Open: https://github.com/premiertravel2024-ctrl/BARQ-ONE/actions
start "" "https://github.com/premiertravel2024-ctrl/BARQ-ONE/actions"
pause
