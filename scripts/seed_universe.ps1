# Seeds the default universe (沪深300 constituents) and the security master.
# Usage: ./scripts/seed_universe.ps1 [-Universe hs300|zz500|hs300+zz500|all]
param([string]$Universe = "hs300")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot\conda.ps1"
$py = Enable-CondaPython
Push-Location "$root\backend"
try {
    & $py -m app.ingestion.pipeline --feed security_master
    & $py -m app.ingestion.pipeline --feed industry_boards
    & $py -m app.ingestion.pipeline --resolve-universe $Universe
} finally {
    Pop-Location
}
