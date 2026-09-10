from __future__ import annotations

import io
import math

import cv2
import numpy as np
from PIL import Image


STANDARD_LAPLACIAN_MIX = [0.78, 0.72, 0.58, 0.46, 0.22, 0.03]


def _robust_edge_mask(luma: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(luma, (0, 0), 1.0)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    positive = mag[mag > 0]
    if positive.size == 0:
        return np.zeros_like(mag, dtype=np.float32)
    denom = float(np.percentile(positive, 92))
    if denom < 1e-6:
        denom = 1.0
    return np.clip(mag / denom, 0.0, 1.0) ** 0.75


def preclean_image(
    image: Image.Image,
    preset: dict,
    structure_protection: float,
) -> Image.Image:
    """Suppress luminance micro-texture without inventing new image structure."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    luma = lab[:, :, 0]
    smooth = cv2.bilateralFilter(
        luma,
        d=int(preset["bilateral_d"]),
        sigmaColor=float(preset["bilateral_sigma_color"]),
        sigmaSpace=float(preset["bilateral_sigma_space"]),
    )

    edge = _robust_edge_mask(luma)
    base_strength = float(preset["preclean_strength"])
    strength = float(np.clip(base_strength * (1.08 - 0.34 * structure_protection), 0.04, 0.62))
    edge_preserve = float(preset.get("edge_preserve", 0.9))

    luma_f = luma.astype(np.float32)
    smooth_f = smooth.astype(np.float32)
    high = luma_f - smooth_f
    detail_keep = (1.0 - strength) + strength * edge * edge_preserve
    cleaned_luma = np.clip(smooth_f + high * detail_keep, 0, 255).astype(np.uint8)

    out_lab = lab.copy()
    out_lab[:, :, 0] = cleaned_luma
    return Image.fromarray(cv2.cvtColor(out_lab, cv2.COLOR_LAB2RGB))


def _aligned_reduced_size(width: int, height: int, long_edge: int) -> tuple[int, int]:
    if max(width, height) <= long_edge:
        return width, height

    scale = long_edge / float(max(width, height))
    scaled_width = width * scale
    scaled_height = height * scale

    def align(value: float) -> int:
        return max(64, int(round(value / 64.0)) * 64)

    return align(scaled_width), align(scaled_height)


def controlled_degrade(image: Image.Image, preset: dict) -> Image.Image:
    """Deterministically remove unstable micro-texture before semantic restoration."""
    source = image.convert("RGB")
    target_size = _aligned_reduced_size(
        source.width,
        source.height,
        int(preset.get("semantic_long_edge", 896)),
    )
    if target_size != source.size:
        source = source.resize(target_size, Image.Resampling.LANCZOS)

    rgb = np.asarray(source, dtype=np.uint8)
    sigma = max(0.0, float(preset.get("semantic_blur_sigma", 0.45)))
    if sigma > 0:
        rgb = cv2.GaussianBlur(rgb, (0, 0), sigmaX=sigma, sigmaY=sigma)

    strength = float(np.clip(preset.get("semantic_preclean_strength", 0.28), 0.0, 0.65))
    if strength <= 0:
        return Image.fromarray(rgb)

    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    luma = lab[:, :, 0]
    smooth = cv2.bilateralFilter(luma, d=5, sigmaColor=22, sigmaSpace=22)
    blended = luma.astype(np.float32) * (1.0 - strength) + smooth.astype(np.float32) * strength
    lab[:, :, 0] = np.clip(blended, 0, 255).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def _pyramid(array: np.ndarray, levels: int) -> tuple[list[np.ndarray], list[np.ndarray]]:
    gaussian = [array]
    for _ in range(levels):
        gaussian.append(cv2.pyrDown(gaussian[-1]))

    laplacian = []
    for index in range(levels):
        current = gaussian[index]
        expanded = cv2.pyrUp(
            gaussian[index + 1],
            dstsize=(current.shape[1], current.shape[0]),
        )
        laplacian.append(current - expanded)
    return gaussian, laplacian


def _validated_weights(weights: list[float], levels: int) -> list[float]:
    if len(weights) != levels + 1:
        return STANDARD_LAPLACIAN_MIX.copy()
    values = [float(value) for value in weights]
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
        return STANDARD_LAPLACIAN_MIX.copy()
    return values


def laplacian_fuse(
    original: Image.Image,
    cleaned: Image.Image,
    generated: Image.Image,
    weights: list[float],
    structure_protection: float,
    levels: int = 5,
) -> Image.Image:
    """Blend generated material detail while keeping coarse original structure."""
    target_size = generated.size
    orig = np.asarray(
        original.convert("RGB").resize(target_size, Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    clean = np.asarray(
        cleaned.convert("RGB").resize(target_size, Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    gen = np.asarray(generated.convert("RGB"), dtype=np.float32)

    orig_gaussian, orig_laplacian = _pyramid(orig, levels)
    _, clean_laplacian = _pyramid(clean, levels)
    gen_gaussian, gen_laplacian = _pyramid(gen, levels)

    mixes = _validated_weights(weights, levels)
    sensitivities = [0.10, 0.18, 0.40, 0.62, 0.82, 0.95]
    protection = float(np.clip(structure_protection, 0.0, 1.0))
    effective = [
        mix * (1.0 - protection * sensitivities[index])
        for index, mix in enumerate(mixes)
    ]

    fused_bands = []
    for index in range(levels):
        base_band = clean_laplacian[index] if index < 2 else orig_laplacian[index]
        mix = effective[index]
        fused_bands.append(base_band * (1.0 - mix) + gen_laplacian[index] * mix)

    residual_mix = effective[-1]
    reconstructed = (
        orig_gaussian[-1] * (1.0 - residual_mix)
        + gen_gaussian[-1] * residual_mix
    )
    for index in range(levels - 1, -1, -1):
        band = fused_bands[index]
        reconstructed = cv2.pyrUp(
            reconstructed,
            dstsize=(band.shape[1], band.shape[0]),
        ) + band

    return Image.fromarray(np.clip(reconstructed, 0, 255).astype(np.uint8))


def resize_exact(image: Image.Image, scale: float) -> Image.Image:
    if abs(scale - 1.0) < 1e-6:
        return image
    width, height = image.size
    target = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    return image.resize(target, Image.Resampling.LANCZOS)


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()
