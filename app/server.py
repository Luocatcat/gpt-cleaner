from __future__ import annotations

import base64
import io
import json
import os
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
import requests
from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image
from werkzeug.utils import secure_filename

from app.restoration import (
    NEGATIVE_PROMPT,
    POSITIVE_PROMPT,
    controlled_degrade,
    get_profile,
    multiscale_fuse,
    png_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
CONFIG_DIR = ROOT / "config"
RUNTIME_DIR = ROOT / "runtime"
WORK_DIR = RUNTIME_DIR / "requests"
DEBUG_DIR = RUNTIME_DIR / "debug"
BENCH_DIR = RUNTIME_DIR / "benchmarks"
for directory in (WORK_DIR, DEBUG_DIR, BENCH_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict:
    with (CONFIG_DIR / "default.json").open("r", encoding="utf-8-sig") as f:
        defaults = json.load(f)
    local_path = CONFIG_DIR / "local.json"
    if not local_path.exists():
        return defaults
    with local_path.open("r", encoding="utf-8-sig") as f:
        local = json.load(f)
    # Old installs can keep local.json: new V0.3 keys are filled from defaults.
    return _deep_merge(defaults, local)


CONFIG = load_config()
COMFY_URL = os.environ.get("GPT_CLEANER_COMFY_URL", CONFIG.get("comfy_url", "http://127.0.0.1:8188"))

app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024


def comfy_get(path: str, timeout: float = 10):
    response = requests.get(f"{COMFY_URL}{path}", timeout=timeout)
    response.raise_for_status()
    return response


def comfy_post(path: str, **kwargs):
    response = requests.post(f"{COMFY_URL}{path}", timeout=60, **kwargs)
    response.raise_for_status()
    return response


def clamp_float(value, low: float, high: float, fallback: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, value))


def _frequency_safe_clean(image: Image.Image, preset_name: str, structure_protection: float) -> Image.Image:
    """V0.2 deterministic fallback. Not the main V0.3 engine."""
    presets = CONFIG.get("presets", {})
    preset = presets.get(preset_name, presets.get("standard", {}))
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    luma = lab[:, :, 0]
    smooth = cv2.bilateralFilter(
        luma,
        d=int(preset.get("bilateral_d", 5)),
        sigmaColor=float(preset.get("bilateral_sigma_color", 18)),
        sigmaSpace=float(preset.get("bilateral_sigma_space", 18)),
    )
    base = float(preset.get("preclean_strength", 0.24))
    strength = float(np.clip(base * (1.08 - 0.34 * structure_protection), 0.03, 0.50))
    lab[:, :, 0] = cv2.addWeighted(luma, 1.0 - strength, smooth, strength, 0)
    return Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def upload_to_comfy(path: Path) -> str:
    with path.open("rb") as f:
        files = {"image": (path.name, f, "image/png")}
        data = {"overwrite": "true", "type": "input"}
        payload = comfy_post("/upload/image", files=files, data=data).json()
    return payload.get("name", path.name)


def _supir_settings() -> dict:
    return CONFIG.get("supir", {})


def build_supir_prompt(input_name: str, profile_name: str) -> dict:
    profile = get_profile(profile_name)
    supir = _supir_settings()
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": input_name},
        },
        "2": {
            "class_type": "SUPIR_Upscale",
            "inputs": {
                "supir_model": supir.get("model", "SUPIR-v0Q_fp16.safetensors"),
                "sdxl_model": supir.get("sdxl_model", "sd_xl_base_1.0.safetensors"),
                "image": ["1", 0],
                "seed": int(supir.get("seed", 123)),
                "resize_method": "lanczos",
                "scale_by": 1.0,
                "steps": int(profile.steps),
                "restoration_scale": float(supir.get("restoration_scale", -1.0)),
                "cfg_scale": float(profile.cfg_scale),
                "a_prompt": supir.get("positive_prompt", POSITIVE_PROMPT),
                "n_prompt": supir.get("negative_prompt", NEGATIVE_PROMPT),
                "s_churn": int(profile.s_churn),
                "s_noise": float(profile.s_noise),
                "control_scale": float(profile.control_scale),
                "cfg_scale_start": float(profile.cfg_scale_start),
                "control_scale_start": float(profile.control_scale_start),
                "color_fix_type": supir.get("color_fix", "Wavelet"),
                "keep_model_loaded": bool(supir.get("keep_model_loaded", False)),
                "use_tiled_vae": True,
                "encoder_tile_size_pixels": int(supir.get("vae_tile_pixels", 512)),
                "decoder_tile_size_latent": int(supir.get("vae_tile_latent", 64)),
                "captions": "",
                "diffusion_dtype": supir.get("diffusion_dtype", "fp16"),
                "encoder_dtype": supir.get("encoder_dtype", "fp32"),
                "batch_size": 1,
                "use_tiled_sampling": True,
                "sampler_tile_size": int(supir.get("sampler_tile_size", 512)),
                "sampler_tile_stride": int(supir.get("sampler_tile_stride", 256)),
                "fp8_unet": bool(supir.get("fp8_unet", True)),
                "fp8_vae": False,
                "sampler": supir.get("sampler", "RestoreEDMSampler"),
            },
        },
        "3": {
            "class_type": "SaveImage",
            "inputs": {"images": ["2", 0], "filename_prefix": "gpt_cleaner_supir"},
        },
    }


