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

function Stop-LocalPort($Port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $conns) {
            if ($conn.OwningProcess) {
                Write-Host "Stopping existing process on port $Port (PID $($conn.OwningProcess))..." -ForegroundColor Yellow
                Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {}
}

function Download-RepoZip($Repo, $Branch, $Target, $Label) {
    if (Test-Path $Target) { return }
    $zipPath = Join-Path $env:TEMP ("gpt-cleaner-node-" + [guid]::NewGuid().ToString('N') + '.zip')
    $tmpPath = Join-Path $env:TEMP ("gpt-cleaner-node-" + [guid]::NewGuid().ToString('N'))
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/$Repo/zip/refs/heads/$Branch" -OutFile $zipPath -TimeoutSec 240
        New-Item -ItemType Directory -Force -Path $tmpPath | Out-Null
        Expand-Archive -Path $zipPath -DestinationPath $tmpPath -Force
        $child = Get-ChildItem $tmpPath -Directory | Select-Object -First 1
        if (-not $child) { throw "$Label archive contained no directory" }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
        Move-Item $child.FullName $Target
    } catch {
        Die "$Label download failed: $($_.Exception.Message)"
    } finally {
        Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item $tmpPath -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Download-HFFile($Python, $RepoId, $Pattern, $TargetDir, $ExpectedFile, $Label) {
    if (Test-Path $ExpectedFile) {
        Write-Host "$Label already exists." -ForegroundColor Green
        return
    }
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    $env:HF_HUB_DISABLE_XET = '1'
    $pyCode = "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$RepoId', allow_patterns=['$Pattern'], local_dir=r'$TargetDir')"
    Write-Host "Downloading $Label..." -ForegroundColor Cyan
    & $Python -c $pyCode
    $directExit = $LASTEXITCODE
    if ($directExit -ne 0 -or -not (Test-Path $ExpectedFile)) {
        Write-Host 'Direct Hugging Face route failed. Retrying through hf-mirror.com...' -ForegroundColor Yellow
        $env:HF_ENDPOINT = 'https://hf-mirror.com'
        & $Python -c $pyCode
        $mirrorExit = $LASTEXITCODE
        Remove-Item Env:HF_ENDPOINT -ErrorAction SilentlyContinue
        if ($mirrorExit -ne 0 -or -not (Test-Path $ExpectedFile)) {
            Die "$Label download failed on both direct and mirror routes."
        }
    }
}

try {
    Step 'Stopping current GPT Cleaner services'
    Stop-LocalPort 8787
    Stop-LocalPort 8188
    Start-Sleep -Seconds 2

    Step 'Downloading latest GPT Cleaner source'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://codeload.github.com/Luocatcat/gpt-cleaner/zip/refs/heads/main' -OutFile $Zip -TimeoutSec 240
    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $TempRoot -Force
    $Source = Get-ChildItem $TempRoot -Directory | Select-Object -First 1
    if (-not $Source) { Die 'Update archive contained no project directory.' }

    Step 'Preserving runtime and local preferences'
    $oldConfig = $null
    if (Test-Path $LocalConfig) {
        try { $oldConfig = Get-Content $LocalConfig -Raw | ConvertFrom-Json } catch {}
    }

    Step 'Updating program code'
    $items = @(
        'README.md','AGENTS.md','WINDOWS_AGENT_PROMPT.md','.gitignore',
        'install.ps1','doctor.ps1','start.ps1','update.ps1','START_GPT_CLEANER.bat','UPDATE_GPT_CLEANER.bat',
        'app','web','scripts','config'
    )
    foreach ($item in $items) {
        $src = Join-Path $Source.FullName $item
        $dst = Join-Path $Root $item
        if (-not (Test-Path $src)) { continue }
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item $src $dst -Recurse -Force
    }

    $Vpy = Join-Path $Runtime 'venv\Scripts\python.exe'
    $Comfy = Join-Path $Runtime 'ComfyUI'
    if (-not (Test-Path $Vpy) -or -not (Test-Path $Comfy)) {
        Write-Host 'Existing runtime is incomplete. Falling back to full installer.' -ForegroundColor Yellow
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'install.ps1') -NoStart
        if ($LASTEXITCODE -ne 0) { Die 'Full installer fallback failed.' }
    } else {
        Step 'Refreshing lightweight app dependencies'
        & $Vpy -m pip install --timeout 180 --retries 8 -r (Join-Path $Root 'app\requirements.txt')
        if ($LASTEXITCODE -ne 0) { Die 'Dependency refresh failed.' }

        Step 'Installing SUPIR semantic node without touching the existing CCSR runtime'
        $SUPIRNode = Join-Path $Comfy 'custom_nodes\ComfyUI-SUPIR'
        Download-RepoZip 'kijai/ComfyUI-SUPIR' 'main' $SUPIRNode 'ComfyUI-SUPIR'
        $supirReq = Join-Path $SUPIRNode 'requirements.txt'
        if (Test-Path $supirReq) {
            & $Vpy -m pip install --timeout 180 --retries 8 -r $supirReq
            if ($LASTEXITCODE -ne 0) { Die 'SUPIR node dependency install failed.' }
        }

        # Preserve the compatibility fix learned from the first Windows install.
        $CCSRNode = Join-Path $Comfy 'custom_nodes\ComfyUI-CCSR'
        $nodeInit = Join-Path $CCSRNode '__init__.py'
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

        Step 'Downloading V0.3 semantic models; existing models are never deleted'
        $CheckpointDir = Join-Path $Comfy 'models\checkpoints'
        $SUPIRModel = Join-Path $CheckpointDir 'SUPIR-v0Q_fp16.safetensors'
        $SDXLModel = Join-Path $CheckpointDir 'sd_xl_base_1.0.safetensors'
        Download-HFFile $Vpy 'Kijai/SUPIR_pruned' 'SUPIR-v0Q_fp16.safetensors' $CheckpointDir $SUPIRModel 'SUPIR-v0Q fp16 (about 2.7 GB)'
        Download-HFFile $Vpy 'stabilityai/stable-diffusion-xl-base-1.0' 'sd_xl_base_1.0.safetensors' $CheckpointDir $SDXLModel 'SDXL base checkpoint (about 6.9 GB)'
    }

    Step 'Migrating local config to the V0.3 schema'
    $defaultConfig = Join-Path $Root 'config\default.json'
    $newConfig = Get-Content $defaultConfig -Raw | ConvertFrom-Json

    if ($oldConfig) {
        if ($oldConfig.comfy_url) { $newConfig.comfy_url = $oldConfig.comfy_url }
        if ($oldConfig.web_host) { $newConfig.web_host = $oldConfig.web_host }
        if ($oldConfig.web_port) { $newConfig.web_port = $oldConfig.web_port }
        # Preserve user-edited prompts/settings if this is already a V0.3 config.
        if ($oldConfig.supir) {
            foreach ($name in @('positive_prompt','negative_prompt','sampler','seed','color_fix')) {
                if ($null -ne $oldConfig.supir.$name) { $newConfig.supir.$name = $oldConfig.supir.$name }
            }
        }
    }

    $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidia) {
        $nv = 'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe'
        if (Test-Path $nv) { $nvidia = Get-Item $nv }
    }
    $vramMB = 8192
    if ($nvidia) {
        $gpuOutput = @(& $nvidia.Source --query-gpu=memory.total --format=csv,noheader,nounits 2>$null)
        if ($LASTEXITCODE -eq 0) {
            $line = $gpuOutput | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1
            if ($line) { $vramMB = [int]$line.Trim() }
        }
    }

    if ($vramMB -lt 7500) {
        $newConfig.supir.sampler_tile_size = 384; $newConfig.supir.sampler_tile_stride = 192; $newConfig.supir.vae_tile_pixels = 384
        $newConfig.ccsr.tile_size = 192; $newConfig.ccsr.tile_stride = 96
    } elseif ($vramMB -lt 10500) {
        $newConfig.supir.sampler_tile_size = 512; $newConfig.supir.sampler_tile_stride = 256; $newConfig.supir.vae_tile_pixels = 512
        $newConfig.ccsr.tile_size = 256; $newConfig.ccsr.tile_stride = 128
    } elseif ($vramMB -lt 15000) {
        $newConfig.supir.sampler_tile_size = 640; $newConfig.supir.sampler_tile_stride = 320; $newConfig.supir.vae_tile_pixels = 640
        $newConfig.ccsr.tile_size = 384; $newConfig.ccsr.tile_stride = 192
    } else {
        $newConfig.supir.sampler_tile_size = 768; $newConfig.supir.sampler_tile_stride = 384; $newConfig.supir.vae_tile_pixels = 768
        $newConfig.ccsr.tile_size = 512; $newConfig.ccsr.tile_stride = 256
    }
    $newConfig.default_mode = 'semantic'
    $newConfig | ConvertTo-Json -Depth 30 | Set-Content -Path $LocalConfig -Encoding UTF8

    Step 'Running V0.3 doctor'
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'doctor.ps1')
    if ($LASTEXITCODE -ne 0) { Die 'Doctor found a critical problem.' }

    Write-Host "`nGPT Cleaner upgraded to V0.3. Runtime, old CCSR model and logs were preserved." -ForegroundColor Green
    if (-not $NoStart) {
        Step 'Launching updated GPT Cleaner'
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'start.ps1')
    }
} finally {
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue
    Remove-Item $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
