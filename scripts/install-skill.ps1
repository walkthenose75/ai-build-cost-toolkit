[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $HOME '.copilot\skills\aic-tracker'),
    [switch]$Force
)

# Single canonical skill source, shared with `python -m ai_build_cost install-skill`.
$source = Join-Path $PSScriptRoot '..\ai_build_cost\skill\SKILL.md'
$source = (Resolve-Path $source).Path

if (Test-Path $Destination) {
    if (-not $Force) {
        throw "Skill already exists at $Destination. Re-run with -Force to replace it."
    }
}

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
Copy-Item -Path $source -Destination (Join-Path $Destination 'SKILL.md') -Force
Write-Output "Installed or updated aic-tracker skill at $Destination"
