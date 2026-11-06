; One-file per-user installer for the existing PyInstaller onedir bundle.
; Build with:
;   ISCC.exe /DAppVersion=1.3.1 installer\FlutterWay.iss

#ifndef AppVersion
  #define AppVersion "1.3.1"
#endif

#define AppName "FlutterWay"
#define AppPublisher "FlutterWay"
#define BundleDir "..\dist\FlutterWayNative"

[Setup]
AppId={{A11870DF-1A28-4A40-95B0-0B72C4FD0AB7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/AboALhasanx/flutterway
AppSupportURL=https://github.com/AboALhasanx/flutterway/issues
AppUpdatesURL=https://github.com/AboALhasanx/flutterway/releases
DefaultDirName={localappdata}\Programs\FlutterWay
DefaultGroupName=FlutterWay
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\FlutterWayNative.exe
OutputDir=..\dist\installer
OutputBaseFilename=FlutterWay-Setup-v{#AppVersion}-windows-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
Uninstallable=yes
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=FlutterWay Setup
VersionInfoProductName=FlutterWay
VersionInfoProductVersion={#AppVersion}
VersionInfoCopyright=Copyright (C) 2026 AboALhasanx

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\FlutterWay"; Filename: "{app}\FlutterWayNative.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\FlutterWay"; Filename: "{app}\FlutterWayNative.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FlutterWayNative.exe"; Description: "Launch FlutterWay"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Deliberately do not remove %LOCALAPPDATA%\FlutterWay: it contains user SDKs,
; projects, logs, reports, and recovery data.
