<#
.SYNOPSIS
    Run SailWise locally on Windows: API + web UI on http://127.0.0.1:8000

.EXAMPLE
    .\scripts\run_local.ps1
    Real forecasts (Open-Meteo), falling back to demo data if unreachable.

.EXAMPLE
    .\scripts\run_local.ps1 -Demo
    Synthetic data only, fully offline.

.EXAMPLE
    .\scripts\run_local.ps1 -Port 9000 -Reload

.NOTES
    If PowerShell refuses to run this file ("script is not digitally signed"), either:
        powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1
    or allow local scripts once, for your user only:
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#>

[CmdletBinding()]
param(
    [switch] $Demo,
    [switch] $Live,
    [switch] $Reload,
    [int]    $Port = 8000,
    [string] $BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$provider = "auto"
if ($Demo) { $provider = "fixture" }
if ($Live) { $provider = "open-meteo" }

# Finding a usable Python on Windows is not just "does the command exist".
#
# Windows ships a stub at %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe that is not
# Python at all: it prints "Python non è stato trovato / Python was not found" and
# offers to open the Microsoft Store. `Get-Command python` finds it happily, so the
# only reliable test is to run it and check that real Python answers back.
function Find-Python {
    $candidates = @(
        @{ Exe = "py";      Prefix = @("-3") },
        @{ Exe = "python3"; Prefix = @() },
        @{ Exe = "python";  Prefix = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }

        $probe = & $candidate.Exe @($candidate.Prefix + @(
            "-c", "import sys; print('SAILWISE_PY %d.%d' % sys.version_info[:2])"
        )) 2>&1
        if ($LASTEXITCODE -ne 0) { continue }

        if ("$probe" -match 'SAILWISE_PY (\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 11) {
                return @{
                    Exe     = $candidate.Exe
                    Prefix  = $candidate.Prefix
                    Version = "$major.$minor"
                }
            }
            Write-Host "    skipping $($candidate.Exe): Python $major.$minor is too old (need 3.11+)" -ForegroundColor DarkYellow
        }
    }
    return $null
}

function Invoke-Python {
    param([string[]] $Arguments)
    & $script:py.Exe @($script:py.Prefix + $Arguments)
}

$script:py = Find-Python
if (-not $script:py) {
    Write-Host ""
    Write-Host "  Python 3.11 or newer was not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "  If you just saw 'Python non e' stato trovato' / 'Python was not found',"
    Write-Host "  that message came from a Windows placeholder, not from Python: Windows"
    Write-Host "  ships a stub that only opens the Microsoft Store."
    Write-Host ""
    Write-Host "  Install it, then open a NEW terminal:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "      winget install Python.Python.3.12"
    Write-Host ""
    Write-Host "  or download it from https://www.python.org/downloads/windows/ and tick"
    Write-Host "  'Add python.exe to PATH' during setup."
    Write-Host ""
    Write-Host "  If 'python' still opens the Microsoft Store afterwards, turn off the"
    Write-Host "  aliases in Settings > Apps > Advanced app settings > App execution"
    Write-Host "  aliases (both 'python.exe' and 'python3.exe')."
    Write-Host ""
    exit 1
}

Write-Host "==> Python $($script:py.Version) via '$($script:py.Exe)'" -ForegroundColor DarkGray

$needsInstall = $false
Invoke-Python @("-c", "import fastapi") 2>$null
if ($LASTEXITCODE -ne 0) { $needsInstall = $true }
Invoke-Python @("-c", "import sailwise_ref") 2>$null
if ($LASTEXITCODE -ne 0) { $needsInstall = $true }

if ($needsInstall) {
    Write-Host "==> Installing dependencies (first run only)" -ForegroundColor Cyan
    Invoke-Python @("-m", "pip", "install", "-e", "./python", "-e", "./backend")
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  Dependency installation failed. If pip reported a permissions error," -ForegroundColor Red
        Write-Host "  try a virtual environment:" -ForegroundColor Red
        Write-Host ""
        Write-Host "      $($script:py.Exe) -m venv .venv"
        Write-Host "      .\.venv\Scripts\Activate.ps1"
        Write-Host "      .\scripts\run_local.ps1"
        Write-Host ""
        exit 1
    }
}

Write-Host ""
Write-Host "  SailWise" -ForegroundColor Cyan
Write-Host "      http://${BindHost}:${Port}" -ForegroundColor White
Write-Host ""
Write-Host "      weather provider : $provider"
Write-Host "      spot dataset     : $(if ($env:SAILWISE_SPOTS_DATASET) { $env:SAILWISE_SPOTS_DATASET } else { 'italian_lakes' })"
Write-Host ""
Write-Host "  On the first run the spot coordinates are resolved in the background"
Write-Host "  through Nominatim, one per second, in priority order. Dervio and Colico"
Write-Host "  are available within seconds; the rest fill in over the next minute."
Write-Host "  The result is cached to disk, so this happens once ever."
Write-Host ""
Write-Host "  SailWise is decision support, not a safety clearance. Always check" -ForegroundColor Yellow
Write-Host "  official forecasts and notices before departure." -ForegroundColor Yellow
Write-Host ""

$env:SAILWISE_WEATHER_PROVIDER = $provider

Set-Location (Join-Path $root "backend")
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", $Port)
if ($Reload) { $uvicornArgs += "--reload" }

Invoke-Python $uvicornArgs
