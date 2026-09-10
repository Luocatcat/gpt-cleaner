import json
import tempfile
import unittest
from pathlib import Path

from app.configuration import deep_merge, load_config


class ConfigurationTests(unittest.TestCase):
    def test_deep_merge_keeps_new_nested_defaults(self):
        merged = deep_merge(
            {
                "semantic": {"model": "supir.safetensors", "steps": 10},
                "default_mode": "semantic",
            },
            {"semantic": {"steps": 8}},
        )

        self.assertEqual(
            merged,
            {
                "semantic": {"model": "supir.safetensors", "steps": 8},
                "default_mode": "semantic",
            },
        )

    def test_load_config_layers_old_local_file_over_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "default.json").write_text(
                json.dumps(
                    {
                        "default_mode": "semantic",
                        "semantic": {"steps": 10, "cfg": 1.5},
                    }
                ),
                encoding="utf-8",
            )
            (root / "local.json").write_text(
                json.dumps({"semantic": {"steps": 8}}), encoding="utf-8"
            )

            self.assertEqual(
                load_config(root),
                {
                    "default_mode": "semantic",
                    "semantic": {"steps": 8, "cfg": 1.5},
                },
            )

    def test_load_config_migrates_legacy_ccsr_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "default.json").write_text(
                json.dumps(
                    {
                        "ccsr": {
                            "model": "ccsr.safetensors",
                            "tile_size": 256,
                            "tile_stride": 128,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "local.json").write_text(
                json.dumps({"tile_size": 192, "tile_stride": 96}),
                encoding="utf-8",
            )

            loaded = load_config(root)

            self.assertEqual(loaded["ccsr"]["tile_size"], 192)
            self.assertEqual(loaded["ccsr"]["tile_stride"], 96)


if __name__ == "__main__":
    unittest.main()
