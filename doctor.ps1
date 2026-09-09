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
    $gpuOut = @(& $nvidia.Source --query-gpu=name,memory.total --format=csv,noheader 2>$null)
    $gpuExit = $LASTEXITCODE
    $gpu = $gpuOut | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1
    if ($gpuExit -eq 0 -and $gpu) { Pass "NVIDIA: $gpu" } else { Fail 'nvidia-smi query failed' }
} else { Fail 'nvidia-smi missing' }

if (Test-Path $Vpy) { Pass 'isolated Python runtime exists' } else { Fail 'runtime/venv is missing' }
if (Test-Path $Comfy) { Pass 'ComfyUI exists' } else { Fail 'runtime/ComfyUI is missing' }
if (Test-Path $Node) { Pass 'ComfyUI-CCSR node exists' } else { Fail 'ComfyUI-CCSR node is missing' }
if (Test-Path $Model) {
    $sizeGB = [math]::Round((Get-Item $Model).Length / 1GB, 2)
    Pass "CCSR fp16 model exists ($sizeGB GB)"
} else { Fail 'CCSR fp16 model is missing' }
if (Test-Path $Config) { Pass 'VRAM-aware local config exists' } else { Warn 'config/local.json missing; default config will be used' }

$nodeInit = Join-Path $Node '__init__.py'
if (Test-Path $nodeInit) {
    $initText = Get-Content $nodeInit -Raw
    if ($initText -match 'GPT_CLEANER_SYSPATH_COMPAT') { Pass 'CCSR custom_nodes import compatibility patch is present' }
    else { Warn 'CCSR sys.path compatibility patch is missing; rerun install.ps1 if execution reports module import errors' }
}

if (Test-Path $Vpy) {
    $code = "import torch; print('torch='+torch.__version__); print('cuda='+str(torch.cuda.is_available())); print('gpu='+(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'))"
    $out = @(& $Vpy -c $code 2>&1)
    $exitCode = $LASTEXITCODE
    $out | ForEach-Object { Write-Host "       $_" }
    if ($exitCode -eq 0 -and ($out -join "`n") -match 'cuda=True') { Pass 'PyTorch CUDA is available' } else { Fail 'PyTorch cannot use CUDA' }

    $imports = @(& $Vpy -c "import flask,cv2,requests,PIL,numpy,huggingface_hub; print('app imports ok'); print('huggingface_hub='+huggingface_hub.__version__)" 2>&1)
    $importsExit = $LASTEXITCODE
    $imports | ForEach-Object { Write-Host "       $_" }
    if ($importsExit -eq 0) { Pass 'GPT Cleaner app dependencies import' } else { Fail 'GPT Cleaner app dependencies failed to import' }

    if (Test-Path $Node) {
        $parent = Split-Path -Parent $Node
        $escaped = $parent.Replace("\", "\\")
        $importCode = "import sys,importlib; sys.path.insert(0,r'$escaped'); importlib.import_module('ComfyUI-CCSR'); print('CCSR package import ok')"
        $nodeImport = @(& $Vpy -c $importCode 2>&1)
        $nodeImportExit = $LASTEXITCODE
        if ($nodeImportExit -eq 0) { Pass 'CCSR package import path works' }
        else {
            Warn 'Direct CCSR package import check failed outside ComfyUI; the runtime smoke test is authoritative.'
            $nodeImport | Select-Object -First 4 | ForEach-Object { Write-Host "       $_" }
        }
    }
}

if ($failed) {
    Write-Host "`nDoctor found critical problems." -ForegroundColor Red
    exit 1
}
Write-Host "`nDoctor passed." -ForegroundColor Green
exit 0
