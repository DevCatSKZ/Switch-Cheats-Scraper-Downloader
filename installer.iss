; Inno Setup script for Switch Cheats Scraper & Downloader
; Build the app first (pyinstaller SwitchCheatsScraper.spec), then compile this
; with Inno Setup 6:  iscc installer.iss  ->  Output\SwitchCheatsScraper-Setup.exe

#define AppName "Switch Cheats Scraper & Downloader"
#define AppExe "SwitchCheatsScraper.exe"
#define AppVersion "1.1"
#define AppPublisher "Mr.Skittelz aka KatzenCode"
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
VersionInfoVersion=1.1.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
; Default into 32-bit Program Files, as requested. {commonpf32} is always
; C:\Program Files (x86). Writing there needs admin rights (UAC prompt).
DefaultDirName={commonpf32}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
; Always show the "Select Destination Location" page so the user can browse to
; (or create) any folder — never auto-skip it based on a previous install.
DisableDirPage=no
; The app prefers to store its data NEXT TO the .exe (portable); when that folder
; is read-only — as C:\Program Files (x86) is for a normal user — it transparently
; falls back to %LOCALAPPDATA%\SwitchCheatsScraper (see _data_dir() in gui.py), so
; a Program Files install works fine. Admin rights are required to install there;
; the user may still pick a writable folder of their own in the wizard.
PrivilegesRequired=admin
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
; Relaunch after install — including after a silent self-update (no skipifsilent),
; and as the original (non-elevated) user so the app doesn't run with admin rights.
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall runasoriginaluser

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
      { Data next to the .exe (portable / writable install). }
      DelTree(ExpandConstant('{app}\cheatsdownload'), True, True, True);
      DelTree(ExpandConstant('{app}\coversdownload'), True, True, True);
      DelTree(ExpandConstant('{app}\browser_profile'), True, True, True);
      DeleteFile(ExpandConstant('{app}\cheats.db'));
      DeleteFile(ExpandConstant('{app}\cheats.db-wal'));
      DeleteFile(ExpandConstant('{app}\cheats.db-shm'));
      DeleteFile(ExpandConstant('{app}\settings.json'));
      DeleteFile(ExpandConstant('{app}\update_state.json'));
      DeleteFile(ExpandConstant('{app}\scraper.log'));
      DeleteFile(ExpandConstant('{app}\.downloaded_cache.json'));
      { ...and the LOCALAPPDATA fallback used when the app folder is read-only
        e.g. a Program Files install - see _data_dir in gui.py. }
      DelTree(ExpandConstant('{localappdata}\SwitchCheatsScraper'), True, True, True);
    end;
  end;
end;
