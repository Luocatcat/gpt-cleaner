from __future__ import annotations

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

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
CONFIG_DIR = ROOT / "config"
RUNTIME_DIR = ROOT / "runtime"
WORK_DIR = RUNTIME_DIR / "requests"
WORK_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    config_path = CONFIG_DIR / "local.json"
    if not config_path.exists():
        config_path = CONFIG_DIR / "default.json"
    # utf-8-sig also accepts ordinary UTF-8 and safely handles Windows PowerShell BOM output.
    with config_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


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


def preclean_image(image: Image.Image, preset_name: str, structure_protection: float) -> Image.Image:
    """Remove unstable high-frequency texture while keeping large edges intact.

    structure_protection: 0 = freer cleanup, 1 = strict original structure.
    """
    preset = CONFIG["presets"].get(preset_name, CONFIG["presets"]["standard"])
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    smooth = cv2.bilateralFilter(
        bgr,
        d=int(preset["bilateral_d"]),
        sigmaColor=float(preset["bilateral_sigma_color"]),
        sigmaSpace=float(preset["bilateral_sigma_space"]),
    )

    base_strength = float(preset["preclean_strength"])
    # Higher structure protection means less aggressive local smoothing.
    strength = base_strength * (1.10 - 0.55 * structure_protection)
    strength = max(0.05, min(0.75, strength))
    blended = cv2.addWeighted(bgr, 1.0 - strength, smooth, strength, 0)

    out = cv2.cvtColor(blended, cv2.COLOR_BGR2RGB)
    return Image.fromarray(out)


def upload_to_comfy(path: Path) -> str:
    with path.open("rb") as f:
        files = {"image": (path.name, f, "image/png")}
        data = {"overwrite": "true", "type": "input"}
        payload = comfy_post("/upload/image", files=files, data=data).json()
    return payload.get("name", path.name)


def build_prompt(input_name: str, output_scale: float, preset_name: str, structure_protection: float) -> dict:
    preset = CONFIG["presets"].get(preset_name, CONFIG["presets"]["standard"])

    # Strict structure protection narrows the generative window.
    protection = clamp_float(structure_protection, 0.0, 1.0, 0.85)
    t_max = float(preset["t_max"]) - protection * 0.08
    t_min = float(preset["t_min"]) + protection * 0.04
    if t_min >= t_max:
        t_min = max(0.05, t_max - 0.08)

    prompt = {
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
                "resize_method": "lanczos",
                "scale_by": float(output_scale),
                "steps": int(preset["steps"]),
                "t_max": round(t_max, 4),
                "t_min": round(t_min, 4),
                "sampling_method": CONFIG.get("sampling_method", "ccsr_tiled_mixdiff"),
                "tile_size": int(CONFIG.get("tile_size", 256)),
                "tile_stride": int(CONFIG.get("tile_stride", 128)),
                "vae_tile_size_encode": int(CONFIG.get("vae_tile_encode", 512)),
                "vae_tile_size_decode": int(CONFIG.get("vae_tile_decode", 512)),
                "color_fix_type": CONFIG.get("color_fix", "adain"),
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
    return prompt


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
    return jsonify(
        {
            "ok": comfy_ok,
            "comfy": comfy_ok,
            "comfy_url": COMFY_URL,
            "engine": "ComfyUI + CCSR",
            "error": comfy_error,
        }
    ), (200 if comfy_ok else 503)


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

    structure = clamp_float(request.form.get("structure", 0.85), 0.0, 1.0, 0.85)
    scale_label = request.form.get("scale", "1")
    scale_map = {"1": 1.0, "2": 2.0, "4": 4.0}
    output_scale = scale_map.get(scale_label, 1.0)

    try:
        original = Image.open(uploaded.stream).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Invalid image: {exc}"}), 400

    cleaned = preclean_image(original, preset_name, structure)
    job_id = uuid.uuid4().hex[:12]
    safe_stem = Path(secure_filename(uploaded.filename)).stem or "image"
    input_path = WORK_DIR / f"{safe_stem}_{job_id}.png"
    cleaned.save(input_path, format="PNG")

    try:
        comfy_name = upload_to_comfy(input_path)
        prompt = build_prompt(comfy_name, output_scale, preset_name, structure)
        output_meta = queue_and_wait(prompt)
        result_bytes = fetch_output_image(output_meta)
    except requests.RequestException as exc:
        return jsonify({"error": f"ComfyUI connection failed: {exc}"}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except OSError:
            pass

    output_name = f"{safe_stem}_cleaned.png"
    return send_file(
        io.BytesIO(result_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=output_name,
        max_age=0,
    )


if __name__ == "__main__":
    host = CONFIG.get("web_host", "127.0.0.1")
    port = int(CONFIG.get("web_port", 8787))
    app.run(host=host, port=port, debug=False)
