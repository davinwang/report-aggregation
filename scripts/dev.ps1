# Starts backend (using the bundled .conda Python when present) and frontend for local dev.
# Usage: ./scripts/dev.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot\conda.ps1"
$py = Enable-CondaPython

Write-Host "== Stock Research Platform dev ==" -ForegroundColor Cyan

$ver = (& $py -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null)
if ($LASTEXITCODE -eq 0 -and $ver -match '^\d+\.\d+$') {
    Write-Host "[backend] python: $py ($ver)" -ForegroundColor Green
    Write-Host "[backend] starting uvicorn on :8000 ..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; & '$py' -m uvicorn app.main:app --reload --port 8000"
} else {
    Write-Host "[backend] real Python not found - skipping. Install Python 3.11+ (or a .conda env) then re-run." -ForegroundColor Yellow
    Write-Host "          (frontend will still start; API calls will fail until backend runs)" -ForegroundColor Yellow
}

Write-Host "[frontend] starting vite on :5173 ..." -ForegroundColor Green
Push-Location "$root\frontend"
if (-not (Test-Path "node_modules")) { npm install }
npm run dev
Pop-Location
