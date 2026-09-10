$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vpy = Join-Path $Root 'runtime\venv\Scripts\python.exe'
$Comfy = Join-Path $Root 'runtime\ComfyUI'
$SUPIRNode = Join-Path $Comfy 'custom_nodes\ComfyUI-SUPIR'
$CCSRNode = Join-Path $Comfy 'custom_nodes\ComfyUI-CCSR'
$SUPIRModel = Join-Path $Comfy 'models\checkpoints\SUPIR-v0Q_fp16.safetensors'
$SDXLModel = Join-Path $Comfy 'models\checkpoints\sd_xl_base_1.0.safetensors'
$CCSRModel = Join-Path $Comfy 'models\CCSR\real-world_ccsr-fp16.safetensors'
$Config = Join-Path $Root 'config\local.json'
$failed = $false

function Pass($m) { Write-Host "[PASS] $m" -ForegroundColor Green }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; $script:failed = $true }
function Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }

Write-Host "GPT Cleaner V0.3 Doctor" -ForegroundColor Cyan

$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $nvidia) {
    $nv = 'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe'
    if (Test-Path $nv) { $nvidia = Get-Item $nv }
}
if ($nvidia) {
    $gpuOutput = @(& $nvidia.Source --query-gpu=name,memory.total --format=csv,noheader 2>$null)
    $gpuExit = $LASTEXITCODE
    $gpu = $gpuOutput | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1
    if ($gpuExit -eq 0 -and $gpu) { Pass "NVIDIA: $gpu" } else { Fail 'nvidia-smi query failed' }
} else { Fail 'nvidia-smi missing' }

if (Test-Path $Vpy) { Pass 'isolated Python runtime exists' } else { Fail 'runtime/venv is missing' }
if (Test-Path $Comfy) { Pass 'ComfyUI exists' } else { Fail 'runtime/ComfyUI is missing' }
if (Test-Path $SUPIRNode) { Pass 'ComfyUI-SUPIR semantic node exists' } else { Fail 'ComfyUI-SUPIR node is missing; run update.ps1' }

if (Test-Path $SUPIRModel) {
    $sizeGB = [math]::Round((Get-Item $SUPIRModel).Length / 1GB, 2)
    if ($sizeGB -gt 2.0) { Pass "SUPIR-v0Q fp16 model exists ($sizeGB GB)" } else { Fail "SUPIR model looks incomplete ($sizeGB GB)" }
} else { Fail 'SUPIR-v0Q_fp16.safetensors is missing' }

if (Test-Path $SDXLModel) {
    $sizeGB = [math]::Round((Get-Item $SDXLModel).Length / 1GB, 2)
    if ($sizeGB -gt 5.0) { Pass "SDXL base checkpoint exists ($sizeGB GB)" } else { Fail "SDXL checkpoint looks incomplete ($sizeGB GB)" }
} else { Fail 'sd_xl_base_1.0.safetensors is missing' }

if (Test-Path $CCSRNode) { Warn 'legacy CCSR fallback is still installed (kept for A/B only)' }
if (Test-Path $CCSRModel) {
    $sizeGB = [math]::Round((Get-Item $CCSRModel).Length / 1GB, 2)
    Warn "legacy CCSR model preserved ($sizeGB GB)"
}

if (Test-Path $Config) {
    Pass 'V0.3 local config exists'
    try {
        $cfg = Get-Content $Config -Raw | ConvertFrom-Json
        if ($cfg.default_mode -eq 'semantic') { Pass 'default engine is semantic' } else { Warn "default_mode is $($cfg.default_mode), expected semantic" }
        if ($cfg.supir.fp8_unet -eq $true) { Pass 'SUPIR fp8 UNet memory saver enabled' } else { Warn 'SUPIR fp8_unet is disabled; 8GB cards may OOM' }
        Pass "SUPIR tile=$($cfg.supir.sampler_tile_size), stride=$($cfg.supir.sampler_tile_stride)"
    } catch { Fail 'config/local.json could not be parsed' }
} else { Warn 'config/local.json missing; defaults will be used' }

if (Test-Path $Vpy) {
    $code = "import torch; print('torch='+torch.__version__); print('cuda='+str(torch.cuda.is_available())); print('gpu='+(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'))"
    $out = & $Vpy -c $code 2>&1
    $out | ForEach-Object { Write-Host "       $_" }
    if ($LASTEXITCODE -eq 0 -and ($out -join "`n") -match 'cuda=True') { Pass 'PyTorch CUDA is available' } else { Fail 'PyTorch cannot use CUDA' }

    & $Vpy -c "import flask,cv2,requests,PIL,numpy; from app.restoration import controlled_degrade,multiscale_fuse; print('app imports ok')" 2>$null
    if ($LASTEXITCODE -eq 0) { Pass 'GPT Cleaner V0.3 app dependencies import' } else { Fail 'GPT Cleaner app dependencies failed to import' }
}

if ($failed) {
    Write-Host "`nDoctor found critical problems." -ForegroundColor Red
    exit 1
}
Write-Host "`nDoctor passed. Start GPT Cleaner and verify /api/health reports supir=true." -ForegroundColor Green
exit 0
