# Build SD Time: standalone app (PyInstaller) + Windows installer (Inno Setup).
#   .\build.ps1              -> dist\SD Time\SD Time.exe  and  dist\SD_Time_Setup_<version>.exe
#   .\build.ps1 -NoInstaller -> only the app folder
# Needs: .venv with requirements + pyinstaller; Inno Setup 6 (winget install JRSoftware.InnoSetup).
param([switch]$NoInstaller)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

$version = (& $py -c "import sd_time; print(sd_time.__version__)").Trim()
Write-Host "== SD Time $version" -ForegroundColor Green

# Windows file properties (Details tab of the .exe)
New-Item -ItemType Directory -Force build | Out-Null
$v = ($version.Split(".") + @("0", "0", "0"))[0..3] -join ", "
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v), prodvers=($v)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'SanddogFX'),
      StringStruct('FileDescription', 'SD Time - time tracker'),
      StringStruct('FileVersion', '$version'),
      StringStruct('ProductName', 'SD Time'),
      StringStruct('ProductVersion', '$version'),
      StringStruct('OriginalFilename', 'SD Time.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Encoding utf8 build\version_info.txt

Write-Host "== PyInstaller" -ForegroundColor Green
& $py -m PyInstaller --noconfirm --clean --log-level WARN `
    --distpath dist --workpath build\pyinstaller packaging\sd_time.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }

Write-Host "== Self-test of the built app" -ForegroundColor Green
$report = Join-Path $env:TEMP "sd_time_selftest.txt"
Remove-Item $report -ErrorAction SilentlyContinue
$p = Start-Process -FilePath "dist\SD Time\SD Time.exe" -ArgumentList "--selftest=$report" -PassThru -Wait
$text = Get-Content $report -Raw -ErrorAction SilentlyContinue
if ($p.ExitCode -ne 0 -or -not $text -or -not $text.StartsWith("OK")) { throw "Self-test failed:`n$text" }
Write-Host $text

if (-not $NoInstaller) {
    Write-Host "== Inno Setup" -ForegroundColor Green
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
              "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }
    & $iscc /Q "/DAppVersion=$version" packaging\installer.iss
    if ($LASTEXITCODE) { throw "Inno Setup failed" }
    Write-Host "Installer: dist\SD_Time_Setup_$version.exe" -ForegroundColor Green
}
