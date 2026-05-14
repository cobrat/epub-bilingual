from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from ebook_bilingual.llm import (
    fetch_ollama_models,
    OpenAICompatibleTranslator,
    format_terminology,
    is_ollama_base_url,
    load_terminology,
    parse_json_string_array,
    terminology_fingerprint,
)


class StubTranslator(OpenAICompatibleTranslator):
    def __init__(self, responses: list[str], *, retries: int = 2) -> None:
        super().__init__(api_key="test-key", model="test-model", retries=retries)
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

    def test_translate_batch_retries_single_segment_after_bad_json(self) -> None:
        translator = StubTranslator(['["unterminated', '["译文"]'], retries=2)

        self.assertEqual(translator.translate_batch(["source"]), ["译文"])

    def test_translate_batch_accepts_single_json_object_translation(self) -> None:
        translator = StubTranslator(['{"translation": "译文"}'])

        self.assertEqual(translator.translate_batch(["source"]), ["译文"])

    def test_translate_batch_uses_plain_text_single_fallback(self) -> None:
        translator = StubTranslator(['{"bad": []}', '{"bad": []}', "译文"], retries=1)

        self.assertEqual(translator.translate_batch(["source"]), ["译文"])

    def test_fetch_ollama_models_reads_local_tags(self) -> None:
        def fake_urlopen(req: object, timeout: float) -> FakeResponse:
            self.assertEqual(req.full_url, "http://localhost:11434/api/tags")
            self.assertEqual(timeout, 2.0)
            return FakeResponse(b'{"models":[{"name":"qwen2.5:7b"},{"name":"llama3.1:8b"}]}')

        with patch("ebook_bilingual.llm.request.urlopen", fake_urlopen):
            self.assertEqual(fetch_ollama_models("http://localhost:11434/v1"), ["llama3.1:8b", "qwen2.5:7b"])

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
