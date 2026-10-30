; Inno Setup script for Pyre Windows installer.
; Compile from nornir-pyre/packaging/windows after build-freeze.ps1.

; Version must be passed by build-installer.ps1 as /DMyAppVersion=...
; (reads nornir-pyre/pyproject.toml). Do not hardcode a release version here.
#ifndef MyAppVersion
  #error "Define MyAppVersion (run packaging/windows/build-installer.ps1)"
#endif

#define MyAppName "Pyre"
#define MyAppPublisher "Nornir"
#define MyAppURL "https://nornir.github.io/"
#define MyAppExeName "pyre.exe"

#ifexist "dist\pyre\pyre.exe"
#else
  #error "Frozen bundle not found. Run build-freeze.ps1 first (expected dist\pyre\pyre.exe)."
#endif

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppPublisher}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Nornir\Pyre
DefaultGroupName=Nornir\Pyre
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=Pyre-{#MyAppVersion}-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\pyre\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
