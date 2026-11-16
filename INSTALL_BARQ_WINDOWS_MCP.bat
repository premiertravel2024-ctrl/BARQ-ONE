@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_windows_mcp.ps1" -Repair
if errorlevel 1 (
  echo [ERROR] Windows-MCP setup failed. See %%LOCALAPPDATA%%\AI Router Agent\logs\windows-mcp-install.log
) else (
  echo [OK] Windows-MCP is installed for your Windows user.
)
pause
