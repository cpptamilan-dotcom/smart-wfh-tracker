; Inno Setup script -> Output\SmartWFHTracker_Setup.exe (per-user, no admin rights needed)
[Setup]
AppName=Smart WFH & Leave Tracker
AppVersion=1.0.0
DefaultDirName={autopf}\SmartWFHTracker
DefaultGroupName=Smart WFH Tracker
PrivilegesRequired=lowest
OutputBaseFilename=SmartWFHTracker_Setup
OutputDir=Output
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\SmartWFHTracker.exe

[Files]
Source: "dist\SmartWFHTracker.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Smart WFH Tracker"; Filename: "{app}\SmartWFHTracker.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "SmartWFHTracker"; ValueData: """{app}\SmartWFHTracker.exe"" --minimized"; \
  Flags: uninsdeletevalue

[Run]
Filename: "{app}\SmartWFHTracker.exe"; Description: "Launch Smart WFH Tracker"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM SmartWFHTracker.exe"; Flags: runhidden skipifdoesntexist; RunOnceId: "StopApp"
; Attendance data in %LOCALAPPDATA%\SmartWFHTracker is intentionally kept on uninstall.
