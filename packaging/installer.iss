; Inno Setup script for SD Time вЂ” build with  .\build.ps1
; Per-user install (no admin rights), Start menu shortcut, optional desktop shortcut and
; autostart, clean uninstall. Your time data in %APPDATA%\SD_Time is kept unless you
; choose to delete it when uninstalling.

#define AppName "SD Time"
#define AppExe "SD Time.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Never change AppId: Windows uses it to recognise updates of the same app.
AppId={{EEC5EE27-1E6B-4F9B-BE74-7A3F132F3E36}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=SanddogFX
AppPublisherURL=https://github.com/sanddogfx/SD_Time
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=SD_Time_Setup_{#AppVersion}
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; The app holds this mutex; setup asks you to close SD Time before updating/uninstalling.
AppMutex=SD_Time_AppMutex
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start SD Time when Windows starts (in the tray)"; Flags: unchecked

[InstallDelete]
; Remove the previous version's libraries so updates don't leave stale files behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\SD Time\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value the app's Settings > "Start with Windows" uses.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --hidden"; Tasks: autostart; \
  Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
    { Autostart may also have been switched on later from Settings. }
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#AppName}');
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\SD_Time');
    if DirExists(DataDir) then
      { Default answer (and the silent-mode answer) is No: your time entries are kept. }
      if SuppressibleMsgBox('Also delete your SD Time data (time entries, projects, settings)?' + #13#10 +
                            DataDir + #13#10#13#10 + 'This cannot be undone.',
                            mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
