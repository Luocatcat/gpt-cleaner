import unittest

from scripts.smoke_test import evaluate_result


class SmokeResultTests(unittest.TestCase):
    def test_semantic_supir_is_pass(self):
        state, message = evaluate_result(
            "semantic",
            200,
            {"X-GPT-Cleaner-Engine": "supir"},
            (256, 256),
            (256, 256),
        )
        self.assertEqual(state, "PASS")
        self.assertIn("supir", message)

    def test_semantic_fallback_is_partial(self):
        state, message = evaluate_result(
            "semantic",
            200,
            {
                "X-GPT-Cleaner-Engine": "ccsr",
                "X-GPT-Cleaner-Fallback": "supir unavailable",
            },
            (256, 256),
            (256, 256),
        )
        self.assertEqual(state, "PARTIAL")
        self.assertIn("supir unavailable", message)

    def test_wrong_output_dimensions_are_fail(self):
        state, message = evaluate_result(
            "safe",
            200,
            {"X-GPT-Cleaner-Engine": "safe"},
            (512, 512),
            (256, 256),
        )
        self.assertEqual(state, "FAIL")
        self.assertIn("512x512", message)


if __name__ == "__main__":
    unittest.main()