def build_ccsr_prompt(input_name: str, profile_name: str) -> dict:
    """Legacy fallback only."""
    preset = CONFIG.get("presets", {}).get(profile_name, CONFIG.get("presets", {}).get("standard", {}))
    ccsr = CONFIG.get("ccsr", {})
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": input_name}},
        "2": {
            "class_type": "DownloadAndLoadCCSRModel",
            "inputs": {"model": ccsr.get("model", "real-world_ccsr-fp16.safetensors")},
        },
        "3": {
            "class_type": "CCSR_Upscale",
            "inputs": {
                "ccsr_model": ["2", 0],
                "image": ["1", 0],
                "resize_method": "lanczos",
                "scale_by": 1.0,
                "steps": int(preset.get("steps", 12)),
                "t_max": float(preset.get("t_max", 0.54)),
                "t_min": float(preset.get("t_min", 0.40)),
                "sampling_method": ccsr.get("sampling_method", "ccsr_tiled_vae_gaussian_weights"),
                "tile_size": int(ccsr.get("tile_size", 256)),
                "tile_stride": int(ccsr.get("tile_stride", 128)),
                "vae_tile_size_encode": int(ccsr.get("vae_tile_encode", 512)),
                "vae_tile_size_decode": int(ccsr.get("vae_tile_decode", 512)),
                "color_fix_type": ccsr.get("color_fix", "wavelet"),
                "keep_model_loaded": False,
                "seed": 123,
            },
        },
        "4": {
            "class_type": "SaveImage",
            "inputs": {"images": ["3", 0], "filename_prefix": "gpt_cleaner_ccsr"},
        },
    }


def queue_and_wait(prompt: dict, output_node: str, timeout_seconds: int = 1200) -> dict:
    queued = comfy_post("/prompt", json={"prompt": prompt}).json()
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        node_errors = queued.get("node_errors")
        raise RuntimeError(f"ComfyUI rejected workflow: {node_errors or queued}")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        history = comfy_get(f"/history/{prompt_id}", timeout=30).json()
        item = history.get(prompt_id)
        if item:
            status = item.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution failed: {status}")
            images = item.get("outputs", {}).get(output_node, {}).get("images", [])
            if images:
                return images[0]
        time.sleep(1.0)
    raise TimeoutError("Timed out waiting for ComfyUI output")


def fetch_output_image(meta: dict) -> Image.Image:
    params = {
        "filename": meta["filename"],
        "subfolder": meta.get("subfolder", ""),
        "type": meta.get("type", "output"),
    }
    response = requests.get(f"{COMFY_URL}/view", params=params, timeout=120)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def run_supir(image: Image.Image, profile_name: str, job_dir: Path | None = None) -> tuple[Image.Image, Image.Image]:
    degraded = controlled_degrade(image, profile_name)
    temp_name = f"semantic_{uuid.uuid4().hex[:12]}.png"
    temp_path = WORK_DIR / temp_name
    degraded.save(temp_path, format="PNG")
    try:
        comfy_name = upload_to_comfy(temp_path)
        meta = queue_and_wait(build_supir_prompt(comfy_name, profile_name), "3")
        generated = fetch_output_image(meta)
        if job_dir is not None:
            degraded.save(job_dir / f"degraded_{profile_name}.png")
            generated.save(job_dir / f"supir_raw_{profile_name}.png")
        return degraded, generated
    finally:
        temp_path.unlink(missing_ok=True)


def run_ccsr(image: Image.Image, profile_name: str) -> Image.Image:
    degraded = controlled_degrade(image, profile_name)
    temp_path = WORK_DIR / f"ccsr_{uuid.uuid4().hex[:12]}.png"
    degraded.save(temp_path, format="PNG")
    try:
        comfy_name = upload_to_comfy(temp_path)
        meta = queue_and_wait(build_ccsr_prompt(comfy_name, profile_name), "4")
        generated = fetch_output_image(meta)
        return multiscale_fuse(image, generated, profile_name, 0.94, force_safe=True)
    finally:
        temp_path.unlink(missing_ok=True)


def _node_available(class_type: str) -> bool:
    try:
        response = comfy_get(f"/object_info/{class_type}", timeout=5)
        data = response.json()
        return bool(data) and class_type in data
    except Exception:
        return False


