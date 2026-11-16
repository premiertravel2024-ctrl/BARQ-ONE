@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo [AI Router] Preparing the Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (echo Install Python 3.11+ and retry.& pause& exit /b 1)
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (echo Could not install dependencies.& pause& exit /b 1)
)
if not exist .env (
  copy .env.example .env >nul
  echo [AI Router] Enter a free Gemini key in the .env file before using voice.
  notepad .env
)
start "AI Router Voice Chat" http://127.0.0.1:8000/
.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
pause
