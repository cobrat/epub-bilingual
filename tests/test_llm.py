from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from ebook_bilingual.llm import (
    OpenAICompatibleTranslator,
    format_terminology,
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
