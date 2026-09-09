from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "scripts" / "update_manifest.json"


def apply_manifest(source: Path, target: Path, manifest: dict) -> None:
    local_path = target / "config" / "local.json"
    local_bytes = local_path.read_bytes() if local_path.exists() else None
    for relative in manifest["source_items"]:
        src = source / relative
        dst = target / relative
        if not src.exists():
            continue
        if dst.is_dir():
            shutil.rmtree(dst)
        elif dst.exists():
            dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    if local_bytes is not None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(local_bytes)


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_models = {
        "checkpoints/juggernautXL_v9Rdphoto2Lightning.safetensors",
        "model_patches/SUPIR-v0Q_fp16.safetensors",
    }
    actual_models = {
        f"{entry['directory']}/{entry['filename']}"
        for entry in manifest["semantic_models"]
    }
    assert actual_models == expected_models, actual_models
    assert "runtime" not in manifest["source_items"]
    assert "config/local.json" not in manifest["source_items"]
    assert manifest["runtime_actions"] == [
        "refresh_app_requirements",
        "update_comfy_core_if_supir_missing",
        "download_missing_semantic_models",
        "preserve_legacy_ccsr",
    ]

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        source = base / "source"
        target = base / "target"
        for root in (source, target):
            (root / "app").mkdir(parents=True)
            (root / "web").mkdir(parents=True)
            (root / "scripts").mkdir(parents=True)
            (root / "config").mkdir(parents=True)

        (source / "app" / "version.txt").write_text("v0.3", encoding="utf-8")
        (source / "README.md").write_text("new", encoding="utf-8")
        (target / "app" / "version.txt").write_text("v0.2", encoding="utf-8")
        local_bytes = b"\xef\xbb\xbf{\r\n  \"tile_size\": 192\r\n}\r\n"
        (target / "config" / "local.json").write_bytes(local_bytes)
        runtime_sentinels = [
            target / "runtime" / "models" / "keep.safetensors",
            target / "runtime" / "logs" / "keep.log",
            target / "runtime" / "venv" / "keep.txt",
        ]
        for sentinel in runtime_sentinels:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text("keep", encoding="utf-8")

        apply_manifest(source, target, manifest)

        assert (target / "app" / "version.txt").read_text(encoding="utf-8") == "v0.3"
        assert (target / "README.md").read_text(encoding="utf-8") == "new"
        assert (target / "config" / "local.json").read_bytes() == local_bytes
        assert all(path.read_text(encoding="utf-8") == "keep" for path in runtime_sentinels)

    print("PASS Windows update contract: runtime/config preserved; semantic downloads exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
