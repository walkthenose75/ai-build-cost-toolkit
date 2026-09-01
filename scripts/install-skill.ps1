[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $HOME '.copilot\skills\aic-tracker'),
    [switch]$Force
)

$source = Join-Path $PSScriptRoot '..\skill\aic-tracker'
$source = (Resolve-Path $source).Path

if (Test-Path $Destination) {
    if (-not $Force) {
        throw "Skill already exists at $Destination. Re-run with -Force to replace it."
    }
}

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $Destination -Recurse -Force
Write-Output "Installed or updated aic-tracker skill at $Destination"
