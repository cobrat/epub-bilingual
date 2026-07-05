from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from ebook_bilingual.llm import (
    CachedTranslator,
    fetch_ollama_models,
    OpenAICompatibleTranslator,
    TranslationCache,
    format_terminology,
    is_ollama_base_url,
    is_probably_untranslated,
    load_terminology,
    parse_json_string_array,
    terminology_fingerprint,
)
from ebook_bilingual.profiling import ProfileMetrics


class StubTranslator(OpenAICompatibleTranslator):
    def __init__(self, responses: list[str], *, retries: int = 2, profile_metrics: ProfileMetrics | None = None) -> None:
        super().__init__(api_key="test-key", model="test-model", retries=retries, profile_metrics=profile_metrics)
        self.responses = responses

    def _post_json(self, payload: dict) -> str:
        if not self.responses:
            raise AssertionError("No stub responses left")
        return self.responses.pop(0)


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.data


class PrefixTranslator:
    def translate_batch(self, texts: list[str]) -> list[str]:
        return [f"译文：{text}" for text in texts]


class CountingTranslator:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate_batch(self, texts: list[str]) -> list[str]:
        self.calls.append(list(texts))
        return ["提示工程的最佳实践是什么？" for _ in texts]


class LlmTests(unittest.TestCase):
    def test_parse_json_string_array_accepts_code_fence(self) -> None:
        self.assertEqual(parse_json_string_array('```json\n["一", "二"]\n```'), ["一", "二"])

    def test_parse_json_string_array_removes_thinking_block(self) -> None:
        self.assertEqual(
            parse_json_string_array("<think>I should translate carefully.</think>\n[\"译文\"]"),
            ["译文"],
        )

    def test_parse_json_string_array_allows_raw_newline_in_string(self) -> None:
        self.assertEqual(parse_json_string_array('["第一行\n第二行"]'), ["第一行\n第二行"])

    def test_parse_json_string_array_accepts_common_object_wrapper(self) -> None:
        self.assertEqual(parse_json_string_array('{"translations": ["一", "二"]}'), ["一", "二"])

    def test_translate_batch_falls_back_to_single_segments_after_bad_batch_json(self) -> None:
        translator = StubTranslator(['["unterminated', '["第一条"]', '["第二条"]'])

        self.assertEqual(translator.translate_batch(["one", "two"]), ["第一条", "第二条"])

    def test_translate_batch_records_fallback_metric(self) -> None:
        metrics = ProfileMetrics()
        translator = StubTranslator(['["unterminated', '["第一条"]', '["第二条"]'], profile_metrics=metrics)

        self.assertEqual(translator.translate_batch(["one", "two"]), ["第一条", "第二条"])
        self.assertEqual(metrics.to_dict()["llm"]["fallbacks"], 1)

    def test_translate_batch_retries_when_chinese_target_response_is_still_english(self) -> None:
        metrics = ProfileMetrics()
        translator = StubTranslator(
            ['["What are the best practices for prompt engineering?"]', '["提示工程的最佳实践是什么？"]'],
            profile_metrics=metrics,
        )

        self.assertEqual(
            translator.translate_batch(["What are the best practices for prompt engineering?"]),
            ["提示工程的最佳实践是什么？"],
        )
        self.assertEqual(metrics.to_dict()["llm"]["fallbacks"], 1)

    def test_translate_batch_retries_single_segment_after_bad_json(self) -> None:
        translator = StubTranslator(['["unterminated', '["译文"]'], retries=2)

        self.assertEqual(translator.translate_batch(["source"]), ["译文"])

    def test_translate_batch_accepts_single_json_object_translation(self) -> None:
        translator = StubTranslator(['{"translation": "译文"}'])

        self.assertEqual(translator.translate_batch(["source"]), ["译文"])

    def test_translate_batch_uses_plain_text_single_fallback(self) -> None:
        translator = StubTranslator(['{"bad": []}', '{"bad": []}', "译文"], retries=1)

        self.assertEqual(translator.translate_batch(["source"]), ["译文"])

    def test_chat_completions_url_preserves_query_params(self) -> None:
        translator = OpenAICompatibleTranslator(
            api_key="test-key",
            model="deployment-name",
            base_url="https://example.openai.azure.com/openai/deployments/deployment-name?api-version=2024-10-21",
        )

        self.assertEqual(
            translator.chat_completions_url,
            "https://example.openai.azure.com/openai/deployments/deployment-name/chat/completions?api-version=2024-10-21",
        )

    def test_full_chat_completions_url_is_not_appended(self) -> None:
        translator = OpenAICompatibleTranslator(
            api_key="test-key",
            model="deployment-name",
            base_url="https://example.openai.azure.com/openai/deployments/deployment-name/chat/completions?api-version=2024-10-21",
        )

        self.assertEqual(
            translator.chat_completions_url,
            "https://example.openai.azure.com/openai/deployments/deployment-name/chat/completions?api-version=2024-10-21",
        )

    def test_kimi_k2_payload_omits_temperature_and_disables_thinking(self) -> None:
        translator = OpenAICompatibleTranslator(
            api_key="test-key",
            model="kimi-k2.6",
            base_url="https://api.moonshot.cn/v1",
        )

        payload = translator._translation_payload(["hello"])

        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["thinking"], {"type": "disabled"})

    def test_standard_payload_keeps_temperature(self) -> None:
        translator = OpenAICompatibleTranslator(
            api_key="test-key",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
        )

        self.assertEqual(translator._translation_payload(["hello"])["temperature"], 0.2)

    def test_fetch_ollama_models_reads_local_tags(self) -> None:
        def fake_urlopen(req: object, timeout: float) -> FakeResponse:
            self.assertEqual(req.full_url, "http://localhost:11434/api/tags")
            self.assertEqual(timeout, 2.0)
            return FakeResponse(b'{"models":[{"name":"qwen2.5:7b"},{"name":"llama3.1:8b"}]}')

        with patch("ebook_bilingual.llm.request.urlopen", fake_urlopen):
            self.assertEqual(fetch_ollama_models("http://localhost:11434/v1"), ["llama3.1:8b", "qwen2.5:7b"])

    def test_openai_translator_records_raw_request_and_retry_metrics(self) -> None:
        metrics = ProfileMetrics()
        translator = OpenAICompatibleTranslator(
            api_key="test-key",
            model="test-model",
            retries=2,
            profile_metrics=metrics,
        )
        calls = 0

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("temporary timeout")
            return FakeResponse('{"choices":[{"message":{"content":"[\\"译文\\"]"}}]}'.encode("utf-8"))

        with patch("ebook_bilingual.llm.request.urlopen", fake_urlopen):
            self.assertEqual(translator.translate_batch(["source"]), ["译文"])

        payload = metrics.to_dict()["llm"]
        self.assertEqual(payload["raw_requests"], 2)
        self.assertEqual(payload["retries"], 1)

    def test_cached_translator_can_delay_cache_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache = TranslationCache.load(cache_path)
            translator = CachedTranslator(PrefixTranslator(), cache, "model", "English", "Chinese", autosave=False)

            self.assertEqual(translator.translate_batch(["Hello."]), ["译文：Hello."])
            self.assertFalse(cache_path.exists())

            cache.save()
            self.assertTrue(cache_path.exists())
            self.assertIn("译文：Hello.", cache_path.read_text(encoding="utf-8"))

    def test_cached_translator_ignores_english_cache_for_chinese_target(self) -> None:
        source = "What are the best practices for prompt engineering?"
        raw = CountingTranslator()
        cache = TranslationCache(path=None, values={})
        translator = CachedTranslator(raw, cache, "model", "English", "Simplified Chinese", autosave=False)
        cache.set(translator.cache_key_for_text(source), source)

        self.assertEqual(translator.cached_count([source]), 0)
        self.assertEqual(translator.cached_batch([source]), [None])
        self.assertEqual(translator.translate_batch([source]), ["提示工程的最佳实践是什么？"])
        self.assertEqual(raw.calls, [[source]])

    def test_probably_untranslated_allows_short_proper_nouns(self) -> None:
        self.assertFalse(is_probably_untranslated("OpenAI", "OpenAI", "Simplified Chinese"))
        self.assertFalse(is_probably_untranslated("Llama 3-70B", "Llama 3-70B", "Simplified Chinese"))
        self.assertFalse(is_probably_untranslated("LAMBADA (PPL)", "LAMBADA (PPL)", "Simplified Chinese"))

    def test_probably_untranslated_flags_english_sentence_for_chinese_target(self) -> None:
        self.assertTrue(
            is_probably_untranslated(
                "What are the best practices for prompt engineering?",
                "What are the best practices for prompt engineering?",
                "Simplified Chinese",
            )
        )

    def test_is_ollama_base_url_matches_default_port(self) -> None:
        self.assertTrue(is_ollama_base_url("http://localhost:11434/v1"))
        self.assertFalse(is_ollama_base_url("https://api.openai.com/v1"))

    def test_load_terminology_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "terms.csv"
            path.write_text(
                "source,target,note\nfoundation model,基础模型,AI term\nagent,智能体,\n",
                encoding="utf-8",
            )

            entries = load_terminology(path)

            self.assertEqual(len(entries), 2)
            self.assertIn("foundation model => 基础模型", format_terminology(entries))
            self.assertTrue(terminology_fingerprint(entries))


if __name__ == "__main__":
    unittest.main()
