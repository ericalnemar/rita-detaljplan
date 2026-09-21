# Länkar rita_detaljplan in i en QGIS 4-profil så att pluginet laddas direkt från källkoden.
# Användning: powershell -File tools\install_dev.ps1 [-Profile default]
param([string]$Profile = "default")

$repo = Split-Path -Parent $PSScriptRoot
$plugins = Join-Path $env:APPDATA "QGIS\QGIS4\profiles\$Profile\python\plugins"
$link = Join-Path $plugins "rita_detaljplan"

New-Item -ItemType Directory -Force $plugins | Out-Null
if (Test-Path $link) {
    Write-Host "Finns redan: $link"
    exit 0
}
New-Item -ItemType Junction -Path $link -Target (Join-Path $repo "rita_detaljplan") | Out-Null
Write-Host "Skapade länk $link -> $repo\rita_detaljplan"
Write-Host "Starta om QGIS och aktivera 'Rita Detaljplan' under Tillägg."