def _image_data_url(image: Image.Image) -> str:
    encoded = base64.b64encode(png_bytes(image)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/health")
def health():
    comfy_ok = False
    error = None
    try:
        comfy_ok = comfy_get("/system_stats", timeout=3).ok
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    supir_ok = comfy_ok and _node_available("SUPIR_Upscale")
    ccsr_ok = comfy_ok and _node_available("CCSR_Upscale")
    return jsonify(
        {
            "ok": True,
            "safe": True,
            "comfy": comfy_ok,
            "supir": supir_ok,
            "ccsr": ccsr_ok,
            "engine": "SUPIR semantic restoration + multiscale structure fusion",
            "default_mode": CONFIG.get("default_mode", "semantic"),
            "error": error,
        }
    )


@app.post("/api/clean")
def clean():
    if "image" not in request.files:
        return jsonify({"error": "Missing image"}), 400
    uploaded = request.files["image"]
    if not uploaded.filename:
        return jsonify({"error": "Empty filename"}), 400

    profile_name = request.form.get("preset", "standard")
    if profile_name not in {"light", "standard", "heavy"}:
        profile_name = "standard"
    mode = request.form.get("mode", CONFIG.get("default_mode", "semantic"))
    if mode not in {"semantic", "safe", "ccsr"}:
        mode = "semantic"
    structure = clamp_float(request.form.get("structure", 0.94), 0.0, 1.0, 0.94)

    try:
        original = Image.open(uploaded.stream).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Invalid image: {exc}"}), 400

    safe_stem = Path(secure_filename(uploaded.filename)).stem or "image"
    job_id = uuid.uuid4().hex[:12]
    job_dir = DEBUG_DIR / f"{job_id}_{safe_stem}"
    job_dir.mkdir(parents=True, exist_ok=True)
    original.save(job_dir / "original.png")

    try:
        if mode == "safe":
            result = _frequency_safe_clean(original, profile_name, structure)
            result.save(job_dir / "safe.png")
        elif mode == "ccsr":
            if not _node_available("CCSR_Upscale"):
                return jsonify({"error": "Legacy CCSR engine is not available."}), 503
            result = run_ccsr(original, profile_name)
            result.save(job_dir / "ccsr_fused.png")
        else:
            if not _node_available("SUPIR_Upscale"):
                return jsonify({"error": "SUPIR semantic engine is not installed/loaded. Run UPDATE_GPT_CLEANER.bat, restart, then retry."}), 503
            _, generated = run_supir(original, profile_name, job_dir)
            result = multiscale_fuse(original, generated, profile_name, structure)
            result.save(job_dir / "semantic_fused.png")
    except requests.RequestException as exc:
        return jsonify({"error": f"ComfyUI connection failed: {exc}"}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500

    response = send_file(
        io.BytesIO(png_bytes(result)),
        mimetype="image/png",
        as_attachment=False,
        download_name=f"{safe_stem}_cleaned.png",
        max_age=0,
    )
    response.headers["X-GPT-Cleaner-Mode"] = mode
    response.headers["X-GPT-Cleaner-Debug"] = str(job_dir)
    return response


@app.post("/api/benchmark")
def benchmark():
    """V0.3 tuning mode: returns four 1X candidates from one source image.

    A: controlled degradation only (expected to look soft; diagnostic only)
    B: low semantic reconstruction
    C: standard semantic reconstruction
    D: same standard SUPIR result with tighter structure fusion
    """
    if "image" not in request.files:
        return jsonify({"error": "Missing image"}), 400
    uploaded = request.files["image"]
    try:
        original = Image.open(uploaded.stream).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Invalid image: {exc}"}), 400
    if not _node_available("SUPIR_Upscale"):
        return jsonify({"error": "SUPIR semantic engine is not available."}), 503

    safe_stem = Path(secure_filename(uploaded.filename or "image.png")).stem or "image"
    job_id = uuid.uuid4().hex[:12]
    job_dir = BENCH_DIR / f"{job_id}_{safe_stem}"
    job_dir.mkdir(parents=True, exist_ok=True)
    original.save(job_dir / "00_original.png")

    try:
        a_small = controlled_degrade(original, "standard")
        a = a_small.resize(original.size, Image.Resampling.LANCZOS)
        a.save(job_dir / "A_clean-base.png")

        _, raw_low = run_supir(original, "light", job_dir)
        b = multiscale_fuse(original, raw_low, "light", 0.94)
        b.save(job_dir / "B_semantic-low.png")

        _, raw_mid = run_supir(original, "standard", job_dir)
        c = multiscale_fuse(original, raw_mid, "standard", 0.92)
        c.save(job_dir / "C_semantic-mid.png")

        d = multiscale_fuse(original, raw_mid, "standard", 0.985, force_safe=True)
        d.save(job_dir / "D_structure-safe.png")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "debug_dir": str(job_dir)}), 500

    return jsonify(
        {
            "ok": True,
            "job": job_id,
            "debug_dir": str(job_dir),
            "images": {
                "A_clean-base": _image_data_url(a),
                "B_semantic-low": _image_data_url(b),
                "C_semantic-mid": _image_data_url(c),
                "D_structure-safe": _image_data_url(d),
            },
        }
    )


if __name__ == "__main__":
    host = CONFIG.get("web_host", "127.0.0.1")
    port = int(CONFIG.get("web_port", 8787))
    app.run(host=host, port=port, debug=False)
