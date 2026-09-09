import unittest

import numpy as np
from PIL import Image

from app.image_ops import controlled_degrade, laplacian_fuse


class ImageOperationTests(unittest.TestCase):
    def test_controlled_degrade_preserves_aspect_and_never_upscales(self):
        wide = Image.new("RGB", (1672, 941), "#808080")
        small = Image.new("RGB", (640, 360), "#808080")
        preset = {"semantic_long_edge": 896, "semantic_blur_sigma": 0.4}

        self.assertEqual(controlled_degrade(wide, preset).size, (896, 512))
        self.assertEqual(controlled_degrade(small, preset).size, (640, 360))

    def test_controlled_degrade_is_deterministic(self):
        pixels = np.arange(768 * 512 * 3, dtype=np.uint32).reshape(512, 768, 3) % 256
        image = Image.fromarray(pixels.astype(np.uint8))
        preset = {"semantic_long_edge": 512, "semantic_blur_sigma": 0.5}

        first = np.asarray(controlled_degrade(image, preset))
        second = np.asarray(controlled_degrade(image, preset))

        self.assertTrue(np.array_equal(first, second))

    def test_controlled_degrade_reduces_unstable_micro_texture(self):
        checker = np.indices((256, 256)).sum(axis=0) % 2
        pixels = np.repeat((checker * 255).astype(np.uint8)[..., None], 3, axis=2)
        image = Image.fromarray(pixels)
        preset = {
            "semantic_long_edge": 896,
            "semantic_blur_sigma": 0.6,
            "semantic_preclean_strength": 0.35,
        }

        result = controlled_degrade(image, preset)

        self.assertLess(float(np.asarray(result).std()), float(pixels.std()) * 0.6)

    def test_laplacian_fuse_returns_original_when_generated_weights_are_zero(self):
        original = Image.new("RGB", (128, 128), "#284664")
        generated = Image.new("RGB", (128, 128), "#dc1e32")

        result = laplacian_fuse(
            original,
            original,
            generated,
            [0, 0, 0, 0, 0, 0],
            1.0,
        )

        delta = np.abs(
            np.asarray(result, dtype=np.int16) - np.asarray(original, dtype=np.int16)
        )
        self.assertLessEqual(int(delta.max()), 1)

    def test_laplacian_fuse_uses_generated_fine_detail(self):
        base = np.full((128, 128, 3), 100, dtype=np.uint8)
        checker = base.copy()
        checker[::2, ::2] = 220
        checker[1::2, 1::2] = 220

        result = laplacian_fuse(
            Image.fromarray(base),
            Image.fromarray(base),
            Image.fromarray(checker),
            [1, 1, 0, 0, 0, 0],
            0.95,
        )

        self.assertGreater(float(np.asarray(result).std()), 20.0)


if __name__ == "__main__":
    unittest.main()
