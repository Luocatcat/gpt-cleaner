from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8787"
EXPECTED_SIZE = (256, 256)


def make_test_image() -> io.BytesIO:
    image = Image.new("RGB", EXPECTED_SIZE, "#d8d8dc")
    draw = ImageDraw.Draw(image)
    draw.ellipse((54, 38, 202, 186), fill="#25262c")
    draw.rectangle((70, 165, 186, 224), fill="#111216")
    draw.ellipse((92, 92, 115, 115), fill="#b88cff")
    draw.ellipse((141, 92, 164, 115), fill="#6d647d")
    for x in range(70, 187, 4):
        draw.line((x, 168, x + 10, 220), fill="#25262c", width=1)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def run_clean(mode: str, timeout: int) -> requests.Response:
    files = {"image": ("smoke.png", make_test_image(), "image/png")}
    data = {
        "mode": mode,
        "preset": "light",
        "structure": "0.97",
        "scale": "1",
    }
    return requests.post(
        f"{BASE}/api/clean",
        files=files,
        data=data,
        timeout=timeout,
    )


def evaluate_result(
    mode: str,
    status_code: int,
    headers,
    actual_size: tuple[int, int] | None,
    expected_size: tuple[int, int],
) -> tuple[str, str]:
    if status_code != 200:
        return "FAIL", f"{mode} returned HTTP {status_code}"
    if actual_size != expected_size:
        actual = "unknown" if actual_size is None else f"{actual_size[0]}x{actual_size[1]}"
        expected = f"{expected_size[0]}x{expected_size[1]}"
        return "FAIL", f"{mode} returned {actual}; expected exact {expected}"

    engine = headers.get("X-GPT-Cleaner-Engine", "missing")
    fallback = headers.get("X-GPT-Cleaner-Fallback", "")
    if mode == "semantic" and engine != "supir":
        reason = f"; {fallback}" if fallback else ""
        return "PARTIAL", f"semantic used {engine} instead of supir{reason}"

    expected_engine = {"safe": "safe", "semantic": "supir", "ccsr": "ccsr"}[mode]
    if engine != expected_engine:
        return "FAIL", f"{mode} reported engine={engine}; expected {expected_engine}"
    return "PASS", f"{mode} engine={engine}, exact {actual_size[0]}x{actual_size[1]}"


def selected_modes(args) -> list[str]:
    if args.safe:
        return ["safe"]
    if args.semantic:
        return ["semantic"]
    if args.ccsr or args.refine:
        return ["ccsr"]
    return ["safe", "semantic"]


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--safe", action="store_true", help="exercise deterministic safe cleanup")
    group.add_argument("--semantic", action="store_true", help="require native SUPIR semantic restoration")
    group.add_argument("--ccsr", action="store_true", help="exercise the legacy CCSR fallback directly")
    group.add_argument("--refine", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        health = requests.get(f"{BASE}/api/health", timeout=12)
        health.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL health: {exc}")
        return 1

    root = Path(__file__).resolve().parents[1]
    had_partial = False
    for mode in selected_modes(args):
        timeout = 120 if mode == "safe" else 1200
        try:
            response = run_clean(mode, timeout)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {mode}: {exc}")
            return 1

        actual_size = None
        content = response.content
        if response.status_code == 200:
            try:
                with Image.open(io.BytesIO(content)) as output:
                    actual_size = output.size
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {mode}: response is not a readable image: {exc}")
                return 1

        state, message = evaluate_result(
            mode,
            response.status_code,
            response.headers,
            actual_size,
            EXPECTED_SIZE,
        )
        print(f"{state} {message}")
        if state == "FAIL":
            if response.status_code != 200:
                print(response.text[:1000])
            return 1

        output_path = root / "runtime" / f"smoke_test_{mode}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
        print(f"     output: {output_path}")
        had_partial = had_partial or state == "PARTIAL"

    return 2 if had_partial else 0


if __name__ == "__main__":
    sys.exit(main())
