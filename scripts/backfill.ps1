# Backfills a feed for a universe. Examples:
#   ./scripts/backfill.ps1 -Feed price_history -Universe hs300
#   ./scripts/backfill.ps1 -Feed research_reports -Universe hs300
#   ./scripts/backfill.ps1 -Feed financials_em -Universe hs300
param(
    [Parameter(Mandatory = $true)][string]$Feed,
    [string]$Universe = "hs300",
    [string]$Start = "",
    [string]$End = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot\conda.ps1"
$py = Enable-CondaPython
Push-Location "$root\backend"
try {
    $cli = @("-m", "app.ingestion.pipeline", "--feed", $Feed, "--universe", $Universe)
    if ($Start) { $cli += @("--start", $Start) }
    if ($End) { $cli += @("--end", $End) }
    & $py @cli
} finally {
    Pop-Location
}
