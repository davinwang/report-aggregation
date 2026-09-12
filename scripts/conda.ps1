# Resolves the bundled conda Python and puts its dirs on PATH so conda-provided
# DLLs (sqlite/openssl/etc.) resolve without activating the env.
# Search order: repo-root .conda, then backend/.conda, then system `python`.
# Dot-source from a sibling script:  . "$PSScriptRoot\conda.ps1"
function Enable-CondaPython {
    $root = Split-Path -Parent $PSScriptRoot
    foreach ($base in @("$root\.conda", "$root\backend\.conda")) {
        if (Test-Path "$base\python.exe") {
            $env:PATH = "$base;$base\Scripts;$base\Library\bin;" + $env:PATH
            return "$base\python.exe"
        }
    }
    return "python"
}
