; Installateur Windows OverLoad (Inno Setup 6)
; Build : iscc /DMyAppVersion=1.0.0 installer\overload.iss
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{6E2B6E0A-6F1E-4B8A-9C55-0A7E10AD0001}
AppName=OverLoad
AppVersion={#MyAppVersion}
AppVerName=OverLoad {#MyAppVersion}
AppPublisher=OverLoad
AppPublisherURL=https://github.com/TOFazer/OverLoad
AppSupportURL=https://github.com/TOFazer/OverLoad/issues
AppUpdatesURL=https://github.com/TOFazer/OverLoad/releases
DefaultDirName={autopf}\OverLoad
DefaultGroupName=OverLoad
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=OverLoad-Setup-{#MyAppVersion}
SetupIconFile=..\assets\logo\overload.ico
UninstallDisplayIcon={app}\OverLoad.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\OverLoad\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OverLoad"; Filename: "{app}\OverLoad.exe"
Name: "{autodesktop}\OverLoad"; Filename: "{app}\OverLoad.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OverLoad.exe"; Description: "{cm:LaunchProgram,OverLoad}"; Flags: nowait postinstall skipifsilent

; Les paramètres, l'historique et la file sont dans %APPDATA%\OverLoad :
; ils ne sont jamais supprimés lors d'une mise à jour.
