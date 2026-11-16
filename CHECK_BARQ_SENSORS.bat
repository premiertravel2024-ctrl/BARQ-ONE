@echo off
setlocal
set "APP=%~dp0"
set "DLL=%APP%hardware-monitor\LibreHardwareMonitorLib.dll"
if exist "%DLL%" (
  echo [BARQ] Checking real local CPU and GPU sensor values...
  powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%APP%scripts\read_hardware_monitor.ps1" -LibraryPath "%DLL%"
  if not errorlevel 1 goto :success
)
echo [BARQ] Direct sensor reading not available. Testing WMI...
powershell.exe -NoProfile -NonInteractive -Command "Get-CimInstance -Namespace root\LibreHardwareMonitor -ClassName Sensor -ErrorAction Stop | Where-Object SensorType -eq Temperature | Select-Object Name,Value"
if errorlevel 1 echo [BARQ] No usable WMI channel. Try INSTALL_BARQ_SENSORS.bat or check Windows sensor-driver permission.
pause
exit /b 1
:success
echo [BARQ] Actual sensor output shown above.
pause
exit /b 0
