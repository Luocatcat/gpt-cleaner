import io
import unittest
from unittest.mock import patch

from PIL import Image

from app import server


def png_file(size=(320, 192), color="#7f8290"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    buffer.seek(0)
    return buffer


READY = {
    "supir": {"ready": True, "missing": []},
    "ccsr": {"ready": True, "missing": []},
}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_safe_route_reports_safe_engine(self):
        response = self.client.post(
            "/api/clean",
            data={
                "image": (png_file(), "sample.png"),
                "mode": "safe",
                "scale": "1",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-GPT-Cleaner-Engine"], "safe")
        self.assertEqual(response.headers["X-GPT-Cleaner-Mode"], "safe")

    @patch.object(
        server,
        "run_comfy_engine",
        side_effect=[RuntimeError("SUPIR unavailable"), RuntimeError("CCSR unavailable")],
    )
    @patch.object(server, "get_engine_status", return_value=READY)
    def test_semantic_falls_back_in_order_and_discloses_reason(
        self, _status, run_engine
    ):
        response = self.client.post(
            "/api/clean",
            data={
                "image": (png_file(), "sample.png"),
                "mode": "semantic",
                "scale": "4",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-GPT-Cleaner-Engine"], "safe")
        self.assertIn("SUPIR unavailable", response.headers["X-GPT-Cleaner-Fallback"])
        self.assertIn("CCSR unavailable", response.headers["X-GPT-Cleaner-Fallback"])
        with Image.open(io.BytesIO(response.data)) as result:
            self.assertEqual(result.size, (320, 192))
        self.assertEqual(
            [call.args[0] for call in run_engine.call_args_list],
            ["supir", "ccsr"],
        )

    @patch.object(
        server,
        "run_comfy_engine",
        return_value=Image.new("RGB", (320, 192), "#9a8f86"),
    )
    @patch.object(server, "get_engine_status", return_value=READY)
    def test_semantic_supir_result_is_exact_one_x(self, _status, _run_engine):
        response = self.client.post(
            "/api/clean",
            data={
                "image": (png_file(), "sample.png"),
                "mode": "semantic",
                "scale": "2",
                "structure": "0.94",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-GPT-Cleaner-Engine"], "supir")
        self.assertNotIn("X-GPT-Cleaner-Fallback", response.headers)
        with Image.open(io.BytesIO(response.data)) as result:
            self.assertEqual(result.size, (320, 192))

    @patch.object(server, "get_engine_status", return_value={
        "supir": {"ready": False, "missing": ["supir.safetensors"]},
        "ccsr": {"ready": True, "missing": []},
    })
    def test_health_reports_ccsr_only_semantic_fallback(self, _status):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["safe"])
        self.assertFalse(payload["supir"]["ready"])
        self.assertTrue(payload["ccsr"]["ready"])
        self.assertEqual(payload["semantic_status"], "fallback")


if __name__ == "__main__":
    unittest.main()
