; Inno Setup script for Switch Cheats Scraper & Downloader
; Build the app first (pyinstaller SwitchCheatsScraper.spec), then compile this
; with Inno Setup 6:  iscc installer.iss  ->  Output\SwitchCheatsScraper-Setup.exe

#define AppName "Switch Cheats Scraper & Downloader"
#define AppExe "SwitchCheatsScraper.exe"
#define AppVersion "1.0"
#define AppPublisher "DevCatSKZ"
#define AppURL "https://github.com/DevCatSKZ/Switch-Cheats-Scraper-Downloader"

[Setup]
AppId={{9F3C7A21-4B6E-4E2A-9E5B-SWITCHCHEATS01}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
; The app stores its data NEXT TO the .exe (portable). Install per-user by
; default so that folder is writable ({autopf} = %LOCALAPPDATA%\Programs for a
; non-admin install). The user may still choose another folder in the wizard.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=Output
OutputBaseFilename=SwitchCheatsScraper-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=app.ico
WizardImageFile=wizard_large.bmp
WizardSmallImageFile=wizard_small.bmp
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole PyInstaller one-folder output.
Source: "dist\SwitchCheatsScraper\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Ship the app icon into {app} root so shortcuts reference a real .ico directly
; (PyInstaller 6 puts bundled data in _internal\, so the exe's own copy is not
; next to it). Referencing an explicit .ico avoids the generic-shortcut-icon
; issue where Windows can't resolve the embedded exe icon from its cache.
Source: "app.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
{ On uninstall, ask whether to also remove the user's data (DB, downloads,
  settings, login profile). This keeps the uninstaller friendly and safe. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    if MsgBox('Auch alle heruntergeladenen Cheats, die Datenbank und Einstellungen entfernen?'#13#10#13#10
              + 'Ja = alles restlos entfernen.'#13#10
              + 'Nein = deine Daten (cheats.db, cheatsdownload, Login) bleiben erhalten.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{app}\cheatsdownload'), True, True, True);
      DelTree(ExpandConstant('{app}\coversdownload'), True, True, True);
      DelTree(ExpandConstant('{app}\browser_profile'), True, True, True);
      DeleteFile(ExpandConstant('{app}\cheats.db'));
      DeleteFile(ExpandConstant('{app}\cheats.db-wal'));
      DeleteFile(ExpandConstant('{app}\cheats.db-shm'));
      DeleteFile(ExpandConstant('{app}\settings.json'));
      DeleteFile(ExpandConstant('{app}\scraper.log'));
      DeleteFile(ExpandConstant('{app}\.downloaded_cache.json'));
    end;
  end;
end;
