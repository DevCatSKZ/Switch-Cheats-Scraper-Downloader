; Inno Setup script for Switch Cheats Scraper & Downloader
; Build the app first (pyinstaller SwitchCheatsScraper.spec), then compile this
; with Inno Setup 6:  iscc installer.iss  ->  Output\SwitchCheatsScraper-Setup.exe

#define AppName "Switch Cheats Scraper & Downloader"
#define AppExe "SwitchCheatsScraper.exe"
#define AppVersion "1.3"
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
VersionInfoVersion=1.3.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
; Per-user install (no admin, no UAC) so the app can update itself SILENTLY.
; {autopf} resolves to %LOCALAPPDATA%\Programs when PrivilegesRequired=lowest
; (the standard per-user location, like VS Code's user installer).
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
; Always show the "Select Destination Location" page so the user can browse to
; (or create) any folder — never auto-skip it based on a previous install.
DisableDirPage=no
; Install PER USER (lowest privileges) — no admin, NO UAC prompt. The app folder
; is then writable, so updates install SILENTLY and the app restarts itself (see
; _apply_installer_update in gui.py). The app stores its data next to the .exe.
; PrivilegesRequiredOverridesAllowed still lets an admin pick an all-users folder.
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
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
; Japanese ships with Inno Setup 6 under Languages\ (version-matched to your
; install, so there is no separate .isl file to keep in sync).
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
; Desktop shortcut ON by default — it points at {app}\app.ico (not the exe's
; embedded icon), so it reliably shows the current app icon. This spares users
; from creating a manual shortcut (which uses the exe icon and can show a generic
; icon until Windows refreshes its cache).
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

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
; Refresh the shell icon cache so the shortcut shows the NEW app.ico immediately.
; Windows caches shortcut icons by path; since app.ico keeps the same path and
; only its content changed, the old icon would otherwise linger until a reboot.
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden runasoriginaluser skipifdoesntexist
; Relaunch after install — including after a silent self-update (no skipifsilent),
; and as the original (non-elevated) user so the app doesn't run with admin rights.
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall runasoriginaluser

[UninstallDelete]
; default_lang.txt is written at install time (not tracked by [Files]), so
; remove it explicitly to leave a clean {app} folder behind.
Type: files; Name: "{app}\default_lang.txt"

[Code]
{ Tell the shell that icons/associations changed so Explorer refreshes the
  shortcut icon right away (otherwise the cached old app.ico can linger). }
procedure SHChangeNotify(wEventId, uFlags: Integer; dwItem1, dwItem2: Cardinal);
  external 'SHChangeNotify@shell32.dll stdcall';

var
  LangPage: TInputOptionWizardPage;

{ Program language code for the option index on the custom page. The app reads
  default_lang.txt (written below) on first run to pick its start language. }
function LangCodeByIndex(I: Integer): String;
begin
  case I of
    1: Result := 'de';
    2: Result := 'es';
    3: Result := 'fr';
    4: Result := 'it';
    5: Result := 'ja';
  else
    Result := 'en';
  end;
end;

{ Pre-select the program language from the installer's own wizard language, so
  choosing German setup -> the program also starts in German. }
function DefaultLangIndex: Integer;
var
  L: String;
begin
  L := ActiveLanguage();
  if L = 'german' then Result := 1
  else if L = 'spanish' then Result := 2
  else if L = 'french' then Result := 3
  else if L = 'italian' then Result := 4
  else if L = 'japanese' then Result := 5
  else Result := 0;
end;

procedure InitializeWizard;
begin
  { A dedicated page (after "Select Destination Location") lets the user choose
    the program language explicitly (all 6), pre-set from the wizard language. }
  LangPage := CreateInputOptionPage(wpSelectDir,
    'Program language / Programmsprache',
    'Which language should Switch Cheats Scraper start in?',
    'Pick the language for the program interface. You can change it any time later inside the app.',
    True, False);
  LangPage.Add('English');
  LangPage.Add('Deutsch (German)');
  LangPage.Add('Espanol (Spanish)');
  LangPage.Add('Francais (French)');
  LangPage.Add('Italiano (Italian)');
  LangPage.Add('Nihongo (Japanese)');
  LangPage.SelectedValueIndex := DefaultLangIndex;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    SHChangeNotify($08000000, $0000, 0, 0);   { SHCNE_ASSOCCHANGED, SHCNF_IDLIST }
    { Persist the chosen program language next to the exe. _installer_default_
      language() in gui.py reads this on the first run (before settings.json). }
    SaveStringToFile(ExpandConstant('{app}\default_lang.txt'),
                     LangCodeByIndex(LangPage.SelectedValueIndex), False);
  end;
end;

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
