@echo off
setlocal
REM One-time explicit download. The Windows Setup option invokes BARQ_Wake.exe
REM directly: no global Python, Vosk, or pip required on the user's PC.
if exist "%~dp0BARQ_Wake.exe" (
  "%~dp0BARQ_Wake.exe" --install-model
  if errorlevel 1 goto fail
  echo Arabic voice wake installed; use START_BARQ_WAKE_AR.vbs to enable listening.
  pause
  exit /b 0
)
REM Developer/source fallback (Windows Python 3.11 is required in this mode).
py -3.11 -m pip install --user "vosk>=0.3.45,<1" "sounddevice>=0.5,<1" "pystray>=0.19,<1" "Pillow>=10,<13"
if errorlevel 1 goto fail
py -3.11 "%~dp0scripts\install_arabic_wake.py"
if errorlevel 1 goto fail
echo Arabic voice wake installed. Use START_BARQ_WAKE_AR.vbs to enable listening.
pause
exit /b 0
:fail
echo Voice wake setup failed. Check internet and model-download connectivity.
pause
exit /b 1
