param(
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $Root 'runtime'
$Comfy = Join-Path $Runtime 'ComfyUI'
$Venv = Join-Path $Runtime 'venv'
$ConfigDir = Join-Path $Root 'config'

function Step($Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Die($Text) { Write-Host "ERROR: $Text" -ForegroundColor Red; exit 1 }

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path','Machine')
    $user = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = "$machine;$user"
}

function Find-Git {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidate = Join-Path $env:ProgramFiles 'Git\cmd\git.exe'
    if (Test-Path $candidate) { return $candidate }
    return $null
}

function Find-Python312 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $path = & $py.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $path -and (Test-Path $path.Trim())) { return $path.Trim() }
        } catch {}
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:ProgramFiles 'Python312\python.exe')
    )
    foreach($p in $candidates) { if (Test-Path $p) { return $p } }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $v = & $python.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($v.Trim() -eq '3.12') { return $python.Source }
    }
    return $null
}

Set-Location $Root
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

Step 'Checking NVIDIA GPU'
$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $nvidia) {
    $nv = 'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe'
    if (Test-Path $nv) { $nvidia = Get-Item $nv }
}
if (-not $nvidia) { Die 'nvidia-smi not found. Install/update the NVIDIA driver first.' }
$gpuLine = & $nvidia.Source --query-gpu=name,memory.total --format=csv,noheader,nounits | Select-Object -First 1
if ($LASTEXITCODE -ne 0 -or -not $gpuLine) { Die 'NVIDIA GPU query failed.' }
$parts = $gpuLine -split ','
$gpuName = $parts[0].Trim()
$vramMB = [int](($parts[1]).Trim())
Write-Host "GPU: $gpuName | VRAM: $vramMB MB" -ForegroundColor Green
if ($vramMB -lt 6000) { Die 'Less than 6 GB VRAM is not supported by the V0 preset.' }

Step 'Checking Git'
$git = Find-Git
if (-not $git) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Die 'Git is missing and winget is unavailable.' }
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Die 'Git installation failed.' }
    Refresh-Path
    $git = Find-Git
}
if (-not $git) { Die 'Git still not found after installation.' }
Write-Host "Git: $git" -ForegroundColor Green

Step 'Checking Python 3.12'
$python = Find-Python312
if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Die 'Python 3.12 is missing and winget is unavailable.' }
    winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Die 'Python 3.12 installation failed.' }
    Refresh-Path
    $python = Find-Python312
}
if (-not $python) { Die 'Python 3.12 still not found after installation.' }
Write-Host "Python: $python" -ForegroundColor Green

Step 'Creating isolated Python runtime'
if (-not (Test-Path (Join-Path $Venv 'Scripts\python.exe'))) {
    & $python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Die 'venv creation failed.' }
}
$Vpy = Join-Path $Venv 'Scripts\python.exe'
& $Vpy -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { Die 'pip bootstrap failed.' }

Step 'Installing PyTorch CUDA 12.8 runtime'
& $Vpy -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { Die 'PyTorch CUDA installation failed.' }

Step 'Installing ComfyUI'
if (-not (Test-Path $Comfy)) {
    & $git clone --depth 1 https://github.com/Comfy-Org/ComfyUI.git $Comfy
    if ($LASTEXITCODE -ne 0) { Die 'ComfyUI clone failed.' }
}
& $Vpy -m pip install -r (Join-Path $Comfy 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Die 'ComfyUI requirements installation failed.' }

Step 'Installing CCSR ComfyUI node'
$CustomNodes = Join-Path $Comfy 'custom_nodes'
$CCSRNode = Join-Path $CustomNodes 'ComfyUI-CCSR'
New-Item -ItemType Directory -Force -Path $CustomNodes | Out-Null
if (-not (Test-Path $CCSRNode)) {
    & $git clone --depth 1 https://github.com/kijai/ComfyUI-CCSR.git $CCSRNode
    if ($LASTEXITCODE -ne 0) { Die 'ComfyUI-CCSR clone failed.' }
}
$nodeReq = Join-Path $CCSRNode 'requirements.txt'
if (Test-Path $nodeReq) {
    & $Vpy -m pip install -r $nodeReq
    if ($LASTEXITCODE -ne 0) { Die 'CCSR node requirements installation failed.' }
}

Step 'Installing GPT Cleaner web runtime'
& $Vpy -m pip install -r (Join-Path $Root 'app\requirements.txt')
if ($LASTEXITCODE -ne 0) { Die 'GPT Cleaner app requirements installation failed.' }

Step 'Downloading fp16 CCSR model'
$ModelDir = Join-Path $Comfy 'models\CCSR'
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
$ModelPath = Join-Path $ModelDir 'real-world_ccsr-fp16.safetensors'
if (-not (Test-Path $ModelPath)) {
    $env:HF_HUB_DISABLE_XET = '1'
    $download = "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Kijai/ccsr-safetensors', allow_patterns=['*real-world_ccsr-fp16.safetensors*'], local_dir=r'$ModelDir')"
    & $Vpy -c $download
    if ($LASTEXITCODE -ne 0) { Die 'CCSR model download failed.' }
}

Step 'Writing VRAM-aware local config'
$defaultConfig = Join-Path $ConfigDir 'default.json'
$localConfig = Join-Path $ConfigDir 'local.json'
$config = Get-Content $defaultConfig -Raw | ConvertFrom-Json
if ($vramMB -lt 7500) {
    $config.tile_size = 192; $config.tile_stride = 96
} elseif ($vramMB -lt 10500) {
    $config.tile_size = 256; $config.tile_stride = 128
} elseif ($vramMB -lt 15000) {
    $config.tile_size = 384; $config.tile_stride = 192
} else {
    $config.tile_size = 512; $config.tile_stride = 256
}
$config | ConvertTo-Json -Depth 20 | Set-Content -Path $localConfig -Encoding UTF8
Write-Host "Preset: tile=$($config.tile_size), stride=$($config.tile_stride)" -ForegroundColor Green

Step 'Running doctor'
& powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'doctor.ps1')
if ($LASTEXITCODE -ne 0) { Die 'Doctor found a critical problem. Review messages above.' }

Write-Host "`nGPT Cleaner installation complete." -ForegroundColor Green
if (-not $NoStart) {
    Step 'Launching GPT Cleaner'
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'start.ps1')
}
