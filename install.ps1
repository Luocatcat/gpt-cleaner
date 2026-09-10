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
$Helpers = Join-Path $Root 'scripts\update_helpers.ps1'

function Step($Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Die($Text) { Write-Host "ERROR: $Text" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $Helpers)) { Die "Update helpers missing: $Helpers" }
. $Helpers
$UpdateManifest = Get-GptCleanerUpdateManifest -Root $Root

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path','Machine')
    $user = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = "$machine;$user"
}

function Find-Git {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    $candidate = Join-Path $env:ProgramFiles 'Git\cmd\git.exe'
    if (Test-Path $candidate) { return $candidate }
    return $null
}

function Test-RealPython($Exe, $WantedVersion) {
    try {
        $raw = @(& $Exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null)
        $exitCode = $LASTEXITCODE
        $version = (($raw | Out-String).Trim())
        return ($exitCode -eq 0 -and $version -eq $WantedVersion)
    } catch {
        return $false
    }
}

function Find-Python312 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py -and $py.Source) {
        try {
            $raw = @(& $py.Source -3.12 -c "import sys; print(sys.executable)" 2>$null)
            $exitCode = $LASTEXITCODE
            $path = (($raw | Out-String).Trim())
            if ($exitCode -eq 0 -and $path -and (Test-Path $path) -and (Test-RealPython $path '3.12')) { return $path }
        } catch {}
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:ProgramFiles 'Python312\python.exe')
    )
    foreach($p in $candidates) {
        if ((Test-Path $p) -and (Test-RealPython $p '3.12')) { return $p }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -and (Test-RealPython $python.Source '3.12')) { return $python.Source }
    return $null
}

function Download-RepoZip($Repo, $Branch, $Target, $Label) {
    $zip = Join-Path $env:TEMP ("gpt-cleaner-" + [guid]::NewGuid().ToString('N') + '.zip')
    $tmp = Join-Path $env:TEMP ("gpt-cleaner-" + [guid]::NewGuid().ToString('N'))
    $url = "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"
    try {
        Write-Host "Git clone unavailable/unstable, using codeload zip for $Label..." -ForegroundColor Yellow
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip -TimeoutSec 180
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $child = Get-ChildItem $tmp -Directory | Select-Object -First 1
        if (-not $child) { throw "Downloaded zip contained no directory" }
        if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
        Move-Item $child.FullName $Target
    } catch {
        Die "$Label download failed: $($_.Exception.Message)"
    } finally {
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Install-Repo($GitExe, $Repo, $Branch, $Target, $Label) {
    if (Test-Path $Target) { return }
    & $GitExe clone --depth 1 --branch $Branch "https://github.com/$Repo.git" $Target
    $cloneExit = $LASTEXITCODE
    if ($cloneExit -ne 0 -or -not (Test-Path $Target)) {
        Remove-Item $Target -Recurse -Force -ErrorAction SilentlyContinue
        Download-RepoZip $Repo $Branch $Target $Label
    }
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
$gpuOutput = @(& $nvidia.Source --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null)
$gpuExit = $LASTEXITCODE
$gpuLine = $gpuOutput | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1
if ($gpuExit -ne 0 -or -not $gpuLine) { Die 'NVIDIA GPU query failed.' }
$parts = $gpuLine -split ','
if ($parts.Count -lt 2) { Die "Unexpected nvidia-smi output: $gpuLine" }
$gpuName = $parts[0].Trim()
$vramMB = [int](($parts[1]).Trim())
Write-Host "GPU: $gpuName | VRAM: $vramMB MB" -ForegroundColor Green
if ($vramMB -lt 6000) { Die 'Less than 6 GB VRAM is not supported by the current preset.' }

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
& $Vpy -m pip install --timeout 180 --retries 8 torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { Die 'PyTorch CUDA installation failed.' }

Step 'Installing ComfyUI'
Install-Repo $git 'Comfy-Org/ComfyUI' 'master' $Comfy 'ComfyUI'
& $Vpy -m pip install --timeout 180 --retries 8 -r (Join-Path $Comfy 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Die 'ComfyUI requirements installation failed.' }

Step 'Installing CCSR ComfyUI node'
$CustomNodes = Join-Path $Comfy 'custom_nodes'
$CCSRNode = Join-Path $CustomNodes 'ComfyUI-CCSR'
New-Item -ItemType Directory -Force -Path $CustomNodes | Out-Null
Install-Repo $git 'kijai/ComfyUI-CCSR' 'main' $CCSRNode 'ComfyUI-CCSR'
$nodeReq = Join-Path $CCSRNode 'requirements.txt'
if (Test-Path $nodeReq) {
    & $Vpy -m pip install --timeout 180 --retries 8 -r $nodeReq
    if ($LASTEXITCODE -ne 0) { Die 'CCSR node requirements installation failed.' }
}

# Newer ComfyUI versions no longer guarantee custom_nodes is on sys.path.
# ComfyUI-CCSR dynamically imports modules through its package folder name, so register the parent explicitly.
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

Step 'Installing GPT Cleaner web runtime'
& $Vpy -m pip install --timeout 180 --retries 8 -r (Join-Path $Root 'app\requirements.txt')
if ($LASTEXITCODE -ne 0) { Die 'GPT Cleaner app requirements installation failed.' }

Step 'Downloading fp16 CCSR model'
$ModelDir = Join-Path $Comfy 'models\CCSR'
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
$ModelPath = Join-Path $ModelDir 'real-world_ccsr-fp16.safetensors'
if (-not (Test-Path $ModelPath)) {
    $env:HF_HUB_DISABLE_XET = '1'
    $download = "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Kijai/ccsr-safetensors', allow_patterns=['*real-world_ccsr-fp16.safetensors*'], local_dir=r'$ModelDir')"
    & $Vpy -c $download
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ModelPath)) {
        Write-Host 'Hugging Face direct download failed. Retrying through hf-mirror.com...' -ForegroundColor Yellow
        $env:HF_ENDPOINT = 'https://hf-mirror.com'
        & $Vpy -c $download
        Remove-Item Env:HF_ENDPOINT -ErrorAction SilentlyContinue
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ModelPath)) { Die 'CCSR model download failed on both direct and mirror routes.' }
}

Step 'Downloading semantic restoration models'
Install-GptCleanerSemanticModels -Python $Vpy -Comfy $Comfy -Manifest $UpdateManifest

Step 'Writing VRAM-aware local config'
$defaultConfig = Join-Path $ConfigDir 'default.json'
$localConfig = Join-Path $ConfigDir 'local.json'
$config = Get-Content $defaultConfig -Raw | ConvertFrom-Json
if ($vramMB -lt 7500) {
    $config.tile_size = 192; $config.tile_stride = 96
    $config.ccsr.tile_size = 192; $config.ccsr.tile_stride = 96
} elseif ($vramMB -lt 10500) {
    $config.tile_size = 256; $config.tile_stride = 128
    $config.ccsr.tile_size = 256; $config.ccsr.tile_stride = 128
} elseif ($vramMB -lt 15000) {
    $config.tile_size = 384; $config.tile_stride = 192
    $config.ccsr.tile_size = 384; $config.ccsr.tile_stride = 192
} else {
    $config.tile_size = 512; $config.tile_stride = 256
    $config.ccsr.tile_size = 512; $config.ccsr.tile_stride = 256
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
