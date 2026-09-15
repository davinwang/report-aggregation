# Rebuilds and restarts the Docker Compose stack (backend + frontend).
# Usage: ./scripts/deploy.ps1 [-Log <path>]
param([string]$Log = "")
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$deploy = Join-Path $root "deploy"

Write-Host "== docker compose build ==" -ForegroundColor Cyan
Set-Location $deploy
if ($Log) {
    docker compose build backend frontend *> $Log
    Select-String -Path $Log -Pattern "naming to|ERROR|error during" | ForEach-Object { $_.Line }
} else {
    docker compose build backend frontend
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[deploy] build FAILED (see log)" -ForegroundColor Red
    exit 1
}

Write-Host "== docker compose up ==" -ForegroundColor Cyan
docker compose up -d --force-recreate
Start-Sleep -Seconds 12
docker ps
