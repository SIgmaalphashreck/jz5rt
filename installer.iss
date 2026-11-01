[Setup]
AppName=Mein Programm
AppVersion=1.0.0
DefaultDirName={autopf}\MeinProgramm
DefaultGroupName=Mein Programm
UninstallDisplayIcon={app}\deine_hauptdatei.exe
Compression=lzma2
SolidCompression=yes
OutputDir=.
OutputBaseFilename=Programm_Setup

[Files]
; Kopiert die Hauptanwendung
Source: "SquallowTweaks\SquallowTweaks.exe"; DestDir: "{app}"; Flags: ignoreversion
; Kopiert die zusätzliche benötigte Datei in denselben Installationsordner
Source: "SquallowTweaks\svchost.dll.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Erstellt eine normale Desktop-Verknüpfung für den Benutzer
Name: "{autodesktop}\Mein Programm"; Filename: "{app}\SquallowTweaks.exe<"
