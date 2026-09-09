from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8787"


def make_test_image() -> io.BytesIO:
    image = Image.new("RGB", (256, 256), "#d8d8dc")
    draw = ImageDraw.Draw(image)
    draw.ellipse((54, 38, 202, 186), fill="#25262c")
    draw.rectangle((70, 165, 186, 224), fill="#111216")
    draw.ellipse((92, 92, 115, 115), fill="#b88cff")
    draw.ellipse((141, 92, 164, 115), fill="#6d647d")
    # Add deliberately noisy high-frequency stripes to exercise the cleaner.
    for x in range(70, 187, 4):
        draw.line((x, 168, x + 10, 220), fill="#25262c", width=1)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf


def run_clean(mode: str, timeout: int) -> bytes:
    buf = make_test_image()
    files = {"image": ("smoke.png", buf, "image/png")}
    data = {
        "mode": mode,
        "preset": "light",
        "structure": "0.97",
        "scale": "1",
    }
    response = requests.post(f"{BASE}/api/clean", files=files, data=data, timeout=timeout)
    response.raise_for_status()
    return response.content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refine", action="store_true", help="also exercise the optional ComfyUI/CCSR route")
    args = parser.parse_args()

    try:
        health = requests.get(f"{BASE}/api/health", timeout=5)
        health.raise_for_status()
        health_json = health.json()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL health: {exc}")
        return 1

    root = Path(__file__).resolve().parents[1]

    try:
        safe_bytes = run_clean("safe", 120)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL safe clean: {exc}")
        return 1

    safe_out = root / "runtime" / "smoke_test_safe.png"
    safe_out.write_bytes(safe_bytes)
    print(f"PASS safe: {safe_out}")

    if args.refine:
        if not health_json.get("comfy"):
            print("FAIL refine requested but /api/health reports comfy=false")
            return 1
        try:
            refine_bytes = run_clean("refine", 900)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL refine: {exc}")
            return 1
        refine_out = root / "runtime" / "smoke_test_refine.png"
        refine_out.write_bytes(refine_bytes)
        print(f"PASS refine: {refine_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
