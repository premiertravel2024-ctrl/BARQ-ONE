@echo off
setlocal
chcp 65001 >nul
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama is not installed or not on PATH. Install/start Ollama first.
  pause
  exit /b 1
)
echo.
echo BARQ - free local coding models. No API key required.
echo 1. Qwen2.5-Coder 7B ^(4.7 GB, recommended for 8GB VRAM^)
echo 2. DeepSeek-Coder 6.7B ^(3.8 GB, alternative^)
echo 3. Qwen3 4B ^(2.5 GB, lightweight general brain^)
echo 4. Qwen2.5-Coder 1.5B ^(1 GB, fast fallback^)
echo.
set "MODEL="
set /p PICK=Choose model to download [1-4] or X to cancel: 
if /I "%PICK%"=="X" exit /b 0
if "%PICK%"=="1" set "MODEL=qwen2.5-coder:7b"
if "%PICK%"=="2" set "MODEL=deepseek-coder:6.7b"
if "%PICK%"=="3" set "MODEL=qwen3:4b"
if "%PICK%"=="4" set "MODEL=qwen2.5-coder:1.5b"
if not defined MODEL (
 echo Invalid choice. Nothing downloaded.
 pause
 exit /b 2
)
echo Downloading %MODEL% from Ollama. This uses network bandwidth and disk space.
ollama pull %MODEL%
if errorlevel 1 (
 echo Model download failed. Verify your connection and free disk space.
 pause
 exit /b 1
)
echo.
ollama list
echo.
echo Download complete. In BARQ, open Settings / Models and refresh local models.
pause
