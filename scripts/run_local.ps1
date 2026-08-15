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

# Windows installs the launcher as `python`; some setups only have `py`.
$python = "python"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $python = "py"
    } else {
        Write-Error "Python not found. Install Python 3.11+ from https://python.org and reopen this terminal."
    }
}

$version = & $python -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
Write-Host "==> Python $version" -ForegroundColor DarkGray

$needsInstall = $false
& $python -c "import fastapi" 2>$null
if ($LASTEXITCODE -ne 0) { $needsInstall = $true }
& $python -c "import sailwise_ref" 2>$null
if ($LASTEXITCODE -ne 0) { $needsInstall = $true }

if ($needsInstall) {
    Write-Host "==> Installing dependencies (first run only)" -ForegroundColor Cyan
    & $python -m pip install -e ./python -e ./backend
    if ($LASTEXITCODE -ne 0) { Write-Error "Dependency installation failed." }
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

& $python @uvicornArgs
