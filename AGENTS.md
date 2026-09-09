# GPT Cleaner · Agent Installation Contract

This repository is designed to be installed by an agent on a Windows NVIDIA machine with minimal user involvement.

## Mission

Install and launch GPT Cleaner so the user can open a minimal web page, upload a GPT-generated image, clean high-frequency AI artifacts, compare before/after, and save the result.

Primary target machine:

- Windows 64-bit
- Ryzen 9 7900X
- 32 GB RAM
- NVIDIA RTX 5060 8 GB

## Non-negotiable rules

1. Do not upload user images to any external AI service.
2. Do not expose ComfyUI port 8188 publicly. It must remain bound to `127.0.0.1`.
3. Do not modify or delete an existing user ComfyUI installation.
4. Do not install packages into the user's global Python environment. Use `runtime/venv` only.
5. Do not delete user files outside this repository.
6. If a command fails, diagnose and repair before reporting failure.
7. Only report installation success after `doctor.ps1` passes and the local web UI responds on port 8787.
8. Prefer reversible changes. Runtime files must live under `runtime/`.
9. This V0 intentionally uses Kijai's ComfyUI CCSR wrapper. Do not claim it is official CCSR-v2.

## First-run sequence

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer should:

1. verify Windows and NVIDIA GPU visibility using `nvidia-smi`;
2. record GPU name and VRAM;
3. ensure Git and Python 3.12 are available;
4. create `runtime/venv`;
5. install PyTorch CUDA wheels into that venv;
6. clone ComfyUI into `runtime/ComfyUI`;
7. install ComfyUI requirements;
8. clone `kijai/ComfyUI-CCSR` into ComfyUI `custom_nodes`;
9. install node requirements inside the venv;
10. install GPT Cleaner app requirements;
11. download the fp16 CCSR model into `runtime/ComfyUI/models/CCSR`;
12. write a VRAM-aware config to `config/local.json`;
13. run `doctor.ps1`;
14. launch via `start.ps1`;
15. verify `http://127.0.0.1:8787/api/health` responds.

## VRAM policy

For approximately 8 GB VRAM, default to conservative settings:

- ComfyUI `--lowvram`
- CCSR tiled sampling
- tile size: 256
- tile stride: 128
- VAE encode/decode tile: 512
- keep model loaded: false

If CUDA OOM occurs:

1. reduce tile size from 256 to 192;
2. reduce tile stride from 128 to 96;
3. if still failing, reduce tile size to 128 and stride to 64;
4. restart ComfyUI after changing preset;
5. retry once.

Never silently reduce output scale. Preserve the user's chosen output size unless the user explicitly agrees.

## Common self-repair rules

### Git missing

Use Windows Package Manager if available:

```powershell
winget install --id Git.Git -e --source winget
```

Then refresh PATH or start a new PowerShell process.

### Python 3.12 missing

Use:

```powershell
winget install --id Python.Python.3.12 -e --source winget
```

Locate `python.exe` under the standard user installation path if PATH has not refreshed yet.

### PyTorch cannot see CUDA

- confirm `nvidia-smi` works;
- reinstall PyTorch from the CUDA 12.8 index used by `install.ps1`;
- verify with:

```powershell
.\runtime\venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO CUDA')"
```

### CCSR model missing

Re-run the model download block in `install.ps1`. Do not substitute random checkpoints.

### ComfyUI custom node import failure

Run:

```powershell
.\runtime\venv\Scripts\python.exe -m pip install -r .\runtime\ComfyUI\custom_nodes\ComfyUI-CCSR\requirements.txt
```

Then restart ComfyUI.

## Start / stop

Start:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

or double-click:

```text
START_GPT_CLEANER.bat
```

The launcher starts:

- ComfyUI on `127.0.0.1:8188`
- GPT Cleaner web app on `0.0.0.0:8787`
- browser on `http://127.0.0.1:8787`

For remote access, use Tailscale or a trusted LAN and open only port 8787. Never expose 8188.

## Acceptance checklist

Before telling the user it is ready, verify all of the following:

- `doctor.ps1` exits with code 0
- `torch.cuda.is_available()` is true
- GPU name is correct
- CCSR fp16 model exists
- ComfyUI `/system_stats` responds locally
- GPT Cleaner `/api/health` responds
- web page loads
- no external AI API key is required

After those pass, tell the user the exact local URL and, if applicable, the Tailscale/LAN URL.
