; BARQ ONE v2.41.20 FRONTEND-ONLY UPDATE
; This installer never replaces Python executables, models, or application settings.
#define AppVersion "2.41.20"
#define ReactDir AddBackslash(SourcePath) + "..\web\react"
#if !FileExists(ReactDir + "\index.html")
 #error "Build fresh React UI before packaging the update."
#endif
#if !FileExists(ReactDir + "\audio\live-capture.js")
 #error "Missing AudioWorklet."
#endif

[Setup]
AppId={{9BB70D04-1EC5-4BC6-B811-64B08F5C8977}
AppName=BARQ ONE
AppVersion={#AppVersion}
AppVerName=BARQ ONE 2.41.20 UI Update
AppPublisher=BARQ ONE
DefaultDirName={localappdata}\Programs\AI Router Agent
UsePreviousAppDir=yes
DisableDirPage=no
DefaultGroupName=BARQ ONE
OutputDir=..\release
OutputBaseFilename=BARQ_UI_Update_2.41.20
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
; Replace ONLY frontend static resources in an existing verified BARQ install.
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
  AppPath: String;
  Target: String;
begin
  Result := '';
  AppPath := ExpandConstant('{app}\BARQ.exe');
  Target := ReactTarget('');
  if not FileExists(AppPath) then begin
    Result := 'This is a UI-only update. Install BARQ ONE v2.41.20 first. The full application was not found in the selected directory.';
    Exit;
  end;
  if not FileExists(AddBackslash(Target) + 'index.html') then begin
    Result := 'The installed BARQ React UI could not be located. A UI-only update cannot be safely applied to this version.';
    Exit;
  end;
end;
