# BARQ read-only CPU/GPU temperature query from the locally installed official DLL.
# Only launched by core.hardware_sensors with a fixed path under BARQ's install folder.
param([Parameter(Mandatory=$true)][string]$LibraryPath)
$ErrorActionPreference='Stop'
if (!(Test-Path -LiteralPath $LibraryPath -PathType Leaf)) { exit 2 }
try {
    Add-Type -Path $LibraryPath -ErrorAction Stop
    $computer=New-Object LibreHardwareMonitor.Hardware.Computer
    $computer.IsCpuEnabled=$true
    $computer.IsGpuEnabled=$true
    $computer.IsStorageEnabled=$true
    $computer.Open()
    try {
        $data=New-Object System.Collections.Generic.List[object]
        foreach($hardware in $computer.Hardware){
            $hardware.Update()
            foreach($sensor in $hardware.Sensors){
                if($sensor.SensorType.ToString() -eq 'Temperature' -and $null -ne $sensor.Value){
                    $data.Add([pscustomobject]@{Name=[string]$sensor.Name;Identifier=[string]$sensor.Identifier;Parent='';Value=[double]$sensor.Value;SensorType='Temperature'})
                }
            }
            foreach($sub in $hardware.SubHardware){
                $sub.Update()
                foreach($sensor in $sub.Sensors){
                    if($sensor.SensorType.ToString() -eq 'Temperature' -and $null -ne $sensor.Value){
                        $data.Add([pscustomobject]@{Name=[string]$sensor.Name;Identifier=[string]$sensor.Identifier;Parent='';Value=[double]$sensor.Value;SensorType='Temperature'})
                    }
                }
            }
        }
        if($data.Count -lt 1){ exit 4 }
        ConvertTo-Json -InputObject @($data.ToArray()) -Compress -Depth 3
    } finally { $computer.Close() }
} catch {
    # Don't leak local paths, traces, or errors into the chat; caller returns
    # a grounded sensor-unavailable status instead of fabricated temperatures.
    exit 3
}
