; BARQ ONE v2.41.2 incrementally updates PyInstaller EXE and compiled React only.
#define AppVersion "2.41.2"
#define ExePath AddBackslash(SourcePath) + "..\dist\BARQ\BARQ.exe"
#define WebDir AddBackslash(SourcePath) + "..\web\react"
#if !FileExists(ExePath)
 #error "Build and verify a fresh BARQ.exe before packaging the incremental update."
#endif
#if !FileExists(WebDir + "\index.html")
 #error "Fresh React index.html is missing."
#endif
#if !FileExists(WebDir + "\audio\live-capture.js")
 #error "Voice audio worklet is missing."
#endif

[Setup]
AppId={{9BB70D04-1EC5-4BC6-B811-64B08F5C8977}
AppName=BARQ ONE
AppVersion={#AppVersion}
AppVerName=BARQ ONE v2.41.2 Core and UI Update
AppPublisher=BARQ ONE
DefaultDirName={localappdata}\Programs\AI Router Agent
UsePreviousAppDir=yes
DisableDirPage=no
DefaultGroupName=BARQ ONE
OutputDir=..\release
OutputBaseFilename=BARQ_Core_UI_Update_2.41.2
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=..\assets\app.ico
CloseApplications=yes
RestartApplications=no
CreateUninstallRegKey=no
Uninstallable=no
UsePreviousLanguage=no

[Files]
; Update only the backend application EXE and React resources. Preserve models and data.
Source: "..\dist\BARQ\BARQ.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\web\react\*"; DestDir: "{code:ReactTarget}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Code]
function ReactTarget(Param: String): String;
begin
  if DirExists(ExpandConstant('{app}\_internal\web\react')) then
    Result := ExpandConstant('{app}\_internal\web\react')
  else
    Result := ExpandConstant('{app}\web\react');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  InstalledExecutable: String;
  UiDir: String;
begin
  Result := '';
  InstalledExecutable := ExpandConstant('{app}\BARQ.exe');
  UiDir := ReactTarget('');
  if not FileExists(InstalledExecutable) then begin
    Result := 'This update requires an existing BARQ ONE 2.41.2 installation. Install BARQ first.';
    Exit;
  end;
  if not DirExists(ExpandConstant('{app}\_internal')) then begin
    Result := 'This installation is not a compatible PyInstaller onedir build. Use the complete installer.';
    Exit;
  end;
  if not FileExists(AddBackslash(UiDir) + 'index.html') then begin
    Result := 'No compatible React UI was found. Use the complete installer.';
    Exit;
  end;
end;
