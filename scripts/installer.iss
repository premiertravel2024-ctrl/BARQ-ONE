#define AppName "BARQ ONE"
#define AppVersion "2.41.15"
#define AppPublisher "BARQ ONE"
; The source directory is the scripts/ folder. Verify the executable BEFORE
; attempting to compile an installer: double-clicking installer.iss does NOT
; build the Windows application. SourcePath is provided by Inno Setup ISPP.
#define BinaryDir AddBackslash(SourcePath) + "..\dist\BARQ"
#if !FileExists(BinaryDir + "\BARQ.exe")
  #error "Missing dist\BARQ\BARQ.exe. Do NOT compile installer.iss directly. Run BUILD_BARQ.bat from the BARQ source folder first."
#endif

[Setup]
; CRITICAL: retain the original app identifier and install directory for in-place upgrades.
AppId={code:ApplicationId}
; Inno Setup requires this when AppId contains a runtime code constant.
UsePreviousLanguage=no
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\AI Router Agent
DisableDirPage=no
DefaultGroupName={#AppName}
OutputDir=..\release
OutputBaseFilename=BARQ_Setup_{#AppVersion}
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
[Dirs]
Name: "{app}\models\wake"
[Files]
Source: "..\scripts\install_presentmon.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\tools\presentmon\LICENSE.txt"; DestDir: "{app}\tools\presentmon"; Flags: ignoreversion
Source: "..\INSTALL_BARQ_FPS.bat"; DestDir: "{app}"; Flags: ignoreversion
; Extracted before installation: keep ahead of the large solid-compressed app.
Source: "..\scripts\ensure_webview2.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\inno_compiler_probe.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\find_inno.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\build_prerequisites.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#BinaryDir}\*"; Excludes: "\hardware-monitor,\hardware-monitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Keep the pinned sensor bundle separate from the legacy copy, which may be running elevated.
Source: "{#BinaryDir}\hardware-monitor\*"; DestDir: "{app}\hardware-monitor\bundled-v0.9.6"; Flags: replacesameversion recursesubdirs createallsubdirs
Source: "..\scripts\barq_wake_tray.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\START_BARQ_WAKE.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\START_BARQ_WAKE.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\barq_wake_vosk.py"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\install_arabic_wake.py"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\INSTALL_ARABIC_WAKE.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\START_BARQ_WAKE_AR.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\START_BARQ_WAKE_AR.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\INSTALL_BARQ_WAKE_STARTUP.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\INSTALL_BARQ_WAKE_STARTUP.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\SHOW_BARQ_FILES.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\install_hardware_monitor.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\read_screen_ocr.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\read_hardware_monitor.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\INSTALL_BARQ_SENSORS.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHECK_BARQ_SENSORS.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\install_windows_mcp.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\INSTALL_BARQ_WINDOWS_MCP.bat"; DestDir: "{app}"; Flags: ignoreversion
; System toolchain script is copied from the source, not generated remotely.
Source: "..\INSTALL_BARQ_TOOLKIT.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\BARQ_SYSTEM_ACCESS_INSTALL_REPORT_AR.md"; DestDir: "{app}"; Flags: ignoreversion
; Remove obsolete binary and shortcuts after the new release is copied. Never delete data.
[InstallDelete]
Type: files; Name: "{app}\AI Router Agent.exe"; Check: not IsSmoke
Type: files; Name: "{autoprograms}\AI Router Agent.lnk"; Check: not IsSmoke
Type: files; Name: "{autodesktop}\AI Router Agent.lnk"; Check: not IsSmoke
[UninstallDelete]
; The model is a BARQ install component, not user conversations/data.
Type: filesandordirs; Name: "{app}\models\wake\vosk-model-ar-mgb2-0.4"

[Icons]
Name: "{autoprograms}\BARQ"; Filename: "{app}\BARQ.exe"; IconFilename: "{app}\BARQ.exe"; Check: not IsSmoke
Name: "{autoprograms}\BARQ Wake Assistant"; Filename: "{app}\START_BARQ_WAKE.vbs"; Check: not IsSmoke
Name: "{autoprograms}\BARQ Arabic Wake"; Filename: "{app}\START_BARQ_WAKE_AR.vbs"; Check: not IsSmoke
Name: "{autoprograms}\BARQ - Installed Files"; Filename: "{app}\SHOW_BARQ_FILES.bat"; Check: not IsSmoke
Name: "{autoprograms}\BARQ - Repair Windows-MCP"; Filename: "{app}\INSTALL_BARQ_WINDOWS_MCP.bat"; Check: not IsSmoke
Name: "{autoprograms}\BARQ - Install or Repair Toolkit"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\INSTALL_BARQ_TOOLKIT.ps1"""; Check: not IsSmoke
Name: "{autoprograms}\BARQ - Repair CPU Sensors"; Filename: "{app}\INSTALL_BARQ_SENSORS.bat"; Check: not IsSmoke
Name: "{autodesktop}\BARQ"; Filename: "{app}\BARQ.exe"; IconFilename: "{app}\BARQ.exe"; Tasks: desktopicon; Check: (not IsSmoke) and (not IsBarqUpdate)
[Tasks]
Name: personalassistant; Description: "Keep BARQ ready in the background, start with Windows, enable wake microphone and ordinary computer commands"
Name: fpsmonitor; Description: "Prepare PresentMon for on-demand FPS measurement (official GitHub, internet if missing)"
Name: desktopicon; Description: "Create a desktop icon"; Flags: unchecked
Name: arabicwake; Description: "Install Arabic voice wake model (~318 MB download, saved inside selected BARQ folder; internet required)"
Name: privacyhelp; Description: "Open Windows microphone privacy settings after setup to grant access yourself"; Flags: unchecked
Name: computerconsent; Description: "Allow BARQ ordinary Windows control (no admin rights; ask for sensitive actions)"; Flags: unchecked
Name: hardwaresensors; Description: "Verify the bundled CPU/GPU temperature sensors"
Name: windowsmcp; Description: "Install Windows-MCP for enhanced BARQ desktop automation (Python 3.14 + uv, internet required)"
Name: toolchain; Description: "Install BARQ Windows toolchain system-wide where available (Git, Node, Python, VS Code, FFmpeg, search tools + Windows-MCP; internet required; may request Windows approval)"
Name: autostart; Description: "Start BARQ in the Windows notification area when you sign in (microphone remains user-controlled)"; Flags: unchecked
; No console-based model download: Inno Setup owns the progress page,
; then executes the bundled model extractor hidden.

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\install_presentmon.ps1"""; Description: "Prepare FPS measurement"; Flags: postinstall skipifsilent; Tasks: fpsmonitor; Check: not IsSmoke
; A checked toolkit task is informed opt-in in the visible Setup wizard.
; The installer uses the included, pinned tool installer and records failures.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\INSTALL_BARQ_TOOLKIT.ps1"""; Description: "Install BARQ Windows toolkit"; Flags: postinstall skipifsilent; Tasks: toolchain; Check: not IsSmoke
; Windows-MCP requires an explicit setup-task choice (checked by default).
; Failure leaves native Windows control working and writes a diagnostic log.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\install_windows_mcp.ps1"""; Description: "Install Windows-MCP desktop bridge for BARQ"; Flags: postinstall skipifsilent; Tasks: windowsmcp; Check: not IsSmoke
; Run only after the user selects the optional hardware sensor component.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\install_hardware_monitor.ps1"""; Description: "Configure hardware temperature sensors for BARQ"; Flags: postinstall skipifsilent; Tasks: hardwaresensors; Check: not IsSmoke
; Windows privacy permissions CANNOT be silently granted by installers.
; Let the user confirm the microphone setting in Windows after installation.
Filename: "ms-settings:privacy-microphone"; Description: "Review Windows microphone access for BARQ"; Flags: shellexec postinstall skipifsilent; Tasks: privacyhelp; Check: not IsSmoke

Filename: "{app}\BARQ.exe"; WorkingDir: "{app}"; Flags: nowait; Check: IsBarqUpdate

[Code]
var
  WakeDownloadPage: TDownloadWizardPage;
  WakeArchiveReady: Boolean;

function IsSmoke: Boolean;
begin
  Result := ExpandConstant('{param:BARQSMOKE|0}') = '1';
end;

function IsBarqUpdate: Boolean;
begin
  Result := (not IsSmoke) and WizardSilent and (ExpandConstant('{param:BARQUPDATE|0}') = '1');
end;

function ApplicationId(Param: String): String;
begin
  if IsSmoke then
    Result := 'BARQ-Smoke-' + ExpandConstant('{param:SMOKEID|isolated}')
  else
    Result := '{9BB70D04-1EC5-4BC6-B811-64B08F5C8977}';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
  Args: String;
begin
  Result := '';
  if IsSmoke then Exit;
  ExtractTemporaryFile('ensure_webview2.ps1');
  ExtractTemporaryFile('build_prerequisites.ps1');
  Args := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{tmp}\ensure_webview2.ps1') + '"';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Args, '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
    Result := 'Unable to start the WebView2 runtime check. Please retry Setup.';
    Exit;
  end;
  if ExitCode <> 0 then
    Result := 'WebView2 could not be verified. Check your connection, then retry. Log: ' +
      ExpandConstant('{localappdata}\Bq\deps\bootstrap\build-prerequisites.log');
end;

function WakeAlreadyInstalled: Boolean;
var
  ModelDir: String;
begin
  ModelDir := AddBackslash(WizardDirValue) + 'models\wake\vosk-model-ar-mgb2-0.4\';
  Result := DirExists(ModelDir + 'am') and DirExists(ModelDir + 'conf');
end;

function ShouldInstallWake: Boolean;
begin
  // Silent smoke checks must never download 318 MB or enable the microphone.
  Result := (not IsSmoke) and (not WizardSilent) and
    WizardIsTaskSelected('arabicwake') and (not WakeAlreadyInstalled);
end;

procedure InitializeWizard;
begin
  WakeArchiveReady := False;
  WakeDownloadPage := CreateDownloadPage(
    'BARQ - Arabic voice installation',
    'Downloading the offline Arabic wake model inside BARQ Setup. Do not close Setup.', nil);
  WakeDownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID <> wpReady then Exit;
  WakeArchiveReady := False;
  if not ShouldInstallWake then Exit;

  WakeDownloadPage.Clear;
  WakeDownloadPage.Add(
    'https://alphacephei.com/vosk/models/vosk-model-ar-mgb2-0.4.zip',
    'vosk-model-ar-mgb2-0.4.zip', '');
  WakeDownloadPage.Show;
  try
    try
      WakeDownloadPage.Download;
      WakeArchiveReady := FileExists(ExpandConstant('{tmp}\vosk-model-ar-mgb2-0.4.zip'));
      if not WakeArchiveReady then
        RaiseException('Arabic wake archive was not downloaded.');
      Log('BARQ: Arabic voice model downloaded by Setup.');
    except
      Result := False;
      if not WakeDownloadPage.AbortedByUser then
        MsgBox('Arabic voice download failed: ' + GetExceptionMessage + #13#10 +
          'Check your connection and press Install to retry, or uncheck the model option.',
          mbError, MB_OK);
    end;
  finally
    WakeDownloadPage.Hide;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
  WakeExe, Archive, ModelDir: String;
begin
  if (CurStep <> ssPostInstall) or IsBarqUpdate then Exit;
  if (not IsSmoke) and WizardIsTaskSelected('computerconsent') then begin
    ExitCode := -1;
    if (not Exec(ExpandConstant('{app}\BARQ.exe'),
      '--setup-computer-consent', ExpandConstant('{app}'), SW_HIDE,
      ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
      RaiseException('Could not enable BARQ computer interaction. Configure in application settings.');
  end;
  if (not IsSmoke) and WizardIsTaskSelected('personalassistant') then begin
    ExitCode := -1;
    if (not Exec(ExpandConstant('{app}\BARQ.exe'),
      '--setup-personal-assistant', ExpandConstant('{app}'), SW_HIDE,
      ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
      RaiseException('BARQ personal background setup failed. Configure background listening in Settings.');
  end;
  if WizardIsTaskSelected('autostart') then begin
    ExitCode := -1;
    if (not Exec(ExpandConstant('{app}\BARQ.exe'),
      '--setup-background-start', ExpandConstant('{app}'), SW_HIDE,
      ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
      RaiseException('BARQ Windows startup setup failed; configure it from BARQ settings.');
  end;
  if not WakeArchiveReady then Exit;
  WakeExe := ExpandConstant('{app}\BARQ_Wake.exe');
  Archive := ExpandConstant('{tmp}\vosk-model-ar-mgb2-0.4.zip');
  ModelDir := ExpandConstant('{app}\models\wake\vosk-model-ar-mgb2-0.4');
  if (not FileExists(WakeExe)) or (not FileExists(Archive)) then
    RaiseException('Arabic wake installer files are missing.');

  ExitCode := -1;
  // The helper is packaged in BARQ_Setup; no terminal/CMD, global Python or
  // second network download. It validates the zip before extracting to {app}.
  if (not Exec(WakeExe,
    '--install-model-from-archive "' + Archive + '"',
    ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode)) or
    (ExitCode <> 0) then
    RaiseException('Arabic model extraction failed. Review disk space and retry setup.');
  if (not DirExists(ModelDir + '\am')) or
     (not DirExists(ModelDir + '\conf')) then
    RaiseException('Arabic model extraction incomplete. Setup cannot mark voice ready.');
  DeleteFile(Archive);
  Log('BARQ: offline Arabic voice model verified in ' + ModelDir);
end;
