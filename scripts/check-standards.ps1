param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Set-Location $ProjectRoot

$ArgsList = @("scripts/check-standards.py")
if ($DryRun) {
    $ArgsList += "--dry-run"
}

python @ArgsList
