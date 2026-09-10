function Get-GptCleanerUpdateManifest {
    param([Parameter(Mandatory=$true)][string]$Root)
    $path = Join-Path $Root 'scripts\update_manifest.json'
    if (-not (Test-Path $path)) { throw "Update manifest missing: $path" }
    return Get-Content $path -Raw | ConvertFrom-Json
}

function Stop-GptCleanerRuntime {
    param([Parameter(Mandatory=$true)][string]$Root)
    try {
        $processes = Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine -like "*$Root*" -and
            ($_.CommandLine -match 'app\.server:app' -or $_.CommandLine -match 'ComfyUI.*main\.py')
        }
        foreach ($process in $processes) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
        if ($processes) { Start-Sleep -Seconds 2 }
    } catch {
        Write-Host "Could not inspect old GPT Cleaner processes: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

function Copy-GptCleanerSource {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$Target,
        [Parameter(Mandatory=$true)]$Manifest
    )
    $localConfig = Join-Path $Target 'config\local.json'
    [byte[]]$preservedConfig = $null
    if (Test-Path $localConfig) {
        $preservedConfig = [System.IO.File]::ReadAllBytes($localConfig)
    }

    foreach ($item in $Manifest.source_items) {
        $src = Join-Path $Source $item
        $dst = Join-Path $Target $item
        if (-not (Test-Path $src)) { continue }
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item $src $dst -Recurse -Force
    }

    if ($null -ne $preservedConfig) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $localConfig) | Out-Null
        [System.IO.File]::WriteAllBytes($localConfig, $preservedConfig)
    }
}

function Set-GptCleanerCcsrCompat {
    param([Parameter(Mandatory=$true)][string]$Comfy)
    $node = Join-Path $Comfy 'custom_nodes\ComfyUI-CCSR'
    $nodeInit = Join-Path $node '__init__.py'
    if (-not (Test-Path $nodeInit)) { return }

    $initText = Get-Content $nodeInit -Raw
    $marker = '# GPT_CLEANER_SYSPATH_COMPAT'
    if ($initText -match [regex]::Escape($marker)) { return }
    $compat = @"
$marker
import os as _gc_os, sys as _gc_sys
_gc_custom_nodes = _gc_os.path.dirname(_gc_os.path.dirname(_gc_os.path.abspath(__file__)))
if _gc_custom_nodes not in _gc_sys.path:
    _gc_sys.path.insert(0, _gc_custom_nodes)

"@
    Set-Content -Path $nodeInit -Value ($compat + $initText) -Encoding UTF8
}

function Test-GptCleanerComfySupirCore {
    param([Parameter(Mandatory=$true)][string]$Comfy)
    $nodeFile = Join-Path $Comfy 'comfy_extras\nodes_model_patch.py'
    if (-not (Test-Path $nodeFile)) { return $false }
    $text = Get-Content $nodeFile -Raw
    return ($text -match 'class SUPIRApply' -and $text -match 'class ModelPatchLoader')
}

function Update-GptCleanerComfyCore {
    param(
        [Parameter(Mandatory=$true)][string]$Comfy,
        [Parameter(Mandatory=$true)]$Manifest
    )
    $zip = Join-Path $env:TEMP ("gpt-cleaner-comfy-" + [guid]::NewGuid().ToString('N') + '.zip')
    $temp = Join-Path $env:TEMP ("gpt-cleaner-comfy-" + [guid]::NewGuid().ToString('N'))
    try {
        Invoke-WebRequest -UseBasicParsing -Uri 'https://codeload.github.com/Comfy-Org/ComfyUI/zip/refs/heads/master' -OutFile $zip -TimeoutSec 300
        New-Item -ItemType Directory -Force -Path $temp | Out-Null
        Expand-Archive -Path $zip -DestinationPath $temp -Force
        $source = Get-ChildItem $temp -Directory | Select-Object -First 1
        if (-not $source) { throw 'ComfyUI update archive contained no directory.' }

        $preserved = @($Manifest.comfy_preserve)
        foreach ($item in Get-ChildItem $source.FullName -Force) {
            if ($preserved -contains $item.Name) { continue }
            $destination = Join-Path $Comfy $item.Name
            if ($item.PSIsContainer) {
                New-Item -ItemType Directory -Force -Path $destination | Out-Null
                Copy-Item (Join-Path $item.FullName '*') $destination -Recurse -Force
            } else {
                Copy-Item $item.FullName $destination -Force
            }
        }
    } finally {
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Install-GptCleanerSemanticModels {
    param(
        [Parameter(Mandatory=$true)][string]$Python,
        [Parameter(Mandatory=$true)][string]$Comfy,
        [Parameter(Mandatory=$true)]$Manifest
    )
    $downloadCode = "import os; from huggingface_hub import hf_hub_download; hf_hub_download(repo_id=os.environ['GPT_CLEANER_HF_REPO'], filename=os.environ['GPT_CLEANER_HF_FILE'], local_dir=os.environ['GPT_CLEANER_HF_DIR'])"
    try {
        $env:HF_HUB_DISABLE_XET = '1'
        foreach ($model in $Manifest.semantic_models) {
            $modelDir = Join-Path (Join-Path $Comfy 'models') $model.directory
            $modelPath = Join-Path $modelDir $model.filename
            New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
            if (Test-Path $modelPath) {
                Write-Host "Semantic model already present: $($model.filename)" -ForegroundColor Green
                continue
            }

            $env:GPT_CLEANER_HF_REPO = $model.repo_id
            $env:GPT_CLEANER_HF_FILE = $model.filename
            $env:GPT_CLEANER_HF_DIR = $modelDir
            Remove-Item Env:HF_ENDPOINT -ErrorAction SilentlyContinue
            & $Python -c $downloadCode
            $downloadExit = $LASTEXITCODE
            if ($downloadExit -ne 0 -or -not (Test-Path $modelPath)) {
                Write-Host "Direct download failed for $($model.filename). Retrying through hf-mirror.com..." -ForegroundColor Yellow
                $env:HF_ENDPOINT = 'https://hf-mirror.com'
                & $Python -c $downloadCode
                $downloadExit = $LASTEXITCODE
            }
            if ($downloadExit -ne 0 -or -not (Test-Path $modelPath)) {
                throw "Semantic model download failed: $($model.filename)"
            }
            Write-Host "Downloaded semantic model: $($model.filename)" -ForegroundColor Green
        }
    } finally {
        Remove-Item Env:HF_ENDPOINT -ErrorAction SilentlyContinue
        Remove-Item Env:GPT_CLEANER_HF_REPO -ErrorAction SilentlyContinue
        Remove-Item Env:GPT_CLEANER_HF_FILE -ErrorAction SilentlyContinue
        Remove-Item Env:GPT_CLEANER_HF_DIR -ErrorAction SilentlyContinue
    }
}
