$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vpy = Join-Path $Root 'runtime\venv\Scripts\python.exe'
$Comfy = Join-Path $Root 'runtime\ComfyUI'
$Node = Join-Path $Comfy 'custom_nodes\ComfyUI-CCSR'
$Model = Join-Path $Comfy 'models\CCSR\real-world_ccsr-fp16.safetensors'
$Config = Join-Path $Root 'config\local.json'
$failed = $false

function Pass($m) { Write-Host "[PASS] $m" -ForegroundColor Green }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; $script:failed = $true }
function Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }

Write-Host "GPT Cleaner Doctor" -ForegroundColor Cyan

$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $nvidia) {
    $nv = 'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe'
    if (Test-Path $nv) { $nvidia = Get-Item $nv }
}
if ($nvidia) {
    $gpu = & $nvidia.Source --query-gpu=name,memory.total --format=csv,noheader | Select-Object -First 1
    if ($LASTEXITCODE -eq 0) { Pass "NVIDIA: $gpu" } else { Fail 'nvidia-smi query failed' }
} else { Fail 'nvidia-smi missing' }

if (Test-Path $Vpy) { Pass 'isolated Python runtime exists' } else { Fail 'runtime/venv is missing' }
if (Test-Path $Comfy) { Pass 'ComfyUI exists' } else { Fail 'runtime/ComfyUI is missing' }
if (Test-Path $Node) { Pass 'ComfyUI-CCSR node exists' } else { Fail 'ComfyUI-CCSR node is missing' }
if (Test-Path $Model) {
    $sizeGB = [math]::Round((Get-Item $Model).Length / 1GB, 2)
    Pass "CCSR fp16 model exists ($sizeGB GB)"
} else { Fail 'CCSR fp16 model is missing' }
if (Test-Path $Config) { Pass 'VRAM-aware local config exists' } else { Warn 'config/local.json missing; default config will be used' }

if (Test-Path $Vpy) {
    $code = "import torch; print('torch='+torch.__version__); print('cuda='+str(torch.cuda.is_available())); print('gpu='+(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'))"
    $out = & $Vpy -c $code 2>&1
    $out | ForEach-Object { Write-Host "       $_" }
    if ($LASTEXITCODE -eq 0 -and ($out -join "`n") -match 'cuda=True') { Pass 'PyTorch CUDA is available' } else { Fail 'PyTorch cannot use CUDA' }

    & $Vpy -c "import flask,cv2,requests,PIL,numpy; print('app imports ok')" 2>$null
    if ($LASTEXITCODE -eq 0) { Pass 'GPT Cleaner app dependencies import' } else { Fail 'GPT Cleaner app dependencies failed to import' }
}

if ($failed) {
    Write-Host "`nDoctor found critical problems." -ForegroundColor Red
    exit 1
}
Write-Host "`nDoctor passed." -ForegroundColor Green
exit 0
