# GPT Cleaner V0.3 · Windows Agent Contract

This project is intended to be installed and maintained by an agent on a Windows NVIDIA machine with minimal user involvement.

## Mission

Get the user from a GitHub URL to a working local web page that cleans GPT-generated image artifacts. V0.3's main engine is **semantic restoration**, not simple sharpening or blur.

Target machine:

- Windows 64-bit
- Ryzen 9 7900X
- 32 GB RAM
- NVIDIA RTX 5060 8 GB
- preferred project directory: `D:\gpt-cleaner`

## V0.3 processing definition

The intended pipeline is:

```text
original
  -> controlled downscale/degradation
  -> SUPIR semantic restoration
  -> multiscale frequency fusion with original structure
  -> exact 1X output
```

Do not replace this with a simple sharpen / Real-ESRGAN / bilateral-only path and call it complete.

The deterministic `safe` path is only a fallback. Legacy CCSR may remain installed for comparison but is not the default engine.

## Non-negotiable safety / environment rules

1. Never upload the user's images to an external AI service.
2. ComfyUI port `8188` must listen on `127.0.0.1` only.
3. Do not delete or modify an unrelated ComfyUI or Python installation.
4. Project Python packages must live inside `runtime/venv`.
5. Preserve `runtime/` during upgrades unless the user explicitly approves a clean reinstall.
6. Preserve existing large models whenever possible.
7. Do not declare success because the web page merely opens. Semantic inference must be tested separately.
8. Fix reproducible installer bugs in this repository, not only as undocumented local edits.
9. On the target RTX 5060 8GB, use tiled sampling / tiled VAE / fp8 UNet defaults first.
10. V0.3 is currently personal/non-commercial benchmark use because SUPIR has non-commercial restrictions.

## Existing-machine upgrade

If `D:\gpt-cleaner\runtime` already exists, **do not run a destructive reinstall**.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\update.ps1
```

or double-click:

```text
UPDATE_GPT_CLEANER.bat
```

The updater must preserve:

- `runtime/venv`
- `runtime/ComfyUI`
- existing CCSR checkpoint(s)
- logs / previous benchmark outputs

It may add:

- `runtime/ComfyUI/custom_nodes/ComfyUI-SUPIR`
- `SUPIR-v0Q_fp16.safetensors`
- `sd_xl_base_1.0.safetensors`

First V0.3 upgrade therefore downloads roughly 9.6 GB of new model files.

## Fresh install

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Fresh V0.3 installs SUPIR as the main engine. Legacy CCSR is optional:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallLegacyCCSR
```

## Known Windows issues learned from the first real install

These regressions must not be reintroduced:

### PowerShell 5.1 + nvidia-smi

Do not pipe `nvidia-smi` directly into `Select-Object -First 1` while checking `$LASTEXITCODE`. PowerShell 5.1 may terminate the process early and report `-1`.

Correct pattern:

```powershell
$rows = @(& $nvidia.Source --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null)
$exit = $LASTEXITCODE
$row = $rows | Where-Object { $_ -and $_.Trim() } | Select-Object -First 1
```

### Windows Store Python stub

`Get-Command python` can resolve to a Store launcher that is not a usable Python interpreter. Always execute and validate output / exit code before using it.

### GitHub clone instability

If `git clone` fails due to reset / timeout / pack errors, use `codeload.github.com/.../zip/refs/heads/...` fallback instead of repeatedly retrying clone.

### Hugging Face connectivity

Large model downloads may fail to `huggingface.co`. The scripts first try Hugging Face directly, then `HF_ENDPOINT=https://hf-mirror.com`. Do not silently swap to an unrelated checkpoint.

### huggingface_hub / transformers conflict

Do not downgrade `huggingface_hub` below the version required by the installed transformers. The app currently allows `huggingface_hub>=1.5,<2`.

### Legacy ComfyUI-CCSR import

If the preserved legacy CCSR node errors with `No module named 'ComfyUI-CCSR'`, retain the `GPT_CLEANER_SYSPATH_COMPAT` parent-path patch. This is only for the legacy fallback.

## Acceptance sequence

After install/update:

1. run `doctor.ps1`;
2. start via `start.ps1` / `START_GPT_CLEANER.bat`;
3. verify `http://127.0.0.1:8787/api/health` returns `supir: true`;
4. run safe smoke test;
5. run semantic smoke test;
6. only then run the four-way benchmark on the user's real Modern Witch source.

Commands:

```powershell
powershell -ExecutionPolicy Bypass -File .\doctor.ps1
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --safe
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --semantic
```

Do not automatically run `--benchmark` on the synthetic image unless needed; the meaningful benchmark uses the user's real source image from the web UI.

## V0.3 benchmark interpretation

The web page can generate:

```text
A_clean-base
B_semantic-low
C_semantic-mid
D_structure-safe
```

Interpret them as follows:

- A: diagnostic degradation base. It is expected to be soft. Never present A as the final solution.
- B: low semantic reconstruction.
- C: main quality candidate.
- D: same semantic family with tighter structural fusion.

The desired result is **not** the sharpest image. It must reduce GPT artifact patterns while restoring coherent detail.

### Inspect these areas

- hair: fewer random fake strands, but visible coherent clump/material detail
- eyes: glass/iris structure should return instead of becoming a purple blur
- skin/resin: smooth but not waxy or featureless
- joints: seams and mechanical boundaries remain readable
- silhouette: front/side/back outlines remain stable
- face: eye/nose/mouth placement must not obviously drift
- background: no tile seams or repeated texture grids

If A is cleaner but B/C/D remain blurry, the SUPIR stage is not contributing enough useful mid/high frequency detail. Do not compensate by adding generic unsharp mask.

If B/C becomes attractive but changes face/shape, adjust the multiscale fusion / structure protection before reducing the entire semantic pass to near zero.

## OOM policy for RTX 5060 8GB

Current default:

- working semantic image around 704–768 px long edge
- tiled sampling: 512 / stride 256
- tiled VAE: 512
- fp8 UNet: enabled
- output: 1X

If CUDA OOM occurs:

1. reduce `supir.sampler_tile_size` to `384`;
2. set stride to `192`;
3. set `supir.vae_tile_pixels` to `384`;
4. restart ComfyUI and retry once;
5. if still OOM, lower the semantic working long edge in `app/restoration.py` from 768 to 704 before touching image quality parameters.

Do not silently lower final output dimensions.

## Reporting back to the user

After V0.3 upgrade, report only:

- update success / failure
- detected GPU and VRAM
- whether SUPIR node loaded
- whether both SUPIR and SDXL model files exist
- doctor result
- semantic smoke test result and output path
- exact local web URL
- any remaining issue requiring approval

Do not overwhelm the user with routine dependency logs unless something failed.
