from __future__ import annotations

import io
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

from app.configuration import load_config
from app.image_ops import image_to_png_bytes, preclean_image, resize_exact

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
CONFIG_DIR = ROOT / "config"
RUNTIME_DIR = ROOT / "runtime"
WORK_DIR = RUNTIME_DIR / "requests"
WORK_DIR.mkdir(parents=True, exist_ok=True)


CONFIG = load_config(CONFIG_DIR)
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


def get_preset(name: str) -> dict:
    presets = CONFIG["presets"]
    return presets.get(name, presets["standard"])


def structure_reinject(
    original: Image.Image,
    cleaned: Image.Image,
    generated: Image.Image,
    preset_name: str,
    structure_protection: float,
) -> Image.Image:
    """Keep original low-frequency structure and borrow only a little generated detail.

    This is the missing safety layer from V0. The generative pass is never allowed to
    replace the complete image. Face shape, limbs, hair silhouette, composition and
    large lighting relationships come from the original. Generated pixels contribute
    mainly to the high-frequency band.
    """
    preset = get_preset(preset_name)
    gen = generated.convert("RGB")
    size = gen.size
    orig = original.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    clean = cleaned.convert("RGB").resize(size, Image.Resampling.LANCZOS)

    orig_np = np.asarray(orig, dtype=np.float32)
    clean_np = np.asarray(clean, dtype=np.float32)
    gen_np = np.asarray(gen, dtype=np.float32)

    h, w = gen_np.shape[:2]
    sigma = max(1.2, min(h, w) / 850.0)
    low_orig = cv2.GaussianBlur(orig_np, (0, 0), sigma)
    low_clean = cv2.GaussianBlur(clean_np, (0, 0), sigma)
    low_gen = cv2.GaussianBlur(gen_np, (0, 0), sigma)

    high_clean = clean_np - low_clean
    high_gen = gen_np - low_gen

    base_mix = float(preset.get("gen_detail_mix", 0.18))
    gen_mix = base_mix * (1.16 - 0.66 * structure_protection)
    gen_mix = float(np.clip(gen_mix, 0.03, 0.30))

    # Tiny low-frequency contribution is only allowed when protection is intentionally low.
    low_gen_mix = float(np.clip((1.0 - structure_protection) * 0.04, 0.0, 0.04))
    low_base = low_orig * (1.0 - low_gen_mix) + low_gen * low_gen_mix
    details = high_clean * (1.0 - gen_mix) + high_gen * gen_mix
    out = np.clip(low_base + details, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def upload_to_comfy(path: Path) -> str:
    with path.open("rb") as f:
        files = {"image": (path.name, f, "image/png")}
        data = {"overwrite": "true", "type": "input"}
        payload = comfy_post("/upload/image", files=files, data=data).json()
    return payload.get("name", path.name)


def build_prompt(input_name: str, preset_name: str, structure_protection: float) -> dict:
    preset = get_preset(preset_name)

    protection = clamp_float(structure_protection, 0.0, 1.0, 0.92)
    # V0 was far too generative. Keep the CCSR sampling window narrow; the post-pass
    # will also reinject original structure before the result is returned.
    t_max = float(preset["t_max"]) - protection * 0.035
    t_min = float(preset["t_min"]) + protection * 0.018
    if t_min >= t_max:
        t_min = max(0.05, t_max - 0.06)

    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": input_name},
        },
        "2": {
            "class_type": "DownloadAndLoadCCSRModel",
            "inputs": {"model": CONFIG.get("model", "real-world_ccsr-fp16.safetensors")},
        },
        "3": {
            "class_type": "CCSR_Upscale",
            "inputs": {
                "ccsr_model": ["2", 0],
                "image": ["1", 0],
                # Generation is always done at 1x. Final 2x/4x output happens after
                # structure reinjection, keeping memory predictable on 8 GB cards.
                "resize_method": "lanczos",
                "scale_by": 1.0,
                "steps": int(preset["steps"]),
                "t_max": round(t_max, 4),
                "t_min": round(t_min, 4),
                "sampling_method": CONFIG.get("sampling_method", "ccsr_tiled_vae_gaussian_weights"),
                "tile_size": int(CONFIG.get("tile_size", 256)),
                "tile_stride": int(CONFIG.get("tile_stride", 128)),
                "vae_tile_size_encode": int(CONFIG.get("vae_tile_encode", 512)),
                "vae_tile_size_decode": int(CONFIG.get("vae_tile_decode", 512)),
                "color_fix_type": CONFIG.get("color_fix", "wavelet"),
                "keep_model_loaded": False,
                "seed": 123,
            },
        },
        "4": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["3", 0],
                "filename_prefix": "gpt_cleaner",
            },
        },
    }


