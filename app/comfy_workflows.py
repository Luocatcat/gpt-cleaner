from __future__ import annotations

import math


SUPIR_NODE_TYPES = {
    "LoadImage",
    "CheckpointLoaderSimple",
    "ModelPatchLoader",
    "SUPIRApply",
    "CLIPTextEncodeSDXL",
    "EmptyLatentImage",
    "KSamplerSelect",
    "BasicScheduler",
    "SamplerCustom",
    "VAEDecodeTiled",
    "SaveImage",
}
CCSR_NODE_TYPES = {"LoadImage", "DownloadAndLoadCCSRModel", "CCSR_Upscale", "SaveImage"}


def _finite_float(value, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) else fallback


def build_supir_prompt(
    input_name: str,
    width: int,
    height: int,
    config: dict,
) -> dict:
    width = max(64, int(width))
    height = max(64, int(height))
    positive = str(config.get("positive_prompt", "high quality, clean coherent material detail"))
    negative = str(config.get("negative_prompt", "dirty texture, deformation, tile seams"))
    clip_inputs = {
        "clip": ["2", 1],
        "width": width,
        "height": height,
        "crop_w": 0,
        "crop_h": 0,
        "target_width": width,
        "target_height": height,
    }

    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": input_name},
        },
        "2": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": config["checkpoint"]},
        },
        "3": {
            "class_type": "ModelPatchLoader",
            "inputs": {"name": config["model_patch"]},
        },
        "4": {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {**clip_inputs, "text_g": positive, "text_l": positive},
        },
        "5": {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {**clip_inputs, "text_g": negative, "text_l": negative},
        },
        "6": {
            "class_type": "SUPIRApply",
            "inputs": {
                "model": ["2", 0],
                "model_patch": ["3", 0],
                "vae": ["2", 2],
                "image": ["1", 0],
                "strength_start": _finite_float(config.get("strength_start"), 1.0),
                "strength_end": _finite_float(config.get("strength_end"), 0.9),
                "restore_cfg": _finite_float(config.get("restore_cfg"), 4.0),
                "restore_cfg_s_tmin": _finite_float(config.get("restore_cfg_s_tmin"), 0.05),
            },
        },
        "7": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": config.get("sampler", "dpmpp_2m_sde")},
        },
        "8": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["6", 0],
                "scheduler": config.get("scheduler", "sgm_uniform"),
                "steps": int(config.get("steps", 10)),
                "denoise": _finite_float(config.get("denoise"), 1.0),
            },
        },
        "9": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "10": {
            "class_type": "SamplerCustom",
            "inputs": {
                "model": ["6", 0],
                "add_noise": True,
                "noise_seed": int(config.get("seed", 123)),
                "cfg": _finite_float(config.get("cfg"), 1.5),
                "positive": ["4", 0],
                "negative": ["5", 0],
                "sampler": ["7", 0],
                "sigmas": ["8", 0],
                "latent_image": ["9", 0],
            },
        },
        "12": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["10", 0],
                "vae": ["2", 2],
                "tile_size": int(config.get("vae_tile_decode", 512)),
                "overlap": int(config.get("vae_overlap", 64)),
                "temporal_size": 64,
                "temporal_overlap": 8,
            },
        },
        "13": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["12", 0],
                "filename_prefix": "gpt_cleaner_supir",
            },
        },
    }


def build_ccsr_prompt(
    input_name: str,
    preset: dict,
    structure_protection: float,
    config: dict,
) -> dict:
    protection = max(0.0, min(1.0, _finite_float(structure_protection, 0.92)))
    t_max = _finite_float(preset.get("t_max"), 0.54) - protection * 0.035
    t_min = _finite_float(preset.get("t_min"), 0.40) + protection * 0.018
    if t_min >= t_max:
        t_min = max(0.05, t_max - 0.06)

    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": input_name},
        },
        "2": {
            "class_type": "DownloadAndLoadCCSRModel",
            "inputs": {"model": config.get("model", "real-world_ccsr-fp16.safetensors")},
        },
        "3": {
            "class_type": "CCSR_Upscale",
            "inputs": {
                "ccsr_model": ["2", 0],
                "image": ["1", 0],
                "resize_method": "lanczos",
                "scale_by": 1.0,
                "steps": int(preset.get("steps", 12)),
                "t_max": round(t_max, 4),
                "t_min": round(t_min, 4),
                "sampling_method": config.get("sampling_method", "ccsr_tiled_vae_gaussian_weights"),
                "tile_size": int(config.get("tile_size", 256)),
                "tile_stride": int(config.get("tile_stride", 128)),
                "vae_tile_size_encode": int(config.get("vae_tile_encode", 512)),
                "vae_tile_size_decode": int(config.get("vae_tile_decode", 512)),
                "color_fix_type": config.get("color_fix", "wavelet"),
                "keep_model_loaded": False,
                "seed": 123,
            },
        },
        "4": {
            "class_type": "SaveImage",
            "inputs": {"images": ["3", 0], "filename_prefix": "gpt_cleaner_ccsr"},
        },
    }


def classify_engines(
    object_info: dict,
    model_files: set[str],
    config: dict,
) -> dict:
    available_nodes = set(object_info)
    semantic = config["semantic"]
    ccsr = config["ccsr"]

    supir_missing = [
        f"node:{name}" for name in sorted(SUPIR_NODE_TYPES - available_nodes)
    ]
    supir_missing.extend(
        name
        for name in (semantic["checkpoint"], semantic["model_patch"])
        if name not in model_files
    )

    ccsr_missing = [
        f"node:{name}" for name in sorted(CCSR_NODE_TYPES - available_nodes)
    ]
    if ccsr["model"] not in model_files:
        ccsr_missing.append(ccsr["model"])

    return {
        "supir": {"ready": not supir_missing, "missing": supir_missing},
        "ccsr": {"ready": not ccsr_missing, "missing": ccsr_missing},
    }
