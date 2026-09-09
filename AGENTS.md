# GPT Cleaner · Agent Installation Contract

This repository is designed to be installed and maintained by an agent on a Windows NVIDIA machine with minimal user involvement.

## Mission

Install and launch GPT Cleaner so the user can open a minimal web page, upload a GPT-generated image, remove high-frequency AI artifacts, compare before/after, and save the result.

Primary target machine:

- Windows 64-bit
- Ryzen 9 7900X
- 32 GB RAM
- NVIDIA RTX 5060 8 GB

## Product behavior

V0.2 has two routes:

- **safe cleanup** (default): deterministic high-frequency suppression with edge protection. This route must work even if ComfyUI is unavailable.
- **AI refine** (experimental): preclean → CCSR → original low-frequency structure reinjection. Do not return raw CCSR output directly.

For character sheets, default to safe cleanup and structure protection >= 0.94.

## Non-negotiable rules

1. Do not upload user images to any external AI service.
2. Do not expose ComfyUI port 8188 publicly. It must remain bound to `127.0.0.1`.
3. Do not modify or delete an existing user ComfyUI installation.
4. Do not install packages into the user's global Python environment. Use `runtime/venv` only.
5. Do not delete user files outside this repository.
6. If a command fails, diagnose and repair before reporting failure.
7. Only report full installation success after `doctor.ps1` passes and the local web UI responds on port 8787.
8. Safe cleanup availability is still useful if the optional ComfyUI refine engine fails. Report that distinction accurately.
9. Prefer reversible changes. Runtime files must live under `runtime/`.
10. The current ComfyUI route uses Kijai's CCSR wrapper. Do not claim it is official CCSR-v2.

## First-run sequence

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer should:

1. verify NVIDIA GPU visibility using `nvidia-smi`;
2. record GPU name and VRAM;
3. ensure Git and a real Python 3.12 interpreter are available;
4. create `runtime/venv`;
5. install PyTorch CUDA wheels into that venv;
6. obtain ComfyUI under `runtime/ComfyUI`;
7. install ComfyUI requirements;
8. obtain `kijai/ComfyUI-CCSR` under ComfyUI `custom_nodes`;
9. install node requirements inside the venv;
10. install GPT Cleaner app requirements;
11. patch the CCSR node import path for current ComfyUI behavior;
12. download the fp16 CCSR model under `runtime/ComfyUI/models/CCSR`;
13. write a VRAM-aware config to `config/local.json`;
14. run `doctor.ps1`;
15. launch via `start.ps1`;
16. verify `http://127.0.0.1:8787/api/health` responds.

## Known first-run issues already handled by repository scripts

Do not reintroduce these bugs:

### PowerShell `nvidia-smi` pipeline race

Do not pipe `nvidia-smi` directly into `Select-Object -First 1` while relying on `$LASTEXITCODE`. PowerShell 5.1 can terminate the native process early and produce an invalid exit code. Collect the complete native output first, store `$LASTEXITCODE`, then select the first non-empty line.

### Windows Store Python stub

`Get-Command python` may resolve to the Microsoft Store launcher instead of a real interpreter. Never call `.Trim()` on unchecked command output. Validate:

- process exit code is 0;
- output is non-empty;
- the resolved executable exists;
- `sys.version_info` reports 3.12.

### GitHub direct clone instability

If `git clone` fails because of reset/timeout/pack errors, use the repository codeload zip fallback. Do not repeatedly hammer clone indefinitely.

### Hugging Face direct timeout

Try normal Hugging Face first. If the CCSR checkpoint cannot be downloaded, retry through `HF_ENDPOINT=https://hf-mirror.com`. This is a file mirror, not an AI inference service.

### `huggingface_hub` / transformers mismatch

Do not downgrade `huggingface_hub` below the version required by current ComfyUI transformers. GPT Cleaner pins it to `>=1.5,<2`.

### Current ComfyUI custom node import path

Recent ComfyUI versions do not guarantee `custom_nodes/` is present on `sys.path`. The installer prepends a `GPT_CLEANER_SYSPATH_COMPAT` block to `ComfyUI-CCSR/__init__.py`. Preserve that patch. If execution reports `No module named 'ComfyUI-CCSR'`, confirm the patch exists, restart ComfyUI, then rerun the refine smoke test.

## VRAM policy

For approximately 8 GB VRAM, default to conservative settings:

- ComfyUI `--lowvram`
- CCSR tiled sampling
- tile size: 256
- tile stride: 128
- VAE encode/decode tile: 512
- keep model loaded: false
- CCSR generation at 1x only; final 2x/4x resize occurs after structure reinjection

If CUDA OOM occurs:

1. reduce tile size from 256 to 192;
2. reduce tile stride from 128 to 96;
3. if still failing, reduce tile size to 128 and stride to 64;
4. restart ComfyUI after changing preset;
5. retry once.

Never silently reduce the requested final output dimensions.

## Start / update

Start:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

or double-click `START_GPT_CLEANER.bat`.

Update code while preserving already-downloaded models and runtime:

```powershell
powershell -ExecutionPolicy Bypass -File .\update.ps1
```

or double-click `UPDATE_GPT_CLEANER.bat`.

The updater intentionally uses codeload zip so it also works on installations originally obtained without `.git` metadata.

## Smoke tests

Safe deterministic path:

```powershell
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py
```

Optional AI refine path:

```powershell
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --refine
```

The second command is the authoritative test for the ComfyUI/CCSR node execution path.

## Start / stop behavior

The launcher starts:

- optional ComfyUI AI-refine engine on `127.0.0.1:8188`;
- GPT Cleaner web app on `0.0.0.0:8787`;
- browser on `http://127.0.0.1:8787`.

If ComfyUI fails to start, do not abort the whole product. Start the web app and clearly report that safe cleanup is available while AI refine is unavailable.

For remote access, use Tailscale or a trusted LAN and expose only port 8787. Never expose 8188.

## Acceptance checklist

Before telling the user it is ready, verify:

- `doctor.ps1` exits with code 0 for the installed runtime;
- `torch.cuda.is_available()` is true when AI refine is expected;
- GPU name is correct;
- GPT Cleaner `/api/health` responds;
- safe smoke test passes;
- web page loads;
- no external AI API key is required.

For **full AI-refine ready** status also verify:

- CCSR fp16 model exists;
- ComfyUI `/system_stats` responds locally;
- `scripts/smoke_test.py --refine` passes.

After those pass, tell the user the exact local URL and, if applicable, the Tailscale/LAN URL.
