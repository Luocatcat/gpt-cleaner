import unittest

from app.comfy_workflows import (
    build_ccsr_prompt,
    build_supir_prompt,
    classify_engines,
)


SEMANTIC = {
    "checkpoint": "juggernaut.safetensors",
    "model_patch": "supir.safetensors",
    "positive_prompt": "clean material",
    "negative_prompt": "dirty texture",
    "sampler": "dpmpp_2m_sde",
    "scheduler": "sgm_uniform",
    "steps": 10,
    "cfg": 1.5,
    "strength_start": 1.0,
    "strength_end": 0.9,
    "restore_cfg": 4.0,
    "restore_cfg_s_tmin": 0.05,
    "denoise": 1.0,
    "seed": 123,
    "vae_tile_decode": 512,
    "vae_overlap": 64,
}

SUPIR_NODES = {
    "LoadImage",
    "CheckpointLoaderSimple",
    "ModelPatchLoader",
    "SUPIRApply",
    "CLIPTextEncodeSDXL",
    "EmptyLatentImage",
    "KSamplerSelect",
    "BasicScheduler",
    "SamplerCustom",
    "VAEDecodeTiled",
    "SaveImage",
}


class ComfyWorkflowTests(unittest.TestCase):
    def test_supir_prompt_wires_core_nodes_and_exact_working_dimensions(self):
        graph = build_supir_prompt("degraded.png", 896, 512, SEMANTIC)

        self.assertEqual(
            graph["1"],
            {"class_type": "LoadImage", "inputs": {"image": "degraded.png"}},
        )
        self.assertEqual(graph["6"]["class_type"], "SUPIRApply")
        self.assertEqual(graph["6"]["inputs"]["image"], ["1", 0])
        self.assertEqual(graph["9"]["inputs"]["width"], 896)
        self.assertEqual(graph["9"]["inputs"]["height"], 512)
        self.assertEqual(graph["12"]["class_type"], "VAEDecodeTiled")
        self.assertEqual(graph["13"]["inputs"]["images"], ["12", 0])
        self.assertEqual(
            {node["class_type"] for node in graph.values()},
            SUPIR_NODES,
        )

    def test_engine_classification_requires_nodes_and_model_files(self):
        config = {
            "semantic": {
                "checkpoint": "juggernaut.safetensors",
                "model_patch": "supir.safetensors",
            },
            "ccsr": {"model": "ccsr.safetensors"},
        }
        object_info = {name: {} for name in SUPIR_NODES}
        object_info["CCSR_Upscale"] = {}
        object_info["DownloadAndLoadCCSRModel"] = {}

        status = classify_engines(
            object_info,
            {"juggernaut.safetensors", "supir.safetensors"},
            config,
        )

        self.assertTrue(status["supir"]["ready"])
        self.assertFalse(status["ccsr"]["ready"])
        self.assertEqual(status["ccsr"]["missing"], ["ccsr.safetensors"])

    def test_ccsr_prompt_keeps_generation_at_one_x(self):
        preset = {"steps": 12, "t_max": 0.54, "t_min": 0.40}
        ccsr = {
            "model": "ccsr.safetensors",
            "tile_size": 256,
            "tile_stride": 128,
            "vae_tile_encode": 512,
            "vae_tile_decode": 512,
            "sampling_method": "ccsr_tiled_vae_gaussian_weights",
            "color_fix": "wavelet",
        }

        graph = build_ccsr_prompt("degraded.png", preset, 0.97, ccsr)

        self.assertEqual(graph["3"]["inputs"]["scale_by"], 1.0)
        self.assertEqual(graph["3"]["inputs"]["tile_size"], 256)
        self.assertEqual(graph["4"]["inputs"]["images"], ["3", 0])


if __name__ == "__main__":
    unittest.main()
