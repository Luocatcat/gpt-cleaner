$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vpy = Join-Path $Root 'runtime\venv\Scripts\python.exe'
$Comfy = Join-Path $Root 'runtime\ComfyUI'
$Logs = Join-Path $Root 'runtime\logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Wait-Url($Url, $Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $true }
        } catch {}
        Start-Sleep -Seconds 1
    }
    return $false
}

if (-not (Test-Path $Vpy)) {
    Write-Host 'GPT Cleaner is not installed yet. Running install.ps1 first...' -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'install.ps1') -NoStart
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

$comfyReady = Wait-Url 'http://127.0.0.1:8188/system_stats' 2
if (-not $comfyReady -and (Test-Path (Join-Path $Comfy 'main.py'))) {
    Write-Host 'Starting optional ComfyUI AI-refine engine...' -ForegroundColor Cyan
    $args = @('main.py','--listen','127.0.0.1','--port','8188','--lowvram','--disable-auto-launch')
    Start-Process -FilePath $Vpy -ArgumentList $args -WorkingDirectory $Comfy -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs 'comfy.out.log') `
        -RedirectStandardError (Join-Path $Logs 'comfy.err.log')
    $comfyReady = Wait-Url 'http://127.0.0.1:8188/system_stats' 120
}

if ($comfyReady) {
    Write-Host 'AI refine ready on localhost:8188' -ForegroundColor Green
} else {
    Write-Host 'AI refine is not ready. GPT Cleaner will still open in SAFE cleanup mode.' -ForegroundColor Yellow
    Write-Host 'If needed, inspect runtime/logs/comfy.err.log and run doctor.ps1.' -ForegroundColor Yellow
}

$webReady = Wait-Url 'http://127.0.0.1:8787/api/health' 2
if (-not $webReady) {
    Write-Host 'Starting GPT Cleaner web UI...' -ForegroundColor Cyan
    $args = @('-m','waitress','--listen=0.0.0.0:8787','app.server:app')
    Start-Process -FilePath $Vpy -ArgumentList $args -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs 'web.out.log') `
        -RedirectStandardError (Join-Path $Logs 'web.err.log')
    if (-not (Wait-Url 'http://127.0.0.1:8787/api/health' 30)) {
        Write-Host 'GPT Cleaner web app did not become ready. Check runtime/logs/web.err.log' -ForegroundColor Red
        exit 1
    }
}

Write-Host 'GPT Cleaner ready: http://127.0.0.1:8787' -ForegroundColor Green
Start-Process 'http://127.0.0.1:8787'
