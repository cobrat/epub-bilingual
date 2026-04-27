from __future__ import annotations

import unittest

from ebook_bilingual.pricing import resolve_prices


class PricingTests(unittest.TestCase):
    def test_resolve_prices_uses_known_siliconflow_model_defaults(self) -> None:
        self.assertEqual(
            resolve_prices(
                "Qwen/Qwen3-30B-A3B-Instruct-2507",
                "https://api.siliconflow.cn/v1",
                None,
                None,
            ),
            (0.09, 0.30),
        )


if __name__ == "__main__":
    unittest.main()
