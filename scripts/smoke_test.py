from __future__ import annotations

import argparse
import base64
import io
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8787"
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"


def make_test_image() -> io.BytesIO:
    image = Image.new("RGB", (512, 320), "#e5e5e8")
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 35, 250, 205), fill="#26272d")
    draw.rectangle((112, 175, 218, 288), fill="#f0d9d4")
    draw.ellipse((125, 105, 157, 137), fill="#ad82ef")
    draw.ellipse((180, 105, 212, 137), fill="#5e596c")
    draw.rectangle((315, 70, 420, 250), fill="#f0d9d4")
    # Artificial high-frequency junk for the cleaner to remove/rebuild.
    for x in range(90, 240, 6):
        draw.line((x, 55, x + 25, 180), fill="#4d4d55", width=1)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf


def check_health(require_supir: bool) -> bool:
    try:
        response = requests.get(f"{BASE}/api/health", timeout=8)
        response.raise_for_status()
        data = response.json()
        print("health:", data)
        if require_supir and not data.get("supir"):
            print("FAIL: SUPIR engine is not ready")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL health: {exc}")
        return False


def run_clean(mode: str) -> int:
    if not check_health(require_supir=(mode == "semantic")):
        return 1
    files = {"image": ("smoke.png", make_test_image(), "image/png")}
    data = {"mode": mode, "preset": "light", "structure": "0.96"}
    try:
        response = requests.post(f"{BASE}/api/clean", files=files, data=data, timeout=1800)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        body = getattr(locals().get("response"), "text", "")
        print(f"FAIL clean: {exc}\n{body[:1600]}")
        return 1
    out = RUNTIME / f"smoke_{mode}.png"
    out.write_bytes(response.content)
    print(f"PASS {mode}: {out}")
    return 0


def run_benchmark() -> int:
    if not check_health(require_supir=True):
        return 1
    files = {"image": ("smoke.png", make_test_image(), "image/png")}
    try:
        response = requests.post(f"{BASE}/api/benchmark", files=files, timeout=3600)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        body = getattr(locals().get("response"), "text", "")
        print(f"FAIL benchmark: {exc}\n{body[:1600]}")
        return 1
    out_dir = RUNTIME / "smoke_benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data_url in data.get("images", {}).items():
        payload = data_url.split(",", 1)[1]
        (out_dir / f"{name}.png").write_bytes(base64.b64decode(payload))
    print(f"PASS benchmark: {out_dir}")
    print("debug:", data.get("debug_dir"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--semantic", action="store_true", help="run one SUPIR semantic pass")
    group.add_argument("--benchmark", action="store_true", help="run the 4-way V0.3 benchmark")
    group.add_argument("--safe", action="store_true", help="run deterministic safe fallback")
    args = parser.parse_args()
    if args.benchmark:
        return run_benchmark()
    if args.semantic:
        return run_clean("semantic")
    return run_clean("safe")


if __name__ == "__main__":
    sys.exit(main())
