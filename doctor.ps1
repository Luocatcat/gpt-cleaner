$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vpy = Join-Path $Root 'runtime\venv\Scripts\python.exe'
$Comfy = Join-Path $Root 'runtime\ComfyUI'
$ConfigDir = Join-Path $Root 'config'
$CcsrNode = Join-Path $Comfy 'custom_nodes\ComfyUI-CCSR'
$CcsrModel = Join-Path $Comfy 'models\CCSR\real-world_ccsr-fp16.safetensors'
$SupirNodeFile = Join-Path $Comfy 'comfy_extras\nodes_model_patch.py'
$SupirModel = Join-Path $Comfy 'models\model_patches\SUPIR-v0Q_fp16.safetensors'
$SdxlModel = Join-Path $Comfy 'models\checkpoints\juggernautXL_v9Rdphoto2Lightning.safetensors'
$failed = $false
$partial = $false

function Pass($m) { Write-Host "[PASS] $m" -ForegroundColor Green }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; $script:failed = $true }
function Partial($m) { Write-Host "[PARTIAL] $m" -ForegroundColor Yellow; $script:partial = $true }
function Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Test-ModelFile($Path) {
    return ((Test-Path $Path) -and (Get-Item $Path).Length -gt 100MB)
}

Write-Host 'GPT Cleaner V0.3 Doctor' -ForegroundColor Cyan

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
if (Test-Path $Comfy) { Pass 'dedicated ComfyUI exists' } else { Fail 'runtime/ComfyUI is missing' }

$supirCoreReady = $false
if (Test-Path $SupirNodeFile) {
    $supirNodeText = Get-Content $SupirNodeFile -Raw
    $supirCoreReady = ($supirNodeText -match 'class SUPIRApply' -and $supirNodeText -match 'class ModelPatchLoader')
}
if ($supirCoreReady) { Pass 'ComfyUI Core SUPIRApply and ModelPatchLoader exist' }
else { Partial 'ComfyUI Core SUPIR nodes are missing; semantic mode must fall back' }

$supirPatchReady = Test-ModelFile $SupirModel
$sdxlReady = Test-ModelFile $SdxlModel
if ($supirPatchReady) {
    $sizeGB = [math]::Round((Get-Item $SupirModel).Length / 1GB, 2)
    Pass "SUPIR fp16 model patch exists ($sizeGB GB)"
} else { Partial 'SUPIR-v0Q_fp16.safetensors is missing or incomplete' }
if ($sdxlReady) {
    $sizeGB = [math]::Round((Get-Item $SdxlModel).Length / 1GB, 2)
    Pass "SDXL restoration checkpoint exists ($sizeGB GB)"
} else { Partial 'Juggernaut XL Lightning checkpoint is missing or incomplete' }

$ccsrReady = ((Test-Path $CcsrNode) -and (Test-ModelFile $CcsrModel))
if ($ccsrReady) { Pass 'legacy CCSR fallback node and model exist' }
elseif ($supirCoreReady -and $supirPatchReady -and $sdxlReady) { Warn 'legacy CCSR fallback is incomplete; SUPIR remains available' }
else { Partial 'legacy CCSR fallback is incomplete; safe cleanup is the remaining fallback' }

$nodeInit = Join-Path $CcsrNode '__init__.py'
if (Test-Path $nodeInit) {
    $initText = Get-Content $nodeInit -Raw
    if ($initText -match 'GPT_CLEANER_SYSPATH_COMPAT') { Pass 'CCSR import compatibility patch is present' }
    else { Warn 'CCSR import compatibility patch is missing; rerun update.ps1' }
}

if (Test-Path $Vpy) {
    $torchCode = "import torch; print('torch='+torch.__version__); print('cuda='+str(torch.cuda.is_available())); print('gpu='+(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'))"
    $torchOut = @(& $Vpy -c $torchCode 2>&1)
    $torchExit = $LASTEXITCODE
    $torchOut | ForEach-Object { Write-Host "       $_" }
    if ($torchExit -eq 0 -and ($torchOut -join "`n") -match 'cuda=True') { Pass 'PyTorch CUDA is available' }
    else { Fail 'PyTorch cannot use CUDA' }

    $imports = @(& $Vpy -c "import flask,cv2,requests,PIL,numpy,huggingface_hub; print('app imports ok'); print('huggingface_hub='+huggingface_hub.__version__)" 2>&1)
    $importsExit = $LASTEXITCODE
    $imports | ForEach-Object { Write-Host "       $_" }
    if ($importsExit -eq 0) { Pass 'GPT Cleaner app dependencies import' }
    else { Fail 'GPT Cleaner app dependencies failed to import' }

    $escapedRoot = $Root.Replace("\", "\\")
    $escapedConfig = $ConfigDir.Replace("\", "\\")
    $configCode = "import sys; from pathlib import Path; sys.path.insert(0,r'$escapedRoot'); from app.configuration import load_config; c=load_config(Path(r'$escapedConfig')); assert c['default_mode']=='semantic'; assert c['semantic']['model_patch']; assert c['ccsr']['model']; print('merged V0.3 config ok')"
    $configOut = @(& $Vpy -c $configCode 2>&1)
    $configExit = $LASTEXITCODE
    $configOut | ForEach-Object { Write-Host "       $_" }
    if ($configExit -eq 0) { Pass 'old local config merges with V0.3 defaults' }
    else { Fail 'V0.3 merged config check failed' }

    if (Test-Path $CcsrNode) {
        $parent = Split-Path -Parent $CcsrNode
        $escapedParent = $parent.Replace("\", "\\")
        $importCode = "import sys,importlib; sys.path.insert(0,r'$escapedParent'); importlib.import_module('ComfyUI-CCSR'); print('CCSR package import ok')"
        $nodeImport = @(& $Vpy -c $importCode 2>&1)
        if ($LASTEXITCODE -eq 0) { Pass 'CCSR package import path works' }
        else {
            Warn 'Direct CCSR package import failed outside ComfyUI; --ccsr smoke test is authoritative'
            $nodeImport | Select-Object -First 4 | ForEach-Object { Write-Host "       $_" }
        }
    }
}

try {
    $objectInfo = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/object_info' -TimeoutSec 3
    $names = @($objectInfo.PSObject.Properties.Name)
    if ($names -contains 'SUPIRApply' -and $names -contains 'ModelPatchLoader') {
        Pass 'running ComfyUI exposes native SUPIR nodes'
    } else {
        Partial 'running ComfyUI does not expose native SUPIR nodes; restart after update'
    }
} catch {
    Warn 'ComfyUI is not running; static files were checked and semantic smoke test remains authoritative'
}

if ($failed) {
    Write-Host "`nDoctor failed: critical base runtime problems found." -ForegroundColor Red
    exit 1
}
if ($partial) {
    Write-Host "`nDoctor partial: base product can run, but full SUPIR semantic readiness is incomplete." -ForegroundColor Yellow
    exit 0
}
Write-Host "`nDoctor passed: full SUPIR semantic route is installed." -ForegroundColor Green
exit 0