def queue_and_wait(prompt: dict, timeout_seconds: int = 900) -> dict:
    queued = comfy_post("/prompt", json={"prompt": prompt}).json()
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return a prompt_id: {queued}")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        history_response = comfy_get(f"/history/{prompt_id}", timeout=30)
        history = history_response.json()
        item = history.get(prompt_id)
        if item:
            status = item.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution failed: {status}")
            outputs = item.get("outputs", {})
            node = outputs.get("4", {})
            images = node.get("images", [])
            if images:
                return images[0]
        time.sleep(1.0)

    raise TimeoutError("Timed out waiting for ComfyUI output")


def fetch_output_image(meta: dict) -> bytes:
    params = {
        "filename": meta["filename"],
        "subfolder": meta.get("subfolder", ""),
        "type": meta.get("type", "output"),
    }
    response = requests.get(f"{COMFY_URL}/view", params=params, timeout=120)
    response.raise_for_status()
    return response.content


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/health")
def health():
    comfy_ok = False
    comfy_error = None
    try:
        comfy_ok = comfy_get("/system_stats", timeout=3).ok
    except Exception as exc:  # noqa: BLE001
        comfy_error = str(exc)
    # The deterministic safe cleaner is part of this Flask process and is ready even
    # when ComfyUI is still warming up. AI refine availability is reported separately.
    return jsonify(
        {
            "ok": True,
            "safe": True,
            "comfy": comfy_ok,
            "comfy_url": COMFY_URL,
            "engine": "frequency-safe-clean + optional CCSR refine",
            "error": comfy_error,
        }
    )


@app.post("/api/clean")
def clean():
    if "image" not in request.files:
        return jsonify({"error": "Missing image"}), 400

    uploaded = request.files["image"]
    if not uploaded.filename:
        return jsonify({"error": "Empty filename"}), 400

    preset_name = request.form.get("preset", "standard")
    if preset_name not in CONFIG["presets"]:
        preset_name = "standard"

    mode = request.form.get("mode", CONFIG.get("default_mode", "safe"))
    if mode not in {"safe", "refine"}:
        mode = "safe"

    structure = clamp_float(request.form.get("structure", 0.92), 0.0, 1.0, 0.92)
    scale_label = request.form.get("scale", "1")
    scale_map = {"1": 1.0, "2": 2.0, "4": 4.0}
    output_scale = scale_map.get(scale_label, 1.0)

    try:
        original = Image.open(uploaded.stream).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Invalid image: {exc}"}), 400

    cleaned = preclean_image(original, get_preset(preset_name), structure)
    safe_stem = Path(secure_filename(uploaded.filename)).stem or "image"

    if mode == "safe":
        result = resize_exact(cleaned, output_scale)
        result_bytes = image_to_png_bytes(result)
    else:
        job_id = uuid.uuid4().hex[:12]
        input_path = WORK_DIR / f"{safe_stem}_{job_id}.png"
        cleaned.save(input_path, format="PNG")
        try:
            # Explicitly fail with a useful message if the optional generative engine is down.
            comfy_get("/system_stats", timeout=4)
            comfy_name = upload_to_comfy(input_path)
            prompt = build_prompt(comfy_name, preset_name, structure)
            output_meta = queue_and_wait(prompt)
            generated_bytes = fetch_output_image(output_meta)
            generated = Image.open(io.BytesIO(generated_bytes)).convert("RGB")
            protected = structure_reinject(original, cleaned, generated, preset_name, structure)
            # Return exact dimensions requested by the user, not CCSR's multiple-of-64 dimensions.
            target_size = (
                max(1, int(round(original.width * output_scale))),
                max(1, int(round(original.height * output_scale))),
            )
            result = protected.resize(target_size, Image.Resampling.LANCZOS)
            result_bytes = image_to_png_bytes(result)
        except requests.RequestException as exc:
            return jsonify({"error": f"AI refine engine unavailable: {exc}. Use 安全清理 or start ComfyUI."}), 502
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500
        finally:
            try:
                input_path.unlink(missing_ok=True)
            except OSError:
                pass

    output_name = f"{safe_stem}_cleaned.png"
    response = send_file(
        io.BytesIO(result_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=output_name,
        max_age=0,
    )
    response.headers["X-GPT-Cleaner-Mode"] = mode
    return response


if __name__ == "__main__":
    host = CONFIG.get("web_host", "127.0.0.1")
    port = int(CONFIG.get("web_port", 8787))
    app.run(host=host, port=port, debug=False)
