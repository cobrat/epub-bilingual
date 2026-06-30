from __future__ import annotations

import unittest

from ebook_bilingual.providers import (
    provider_id_for_base_url,
    provider_template_by_id,
    resolve_prices,
)


class ProviderTests(unittest.TestCase):
    def test_registry_resolves_siliconflow_prices(self) -> None:
        self.assertEqual(
            resolve_prices(
                "Qwen/Qwen3-30B-A3B-Instruct-2507",
                "https://api.siliconflow.cn/v1",
                None,
                None,
            ),
            (0.09, 0.30),
        )

    def test_registry_recognizes_ollama_and_recommended_batch_size(self) -> None:
        self.assertEqual(provider_id_for_base_url("http://localhost:11434/v1"), "ollama")
        template = provider_template_by_id("ollama")

        self.assertIsNotNone(template)
        assert template is not None
        self.assertFalse(template.api_key_required)
        self.assertEqual(template.recommended_batch_size, 2)

    def test_registry_resolves_additional_openai_compatible_providers(self) -> None:
        cases = {
            "https://generativelanguage.googleapis.com/v1beta/openai/": "gemini",
            "https://openrouter.ai/api/v1": "openrouter",
            "https://api.groq.com/openai/v1": "groq",
            "https://api.mistral.ai/v1": "mistral",
            "https://api.together.ai/v1": "together",
            "https://api.moonshot.cn/v1": "kimi",
            "https://api.perplexity.ai": "perplexity",
            "https://book-translator.openai.azure.com/openai/v1": "azure-openai",
        }

        for base_url, provider_id in cases.items():
            with self.subTest(base_url=base_url):
                self.assertEqual(provider_id_for_base_url(base_url), provider_id)
                self.assertIsNotNone(provider_template_by_id(provider_id))

    def test_registry_resolves_groq_prices(self) -> None:
        self.assertEqual(
            resolve_prices(
                "llama-3.3-70b-versatile",
                "https://api.groq.com/openai/v1",
                None,
                None,
            ),
            (0.59, 0.79),
        )


if __name__ == "__main__":
    unittest.main()
