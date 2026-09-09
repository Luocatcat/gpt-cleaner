param(
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $Root 'runtime'
$LocalConfig = Join-Path $Root 'config\local.json'
$TempRoot = Join-Path $env:TEMP ("gpt-cleaner-update-" + [guid]::NewGuid().ToString('N'))
$Zip = "$TempRoot.zip"

function Step($Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Die($Text) { Write-Host "ERROR: $Text" -ForegroundColor Red; exit 1 }

try {
    Step 'Downloading latest GPT Cleaner source'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://codeload.github.com/Luocatcat/gpt-cleaner/zip/refs/heads/main' -OutFile $Zip -TimeoutSec 180
    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $TempRoot -Force
    $Source = Get-ChildItem $TempRoot -Directory | Select-Object -First 1
    if (-not $Source) { Die 'Update archive contained no project directory.' }

    Step 'Updating code while preserving runtime and local GPU config'
    $preservedConfig = $null
    if (Test-Path $LocalConfig) { $preservedConfig = Get-Content $LocalConfig -Raw }

    $items = @(
        'README.md','AGENTS.md','WINDOWS_AGENT_PROMPT.md','.gitignore',
        'install.ps1','doctor.ps1','start.ps1','update.ps1','START_GPT_CLEANER.bat',
        'app','web','scripts','config'
    )
    foreach ($item in $items) {
        $src = Join-Path $Source.FullName $item
        $dst = Join-Path $Root $item
        if (-not (Test-Path $src)) { continue }
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item $src $dst -Recurse -Force
    }

    if ($preservedConfig) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LocalConfig) | Out-Null
        Set-Content -Path $LocalConfig -Value $preservedConfig -Encoding UTF8
    }

    Step 'Refreshing lightweight Python dependencies and compatibility patches'
    $Vpy = Join-Path $Runtime 'venv\Scripts\python.exe'
    if (Test-Path $Vpy) {
        & $Vpy -m pip install --timeout 180 --retries 8 -r (Join-Path $Root 'app\requirements.txt')
        if ($LASTEXITCODE -ne 0) { Die 'Dependency refresh failed.' }
    } else {
        Write-Host 'Runtime not installed yet; install.ps1 will create it later.' -ForegroundColor Yellow
    }

    $Node = Join-Path $Runtime 'ComfyUI\custom_nodes\ComfyUI-CCSR'
    $nodeInit = Join-Path $Node '__init__.py'
    if (Test-Path $nodeInit) {
        $initText = Get-Content $nodeInit -Raw
        $marker = '# GPT_CLEANER_SYSPATH_COMPAT'
        if ($initText -notmatch [regex]::Escape($marker)) {
            $compat = @"
$marker
import os as _gc_os, sys as _gc_sys
_gc_custom_nodes = _gc_os.path.dirname(_gc_os.path.dirname(_gc_os.path.abspath(__file__)))
if _gc_custom_nodes not in _gc_sys.path:
    _gc_sys.path.insert(0, _gc_custom_nodes)

"@
            Set-Content -Path $nodeInit -Value ($compat + $initText) -Encoding UTF8
        }
    }

    Write-Host "`nGPT Cleaner source updated. Existing models/runtime were preserved." -ForegroundColor Green
    if (-not $NoStart) {
        Step 'Launching updated GPT Cleaner'
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'start.ps1')
    }
} finally {
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue
    Remove-Item $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
