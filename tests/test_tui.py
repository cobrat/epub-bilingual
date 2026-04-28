from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ebook_bilingual.tui import TuiConfig, build_cli_args, command_preview, default_config, validate_config


class TuiTests(unittest.TestCase):
    def test_build_cli_args_includes_clean_layout_options(self) -> None:
        config = TuiConfig(
            input_path="books/input.epub",
            output_path="books/output.epub",
            model="test-model",
            api_key="secret",
            base_url="https://api.example.com/v1",
            layout="clean",
            style_css_path="styles/eink-10.3.css",
            number_headings=True,
            dry_run=False,
            mock=True,
            limit=10,
        )

        args = build_cli_args(config)

        self.assertEqual(args[:2], ["books/input.epub", "books/output.epub"])
        self.assertIn("--style-css", args)
        self.assertIn("styles/eink-10.3.css", args)
        self.assertIn("--number-headings", args)
        self.assertIn("--mock", args)
        self.assertNotIn("--dry-run", args)
        self.assertEqual(args[args.index("--limit") + 1], "10")

    def test_build_cli_args_omits_clean_only_options_for_preserve_layout(self) -> None:
        config = TuiConfig(
            input_path="books/input.epub",
            layout="preserve",
            style_css_path="styles/eink-10.3.css",
            number_headings=True,
        )

        args = build_cli_args(config)

        self.assertNotIn("--style-css", args)
        self.assertNotIn("--number-headings", args)

    def test_command_preview_redacts_api_key(self) -> None:
        preview = command_preview(TuiConfig(input_path="books/input.epub", api_key="secret"))

        self.assertIn("--api-key", preview)
        self.assertIn("***", preview)
        self.assertNotIn("secret", preview)

    def test_validate_config_accepts_safe_dry_run_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "input.epub"
            style_path = root / "style.css"
            input_path.write_bytes(b"epub")
            style_path.write_text("body {}", encoding="utf-8")
            config = TuiConfig(input_path="input.epub", style_css_path="style.css", dry_run=True)

            self.assertIsNone(validate_config(config, root))

    def test_validate_config_rejects_missing_model_for_real_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "input.epub"
            input_path.write_bytes(b"epub")
            config = TuiConfig(
                input_path="input.epub",
                style_css_path="",
                dry_run=False,
                mock=False,
                model="",
                api_key="secret",
            )

            with patch.dict(os.environ, {"LLM_MODEL": "", "LLM_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
                self.assertEqual(validate_config(config, root), "Model is required unless dry run or mock is enabled.")

    def test_default_config_suggests_first_non_bilingual_epub(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            books = root / "books"
            books.mkdir()
            (books / "book.bilingual.epub").write_bytes(b"generated")
            (books / "book.epub").write_bytes(b"source")

            config = default_config(root)

            self.assertEqual(config.input_path, "books/book.epub")


if __name__ == "__main__":
    unittest.main()
