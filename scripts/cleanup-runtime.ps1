param(
    [switch]$DryRun,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$ArgsList = @("scripts/cleanup_runtime.py")
if ($DryRun) {
    $ArgsList += "--dry-run"
}
if ($Json) {
    $ArgsList += "--json"
}

python @ArgsList
