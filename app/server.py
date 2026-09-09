from __future__ import annotations

import io
import json
import os
import time
import uuid
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image
from werkzeug.utils import secure_filename

from app.comfy_workflows import build_ccsr_prompt, build_supir_prompt, classify_engines
from app.configuration import load_config
from app.image_ops import (
    controlled_degrade,
    image_to_png_bytes,
    laplacian_fuse,
    preclean_image,
    resize_exact,
)

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
CONFIG_DIR = ROOT / "config"
RUNTIME_DIR = ROOT / "runtime"
WORK_DIR = RUNTIME_DIR / "requests"
DEBUG_DIR = RUNTIME_DIR / "debug"
WORK_DIR.mkdir(parents=True, exist_ok=True)


CONFIG = load_config(CONFIG_DIR)
COMFY_URL = os.environ.get("GPT_CLEANER_COMFY_URL", CONFIG.get("comfy_url", "http://127.0.0.1:8188"))

app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

_ENGINE_STATUS_CACHE: tuple[float, dict] | None = None


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


def upload_to_comfy(path: Path) -> str:
    with path.open("rb") as f:
        files = {"image": (path.name, f, "image/png")}
        data = {"overwrite": "true", "type": "input"}
        payload = comfy_post("/upload/image", files=files, data=data).json()
    return payload.get("name", path.name)


def _local_model_files() -> set[str]:
    models_dir = RUNTIME_DIR / "ComfyUI" / "models"
    if not models_dir.exists():
        return set()
    return {
        path.name
        for path in models_dir.rglob("*")
        if path.is_file()
    }


def get_engine_status(force: bool = False) -> dict:
    global _ENGINE_STATUS_CACHE
    now = time.monotonic()
    if not force and _ENGINE_STATUS_CACHE and now - _ENGINE_STATUS_CACHE[0] < 15:
        return _ENGINE_STATUS_CACHE[1]

    try:
        object_info = comfy_get("/object_info", timeout=8).json()
        status = classify_engines(object_info, _local_model_files(), CONFIG)
        status["comfy"] = True
        status["error"] = None
        _ENGINE_STATUS_CACHE = (now, status)
        return status
    except Exception as exc:  # noqa: BLE001
        reason = str(exc)
        return {
            "comfy": False,
            "error": reason,
            "supir": {"ready": False, "missing": ["ComfyUI unavailable"]},
            "ccsr": {"ready": False, "missing": ["ComfyUI unavailable"]},
        }


def queue_and_wait(
    prompt: dict,
    output_node_id: str,
    timeout_seconds: int = 900,
) -> dict:
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
            node = outputs.get(output_node_id, {})
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


def run_comfy_engine(
    engine: str,
    input_path: Path,
    preset: dict,
    structure_protection: float,
) -> Image.Image:
    comfy_name = upload_to_comfy(input_path)
    with Image.open(input_path) as source:
        width, height = source.size

    if engine == "supir":
        prompt = build_supir_prompt(comfy_name, width, height, CONFIG["semantic"])
        output_node_id = "13"
    elif engine == "ccsr":
        prompt = build_ccsr_prompt(
            comfy_name,
            preset,
            structure_protection,
            CONFIG["ccsr"],
        )
        output_node_id = "4"
    else:
        raise ValueError(f"Unsupported ComfyUI engine: {engine}")

    output_meta = queue_and_wait(prompt, output_node_id)
    generated_bytes = fetch_output_image(output_meta)
    return Image.open(io.BytesIO(generated_bytes)).convert("RGB")


