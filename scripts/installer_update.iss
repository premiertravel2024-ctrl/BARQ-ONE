; BARQ IN-PLACE UPDATE. Same AppId and directory as installed v2.30.0.
; Fresh binaries only. Never deletes conversations, settings or the 318MB Arabic voice model.
#define AppName "BARQ"
#define AppVersion "2.30.0"
#define BinaryDir AddBackslash(SourcePath) + "..\dist\BARQ"
#if !FileExists(BinaryDir + "\BARQ.exe")
  #error "Build BARQ.exe first from source using BUILD_BARQ.bat."
#endif
#if !FileExists(BinaryDir + "\BARQ_Wake.exe")
  #error "Build BARQ_Wake.exe first; this update requires the bundled wake runtime."
#endif

[Setup]
AppId={{9BB70D04-1EC5-4BC6-B811-64B08F5C8977}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=BARQ
DefaultDirName={localappdata}\Programs\AI Router Agent
DisableDirPage=no
DefaultGroupName=BARQ
OutputDir=..\release
OutputBaseFilename=BARQ_Update_{#AppVersion}_VoiceWake
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\BARQ.exe
CloseApplications=yes
RestartApplications=no
UsePreviousLanguage=no
CreateUninstallRegKey=no
UpdateUninstallLogAppName=no

[Files]
; Replace the existing runtime in place, preserve user files and Vosk model.
Source: "{#BinaryDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\scripts\install_hardware_monitor.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\read_hardware_monitor.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\INSTALL_BARQ_SENSORS.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHECK_BARQ_SENSORS.bat"; DestDir: "{app}"; Flags: ignoreversion
; When an official SHA256-verified release has been staged with STAGE_BARQ_SENSORS.bat,
; bundle it in Setup. Otherwise the checked sensor task downloads it after installation.
#if DirExists(AddBackslash(SourcePath) + "..\hardware-monitor")
Source: "..\hardware-monitor\*"; DestDir: "{app}\hardware-monitor"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif

[Icons]
Name: "{autoprograms}\BARQ"; Filename: "{app}\BARQ.exe"; Check: not WizardSilent
Name: "{autoprograms}\BARQ - Repair CPU Sensors"; Filename: "{app}\INSTALL_BARQ_SENSORS.bat"; Check: not WizardSilent

[Tasks]
Name: privacyhelp; Description: "Open Windows microphone settings after update (user approval required)"; Flags: unchecked
Name: computerconsent; Description: "Allow BARQ to use ordinary Windows desktop tools (no administrator access; sensitive actions still need confirmation)"
Name: autostart; Description: "Start BARQ in the Windows notification area when you sign in (microphone remains user-controlled)"; Flags: unchecked
Name: hardwaresensors; Description: "Install local CPU-temperature sensor application (LibreHardwareMonitor, official GitHub, internet required)"

[Run]
Filename: "ms-settings:privacy-microphone"; Description: "Review microphone privacy settings for BARQ"; Flags: shellexec postinstall skipifsilent; Tasks: privacyhelp
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\install_hardware_monitor.ps1"""; Flags: postinstall skipifsilent; Tasks: hardwaresensors; Description: "Install local hardware sensors for optional CPU-temperature readings"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
begin
  if CurStep <> ssPostInstall then Exit;
  if WizardIsTaskSelected('computerconsent') then begin
    ExitCode := -1;
    if (not Exec(ExpandConstant('{app}\BARQ.exe'),
      '--setup-computer-consent', ExpandConstant('{app}'), SW_HIDE,
      ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
      RaiseException('BARQ computer permission setup failed; configure it manually in BARQ settings.');
  end;
  if WizardIsTaskSelected('autostart') then begin
    ExitCode := -1;
    if (not Exec(ExpandConstant('{app}\BARQ.exe'),
      '--setup-background-start', ExpandConstant('{app}'), SW_HIDE,
      ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
      RaiseException('BARQ Windows startup setup failed; configure it from BARQ settings.');
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;
