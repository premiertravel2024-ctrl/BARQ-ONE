@echo off
setlocal
set "APP=%~dp0"
set "DATA=%LOCALAPPDATA%\AI Router Agent"
echo BARQ application and included dependencies:
echo   %APP%
echo.
echo Optional Arabic voice wake model:
echo   %APP%models\wake

echo Existing user settings and chat data (not deleted by upgrades):
echo   %DATA%
echo.
if not exist "%APP%BARQ.exe" echo WARNING: BARQ.exe is missing here.
if not exist "%APP%BARQ_Wake.exe" echo WARNING: BARQ_Wake.exe is missing here.
start "" explorer.exe "%APP%"
set /p OPEN_DATA=Open user data folder too? (Y/N):
if /i "%OPEN_DATA%"=="Y" if exist "%DATA%" start "" explorer.exe "%DATA%"
endlocal
