from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class SemanticProfile:
    name: str
    working_long_edge: int
    steps: int
    cfg_scale: float
    control_scale: float
    cfg_scale_start: float
    control_scale_start: float
    s_churn: int
    s_noise: float
    fusion_weights: tuple[float, float, float, float, float]
    edge_protect: float


PROFILES: dict[str, SemanticProfile] = {
    "light": SemanticProfile(
        name="light",
        working_long_edge=704,
        steps=10,
        cfg_scale=3.0,
        control_scale=1.15,
        cfg_scale_start=2.5,
        control_scale_start=0.85,
        s_churn=2,
        s_noise=1.002,
        # generated contribution: ultra-high, high, mid, low-mid, base
        fusion_weights=(0.56, 0.62, 0.46, 0.16, 0.015),
        edge_protect=0.80,
    ),
    "standard": SemanticProfile(
        name="standard",
        working_long_edge=768,
        steps=14,
        cfg_scale=3.8,
        control_scale=1.08,
        cfg_scale_start=3.2,
        control_scale_start=0.78,
        s_churn=3,
        s_noise=1.003,
        fusion_weights=(0.66, 0.73, 0.58, 0.22, 0.020),
        edge_protect=0.78,
    ),
    "heavy": SemanticProfile(
        name="heavy",
        working_long_edge=832,
        steps=18,
        cfg_scale=4.4,
        control_scale=1.00,
        cfg_scale_start=3.8,
        control_scale_start=0.70,
        s_churn=4,
        s_noise=1.003,
        fusion_weights=(0.72, 0.80, 0.66, 0.28, 0.025),
        edge_protect=0.74,
    ),
}


POSITIVE_PROMPT = (
    "high quality clean coherent image, preserved composition and identity, "
    "clean material shading, coherent surfaces, controlled fine detail, "
    "natural texture appropriate to the subject, clean edges, subtle highlights"
)

NEGATIVE_PROMPT = (
    "oversharpened, noisy, gritty, random microtexture, fake hair strands, tangled strands, "
    "plastic glare, dirty texture, repeated patterns, ringing, halos, waxy blur, smeared detail, "
    "deformed anatomy, altered identity, extra objects, text corruption"
)


def get_profile(name: str) -> SemanticProfile:
    return PROFILES.get(name, PROFILES["standard"])


def _as_rgb_np(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.float32)


def _resize_long_edge(image: Image.Image, long_edge: int) -> Image.Image:
    w, h = image.size
    current = max(w, h)
    if current <= long_edge:
        return image.copy()
    scale = long_edge / float(current)
    target = (max(64, int(round(w * scale))), max(64, int(round(h * scale))))
    # SUPIR is happier with dimensions divisible by 32.
    target = (max(64, target[0] // 32 * 32), max(64, target[1] // 32 * 32))
    return image.resize(target, Image.Resampling.LANCZOS)


def controlled_degrade(image: Image.Image, profile_name: str) -> Image.Image:
    """Intentionally remove unstable GPT micro-detail before semantic restoration.

    The key idea is not to blur the final image. We create a smaller, cleaner semantic
    canvas for SUPIR, then let it regenerate coherent material detail before fusing
    structure back from the original.
    """
    profile = get_profile(profile_name)
    work = _resize_long_edge(image.convert("RGB"), profile.working_long_edge)
    arr = np.asarray(work, dtype=np.uint8)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    luma = lab[:, :, 0]

    # Mild edge-aware cleanup. Downsampling does most of the anti-GPT-texture work;
    # this pass only removes leftover tiny ringing / random speckle.
    smooth = cv2.bilateralFilter(luma, d=5, sigmaColor=12, sigmaSpace=12)
    amount = {"light": 0.16, "standard": 0.22, "heavy": 0.28}.get(profile_name, 0.22)
    lab[:, :, 0] = cv2.addWeighted(luma, 1.0 - amount, smooth, amount, 0)
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return Image.fromarray(out)


def _blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(arr, (0, 0), sigmaX=sigma, sigmaY=sigma, borderType=cv2.BORDER_REFLECT101)


def _bands(arr: np.ndarray) -> list[np.ndarray]:
    """Five frequency bands from micro detail to large structure."""
    g1 = _blur(arr, 0.9)
    g2 = _blur(arr, 2.4)
    g3 = _blur(arr, 6.5)
    g4 = _blur(arr, 18.0)
    return [arr - g1, g1 - g2, g2 - g3, g3 - g4, g4]


def _macro_edge_mask(original: np.ndarray) -> np.ndarray:
    """Protect structural boundaries without preserving every fake micro-edge."""
    gray = cv2.cvtColor(np.clip(original, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    # Blur before gradient so 1px fake hairs and noisy texture are not classified as structure.
    gray = cv2.GaussianBlur(gray, (0, 0), 2.2)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    pos = mag[mag > 0]
    if pos.size == 0:
        mask = np.zeros_like(mag, dtype=np.float32)
    else:
        denom = max(float(np.percentile(pos, 90)), 1e-6)
        mask = np.clip(mag / denom, 0.0, 1.0)
    mask = cv2.GaussianBlur(mask, (0, 0), 1.2)
    return np.repeat(mask[:, :, None], 3, axis=2)


def multiscale_fuse(
    original: Image.Image,
    generated: Image.Image,
    profile_name: str = "standard",
    structure_protection: float = 0.92,
    *,
    force_safe: bool = False,
) -> Image.Image:
    """Fuse SUPIR detail while locking silhouette / facial placement from the input.

    Unlike the V0.2 single Gaussian blend, this explicitly treats large structure,
    material-scale detail and micro-detail differently. Structure protection mainly
    strengthens protection near macro edges. It no longer globally mutes the restoration.
    """
    profile = get_profile(profile_name)
    protection = float(np.clip(structure_protection, 0.0, 1.0))

    orig = original.convert("RGB")
    gen = generated.convert("RGB").resize(orig.size, Image.Resampling.LANCZOS)
    orig_np = _as_rgb_np(orig)
    gen_np = _as_rgb_np(gen)

    ob = _bands(orig_np)
    gb = _bands(gen_np)
    edge = _macro_edge_mask(orig_np)

    weights = np.array(profile.fusion_weights, dtype=np.float32)
    if force_safe:
        # D_structure-safe benchmark: keep the semantic improvement but tighten identity.
        weights *= np.array([0.80, 0.82, 0.76, 0.70, 0.45], dtype=np.float32)

    # Slider changes edge protection much more than overall generated detail.
    edge_strength = float(np.clip(profile.edge_protect * (0.62 + 0.42 * protection), 0.0, 0.96))

    result_bands: list[np.ndarray] = []
    for index, (o_band, g_band) in enumerate(zip(ob, gb)):
        base_w = float(weights[index])
        if index == 4:
            # Global shape / lighting base is essentially original.
            w = base_w * (1.0 - 0.70 * protection)
            result_bands.append(o_band * (1.0 - w) + g_band * w)
            continue

        # Protect strong macro boundaries, but let SUPIR replace non-structural GPT texture.
        spatial_w = base_w * (1.0 - edge * edge_strength)
        # At very high protection, do not kill restoration in flat/material regions.
        floor = base_w * (0.68 if index <= 1 else 0.56)
        spatial_w = np.maximum(spatial_w, floor)
        result_bands.append(o_band * (1.0 - spatial_w) + g_band * spatial_w)

    out = np.clip(sum(result_bands), 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG", optimize=False)
    return buf.getvalue()
