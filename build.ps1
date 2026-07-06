# Build Switch Cheats Scraper into an .exe (+ optional installer).
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# Requires: Python 3.11-3.13 recommended (PyInstaller wheels), pip.
# Optional: Inno Setup 6 (iscc) on PATH for the installer step.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== 1/4  Installing build + runtime dependencies ==" -ForegroundColor Cyan
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m pip install pyinstaller

Write-Host "== 2/4  Downloading the bundled Chromium ==" -ForegroundColor Cyan
# Only Chromium is bundled (the Built-in default). Firefox is downloaded on demand
# at runtime into the per-user data folder, keeping the app small.
$env:PLAYWRIGHT_BROWSERS_PATH = "0"
py -m playwright install chromium

Write-Host "== 3/4  Building the .exe with PyInstaller ==" -ForegroundColor Cyan
py -m PyInstaller --noconfirm SwitchCheatsScraper.spec

$exe = "dist\SwitchCheatsScraper\SwitchCheatsScraper.exe"
if (Test-Path $exe) {
    Write-Host "Built: $exe" -ForegroundColor Green
} else {
    throw "Build failed: $exe not found"
}

# Playwright's PyInstaller hook bundles every browser present in the build env's
# package (incl. a previously-installed Firefox). Strip Firefox from dist so only
# Chromium ships — the app downloads Firefox on demand at runtime.
$fxGlob = "dist\SwitchCheatsScraper\_internal\playwright\driver\package\.local-browsers\firefox-*"
Get-ChildItem -Path $fxGlob -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Stripping bundled Firefox: $($_.Name)" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $_.FullName
}

Write-Host "== 4/5  Building the installer (if Inno Setup is available) ==" -ForegroundColor Cyan
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($p in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                     "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                     "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if ($iscc) {
    & $iscc installer.iss
    Write-Host "Installer: Output\SwitchCheatsScraper-Setup.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup (iscc) not found - skipped installer." -ForegroundColor Yellow
    Write-Host "Install it from https://jrsoftware.org/isdl.php, then run: iscc installer.iss"
}

Write-Host "== 5/5  Packing the portable ZIP ==" -ForegroundColor Cyan
if (-not (Test-Path Output)) { New-Item -ItemType Directory Output | Out-Null }
Compress-Archive -Path "dist\SwitchCheatsScraper" -DestinationPath "Output\SwitchCheatsScraper-portable.zip" -Force
Write-Host "Portable: Output\SwitchCheatsScraper-portable.zip" -ForegroundColor Green