def _save_debug_bundle(
    job_id: str,
    degraded: Image.Image,
    generated: Image.Image | None,
    result: Image.Image,
    manifest: dict,
) -> None:
    debug_path = DEBUG_DIR / job_id
    debug_path.mkdir(parents=True, exist_ok=True)
    degraded.save(debug_path / "01-degraded.png", format="PNG")
    if generated is not None:
        generated.save(debug_path / "02-generated.png", format="PNG")
    result.save(debug_path / "03-fused.png", format="PNG")
    with (debug_path / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def _safe_header(value: str) -> str:
    return value.encode("latin-1", "replace").decode("latin-1")[:512]


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/health")
def health():
    status = get_engine_status()
    supir = status["supir"]
    ccsr = status["ccsr"]
    if supir["ready"]:
        semantic_status = "ready"
    elif ccsr["ready"]:
        semantic_status = "fallback"
    else:
        semantic_status = "safe-only"
    comfy_ok = bool(status.get("comfy", supir["ready"] or ccsr["ready"]))
    return jsonify(
        {
            "ok": True,
            "safe": True,
            "comfy": comfy_ok,
            "comfy_url": COMFY_URL,
            "default_mode": "semantic",
            "semantic_status": semantic_status,
            "supir": supir,
            "ccsr": ccsr,
            "error": status.get("error"),
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

    mode = request.form.get("mode", CONFIG.get("default_mode", "semantic"))
    if mode == "refine":
        mode = "ccsr"
    if mode not in {"safe", "semantic", "ccsr"}:
        mode = CONFIG.get("default_mode", "semantic")
    if mode not in {"safe", "semantic", "ccsr"}:
        mode = "semantic"

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

    actual_engine = "safe"
    fallback_reasons: list[str] = []
    if mode == "safe":
        result = resize_exact(cleaned, output_scale)
    else:
        job_id = uuid.uuid4().hex[:12]
        input_path = WORK_DIR / f"{safe_stem}_{job_id}.png"
        degraded = controlled_degrade(original, get_preset(preset_name))
        degraded.save(input_path, format="PNG")
        started_at = time.monotonic()
        generated = None
        try:
            status = get_engine_status(force=True)
            candidates = ("supir", "ccsr") if mode == "semantic" else ("ccsr",)
            for engine in candidates:
                engine_status = status[engine]
                if not engine_status["ready"]:
                    missing = ", ".join(engine_status["missing"])
                    fallback_reasons.append(f"{engine}: unavailable ({missing})")
                    continue
                try:
                    generated = run_comfy_engine(
                        engine,
                        input_path,
                        get_preset(preset_name),
                        structure,
                    )
                    actual_engine = engine
                    break
                except Exception as exc:  # noqa: BLE001
                    fallback_reasons.append(f"{engine}: {exc}")

            if generated is None and mode == "ccsr":
                return jsonify(
                    {"error": "CCSR unavailable", "details": fallback_reasons}
                ), 503

            if generated is None:
                result = cleaned.resize(original.size, Image.Resampling.LANCZOS)
                actual_engine = "safe"
            else:
                result = laplacian_fuse(
                    original,
                    cleaned,
                    generated,
                    get_preset(preset_name).get("laplacian_generated_mix", []),
                    structure,
                ).resize(original.size, Image.Resampling.LANCZOS)

            if CONFIG["semantic"].get("debug_intermediates", False):
                _save_debug_bundle(
                    job_id,
                    degraded,
                    generated,
                    result,
                    {
                        "engine": actual_engine,
                        "fallback_reasons": fallback_reasons,
                        "source_size": list(original.size),
                        "working_size": list(degraded.size),
                        "preset": preset_name,
                        "structure_protection": structure,
                        "elapsed_seconds": round(time.monotonic() - started_at, 3),
                    },
                )
        finally:
            try:
                input_path.unlink(missing_ok=True)
            except OSError:
                pass

    result_bytes = image_to_png_bytes(result)
    output_name = f"{safe_stem}_cleaned.png"
    response = send_file(
        io.BytesIO(result_bytes),
        mimetype="image/png",
        as_attachment=False,
        download_name=output_name,
        max_age=0,
    )
    response.headers["X-GPT-Cleaner-Mode"] = mode
    response.headers["X-GPT-Cleaner-Engine"] = actual_engine
    if fallback_reasons:
        response.headers["X-GPT-Cleaner-Fallback"] = _safe_header(
            "; ".join(fallback_reasons)
        )
    return response


if __name__ == "__main__":
    host = CONFIG.get("web_host", "127.0.0.1")
    port = int(CONFIG.get("web_port", 8787))
    app.run(host=host, port=port, debug=False)
