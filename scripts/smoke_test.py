from __future__ import annotations

import io
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8787"


def main() -> int:
    try:
        health = requests.get(f"{BASE}/api/health", timeout=5)
        health.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL health: {exc}")
        return 1

    image = Image.new("RGB", (256, 256), "#d8d8dc")
    draw = ImageDraw.Draw(image)
    draw.ellipse((54, 38, 202, 186), fill="#25262c")
    draw.rectangle((70, 165, 186, 224), fill="#111216")
    draw.ellipse((92, 92, 115, 115), fill="#b88cff")
    draw.ellipse((141, 92, 164, 115), fill="#6d647d")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)

    files = {"image": ("smoke.png", buf, "image/png")}
    data = {"preset": "light", "structure": "0.95", "scale": "1"}
    try:
        response = requests.post(f"{BASE}/api/clean", files=files, data=data, timeout=900)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        body = getattr(locals().get("response"), "text", "")
        print(f"FAIL clean: {exc}\n{body[:1000]}")
        return 1

    out = Path(__file__).resolve().parents[1] / "runtime" / "smoke_test_output.png"
    out.write_bytes(response.content)
    print(f"PASS: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
