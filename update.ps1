param(
    [switch]$NoStart,
    [switch]$SkipDoctor
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $Root 'runtime'
$Comfy = Join-Path $Runtime 'ComfyUI'
$Vpy = Join-Path $Runtime 'venv\Scripts\python.exe'
$TempRoot = Join-Path $env:TEMP ("gpt-cleaner-update-" + [guid]::NewGuid().ToString('N'))
$Zip = "$TempRoot.zip"
$Helpers = Join-Path $Root 'scripts\update_helpers.ps1'

function Step($Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Die($Text) { Write-Host "ERROR: $Text" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $Helpers)) {
    Die 'V0.3 update helpers are missing. Run the existing updater once to fetch the latest source, then run update.ps1 again.'
}
. $Helpers

try {
    Step 'Downloading latest GPT Cleaner source'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://codeload.github.com/Luocatcat/gpt-cleaner/zip/refs/heads/main' -OutFile $Zip -TimeoutSec 180
    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $TempRoot -Force
    $Source = Get-ChildItem $TempRoot -Directory | Select-Object -First 1
    if (-not $Source) { Die 'Update archive contained no project directory.' }

    $sourceManifestPath = Join-Path $Source.FullName 'scripts\update_manifest.json'
    if (-not (Test-Path $sourceManifestPath)) { Die 'Latest source has no update manifest.' }
    $Manifest = Get-Content $sourceManifestPath -Raw | ConvertFrom-Json

    Step 'Stopping this installation runtime before in-place update'
    Stop-GptCleanerRuntime -Root $Root

    Step 'Updating source while preserving runtime and local config bytes'
    Copy-GptCleanerSource -Source $Source.FullName -Target $Root -Manifest $Manifest

    if (-not (Test-Path $Vpy)) {
        Die 'Existing runtime Python is missing. Run install.ps1 instead of deleting or rebuilding runtime manually.'
    }
    if (-not (Test-Path $Comfy)) {
        Die 'Existing runtime ComfyUI is missing. Run install.ps1 instead of deleting or rebuilding runtime manually.'
    }

    Step 'Refreshing lightweight GPT Cleaner dependencies'
    & $Vpy -m pip install --timeout 180 --retries 8 -r (Join-Path $Root 'app\requirements.txt')
    if ($LASTEXITCODE -ne 0) { Die 'GPT Cleaner dependency refresh failed.' }

    if (-not (Test-GptCleanerComfySupirCore -Comfy $Comfy)) {
        Step 'Updating dedicated ComfyUI core for native SUPIR support'
        Update-GptCleanerComfyCore -Comfy $Comfy -Manifest $Manifest
        & $Vpy -m pip install --timeout 180 --retries 8 -r (Join-Path $Comfy 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { Die 'ComfyUI dependency refresh failed.' }
        if (-not (Test-GptCleanerComfySupirCore -Comfy $Comfy)) {
            Die 'ComfyUI update completed but SUPIR Core nodes are still missing.'
        }
    } else {
        Write-Host 'ComfyUI Core SUPIR support already present.' -ForegroundColor Green
    }

    Step 'Preserving legacy CCSR fallback compatibility'
    Set-GptCleanerCcsrCompat -Comfy $Comfy

    Step 'Downloading only missing semantic restoration models'
    Install-GptCleanerSemanticModels -Python $Vpy -Comfy $Comfy -Manifest $Manifest

    if (-not $SkipDoctor) {
        Step 'Running V0.3 doctor'
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'doctor.ps1')
        if ($LASTEXITCODE -ne 0) { Die 'Doctor found a critical base-runtime problem.' }
    }

    Write-Host "`nGPT Cleaner V0.3 source and semantic models updated. Existing runtime, CCSR model, logs, and local config were preserved." -ForegroundColor Green
    if (-not $NoStart) {
        Step 'Launching updated GPT Cleaner'
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'start.ps1')
    }
} finally {
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue
    Remove-Item $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
