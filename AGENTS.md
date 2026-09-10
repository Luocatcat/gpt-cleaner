# GPT Cleaner V0.3 · Agent Installation Contract

This repository is installed and maintained by an agent on a Windows NVIDIA machine. Diagnose safe in-scope failures instead of asking the user to relay routine commands.

## Mission

Install, upgrade, launch, and verify GPT Cleaner so the default route performs local SUPIR semantic restoration at exact 1x. Keep deterministic safe cleanup and the old CCSR node available as fallbacks.

Primary target:

- Windows 64-bit;
- Ryzen 9 7900X;
- 32 GB RAM;
- NVIDIA RTX 5060 8 GB;
- preferred path `D:\gpt-cleaner`.

## Product behavior

V0.3 has two user-facing modes:

- **semantic restoration** (default): controlled degradation → Core SUPIR → multi-scale Laplacian fusion → exact original dimensions;
- **safe cleanup**: deterministic luminance micro-texture suppression, available without ComfyUI.

Semantic fallback order is fixed:

```text
SUPIR → legacy CCSR → safe cleanup
```

The HTTP response and web UI must disclose the actual engine. Never report a CCSR or safe fallback as SUPIR success.

The old CCSR wrapper is `kijai/ComfyUI-CCSR`, not official CCSR-v2. Do not rename or misrepresent it.

## Non-negotiable rules

1. Do not upload user images to an external inference service.
2. Do not expose ComfyUI port 8188 beyond `127.0.0.1`.
3. Do not modify or delete another user ComfyUI installation.
4. Use only this repository's `runtime\venv`; do not install into global Python.
5. Do not delete files outside this repository.
6. Preserve `runtime\`, models, logs, and `config\local.json` during upgrade.
7. Diagnose dependency, PATH, CUDA, download, and startup failures before reporting them.
8. Safe cleanup remains useful when optional generative engines fail. Report full, partial, and failed status accurately.
9. V0.3 semantic mode is exact 1x only. Do not silently honor 2x or 4x requests.
10. Do not claim visual-quality success before the modern-witch/BJD A/B is reviewed.

## First installation

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The installer must:

1. query NVIDIA name and VRAM without the PowerShell 5.1 pipeline race;
2. find or install Git;
3. find a real Python 3.12 interpreter, rejecting Windows Store stubs;
4. create `runtime\venv`;
5. install CUDA PyTorch inside that venv;
6. obtain a dedicated `runtime\ComfyUI` with codeload fallback;
7. install ComfyUI requirements;
8. install the legacy CCSR node and its compatibility patch;
9. install GPT Cleaner app requirements;
10. download the old CCSR checkpoint;
11. download the Juggernaut XL Lightning checkpoint and SUPIR v0Q fp16 model patch;
12. write VRAM-aware CCSR settings to `config\local.json`;
13. run `doctor.ps1`;
14. launch locally and verify the web health endpoint.

## Incremental V0.2 upgrade

V0.2 may have been installed from a zip and may have no `.git`. Run the existing updater once to fetch V0.3 source, then run the newly fetched updater a second time to perform semantic model installation:

```powershell
Set-Location D:\gpt-cleaner
powershell -NoProfile -ExecutionPolicy Bypass -File .\update.ps1 -NoStart
powershell -NoProfile -ExecutionPolicy Bypass -File .\update.ps1 -NoStart -SkipDoctor
powershell -NoProfile -ExecutionPolicy Bypass -File .\doctor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

The V0.3 updater must not reinstall Python, PyTorch, the old CCSR model, or the complete runtime. If Core `SUPIRApply` is missing, it updates only this repository's dedicated ComfyUI core while preserving `.git`, `models`, `custom_nodes`, `input`, `output`, `temp`, and `user`.

## Required models

```text
runtime\ComfyUI\models\checkpoints\juggernautXL_v9Rdphoto2Lightning.safetensors
runtime\ComfyUI\models\model_patches\SUPIR-v0Q_fp16.safetensors
runtime\ComfyUI\models\CCSR\real-world_ccsr-fp16.safetensors
```

Model sources are recorded in `scripts\update_manifest.json`. Try Hugging Face directly, then `HF_ENDPOINT=https://hf-mirror.com`. This mirror transfers model files; it is not an inference service.

## Real Windows issues already fixed

Do not reintroduce these failures:

### `nvidia-smi` PowerShell 5.1 race

Never pipe `nvidia-smi` directly into `Select-Object -First 1` while relying on `$LASTEXITCODE`. Collect complete native output, save the exit code, then select the first line.

### Windows Store Python stub

`Get-Command python` can return a launcher instead of Python. Validate exit code, non-empty output, executable path, and Python 3.12 before using it. Never call `.Trim()` on unchecked output.

### GitHub instability

After a failed Git clone, use `codeload.github.com` zip once. Do not retry an unstable clone indefinitely.

### Hugging Face timeout

Retry a failed model download through `https://hf-mirror.com`. Keep already completed model files.

### `huggingface_hub` mismatch

Keep `huggingface_hub>=1.5,<2`; do not downgrade it below current ComfyUI transformers requirements.

### Current ComfyUI CCSR import path

Keep the `GPT_CLEANER_SYSPATH_COMPAT` block in `ComfyUI-CCSR\__init__.py`. If `No module named 'ComfyUI-CCSR'` returns, reapply the patch, restart ComfyUI, and rerun `--ccsr`.

## 8 GB VRAM policy

- launch ComfyUI with `--lowvram`;
- keep semantic working long edge at 768–1024 px;
- keep semantic output at 1x;
- use 512 px tiled VAE decode with 64 px overlap;
- do not install the optional Qwen caption model;
- keep legacy CCSR at 256 tile / 128 stride for approximately 8 GB.

For CCSR CUDA OOM only, reduce tile/stride to 192/96, then 128/64, restarting ComfyUI after each change. Do not silently change final output dimensions.

## Start and verification

Start:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Verify:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\doctor.ps1
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --safe
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --semantic
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --ccsr
```

Interpret results:

- `PASS semantic engine=supir`: full semantic path ran;
- `PARTIAL semantic used ccsr`: SUPIR failed or was unavailable, CCSR worked;
- `PARTIAL semantic used safe`: both generative engines failed, safe worked;
- `FAIL`: requested route or exact dimensions failed.

Only report full V0.3 readiness after doctor, safe smoke, and semantic smoke pass on Windows. Report CCSR separately. A passing synthetic smoke test does not prove the target image meets visual quality.

## Visual acceptance

Run the modern-witch/BJD source at semantic, standard, structure protection 94–98, exact 1x. Compare against the source and Yansen 1K reference for:

- fewer fake hair strands and repeated micro-patterns;
- cleaner skin, resin, glass-eye, and joint materials;
- better medium-scale shading rather than simple blur;
- no visible tile seams;
- stable front/side/back silhouettes and joint positions;
- minimal eye, nose, mouth, and face-shape movement.

If the real source and comparison reference are unavailable, report visual acceptance as `partial`.
