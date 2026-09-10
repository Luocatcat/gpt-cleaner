from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


LEGACY_CCSR_KEYS = {
    "model",
    "tile_size",
    "tile_stride",
    "vae_tile_encode",
    "vae_tile_decode",
    "sampling_method",
    "color_fix",
}


def deep_merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _normalize_local_override(local: dict) -> dict:
    normalized = deepcopy(local)
    legacy_ccsr = {
        key: normalized[key]
        for key in LEGACY_CCSR_KEYS
        if key in normalized
    }
    if legacy_ccsr:
        normalized["ccsr"] = deep_merge(legacy_ccsr, normalized.get("ccsr", {}))
    return normalized


def load_config(config_dir: Path) -> dict:
    with (config_dir / "default.json").open("r", encoding="utf-8-sig") as handle:
        defaults = json.load(handle)

    local_path = config_dir / "local.json"
    if not local_path.exists():
        return defaults

    with local_path.open("r", encoding="utf-8-sig") as handle:
        local = json.load(handle)
    return deep_merge(defaults, _normalize_local_override(local))
