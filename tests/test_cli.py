from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ebook_bilingual.cli import build_parser, main, print_progress, run_from_args
from ebook_bilingual.epub import ConversionStats, TranslationProgress


FIXTURE_EPUB = Path(__file__).parents[1] / "books" / "tiny.epub"


def write_bad_xhtml_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
        )
        zf.writestr(
            "OPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest><item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chap1"/></spine>
</package>""",
        )
        zf.writestr("OPS/chapter1.xhtml", "<html><body><p>Broken")


class CliTests(unittest.TestCase):
    def test_requires_input_without_interactive(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            main([])

        self.assertEqual(ctx.exception.code, 2)

    def test_interactive_does_not_require_positional_input(self) -> None:
        with patch("ebook_bilingual.interactive.run_interactive", return_value=0) as run_interactive:
            self.assertEqual(main(["--interactive"]), 0)

        run_interactive.assert_called_once()

    def test_rejects_non_positive_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.epub"
            input_path.write_bytes(b"not used")

            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
                main([str(input_path), "--timeout", "0"])

        self.assertEqual(ctx.exception.code, 2)

    def test_rejects_non_positive_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.epub"
            input_path.write_bytes(b"not used")

            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
                main([str(input_path), "--retries", "0"])

        self.assertEqual(ctx.exception.code, 2)

    def test_rejects_negative_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.epub"
            input_path.write_bytes(b"not used")

            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
                main([str(input_path), "--limit", "-1"])

        self.assertEqual(ctx.exception.code, 2)

    def test_progress_output_shows_segments_batches_percent_and_document(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            print_progress(
                TranslationProgress(
                    completed_segments=1,
                    total_segments=2,
                    completed_batches=1,
                    total_batches=2,
                    current_document="OPS/chapter.xhtml",
                )
            )

        self.assertIn("Progress: 1/2 segments | batches 1/2 | 50.0% | OPS/chapter.xhtml", output.getvalue())

    def test_quiet_disables_progress_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.epub"
            input_path.write_bytes(b"not used")
            parser = build_parser()
            args = parser.parse_args([str(input_path), "--mock", "--quiet"])

            with redirect_stdout(io.StringIO()), patch(
                "ebook_bilingual.app.convert_epub_to_bilingual",
                return_value=ConversionStats(documents=1, translated_segments=1),
            ) as convert:
                self.assertEqual(run_from_args(args, parser), 0)

        self.assertIsNone(convert.call_args.kwargs["progress_callback"])

    def test_ollama_base_url_does_not_require_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.epub"
            input_path.write_bytes(b"not used")
            parser = build_parser()
            args = parser.parse_args([str(input_path), "--base-url", "http://localhost:11434/v1", "--model", "qwen2.5:7b"])
            args.api_key = None

            with redirect_stdout(io.StringIO()), patch(
                "ebook_bilingual.app.convert_epub_to_bilingual",
                return_value=ConversionStats(documents=1, translated_segments=1),
            ):
                self.assertEqual(run_from_args(args, parser), 0)

    def test_clean_layout_loads_styles_directory_css_when_flag_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_cwd = os.getcwd()
            try:
                os.chdir(root)

                input_path = root / "input.epub"
                input_path.write_bytes(b"not used")
                css_dir = root / "styles"
                css_dir.mkdir()
                marker = """:root { --discovered: 7; }\n"""
                (css_dir / "theme.css").write_text(marker, encoding="utf-8")

                parser = build_parser()
                args = parser.parse_args([str(input_path), "--mock", "--quiet", "--layout", "clean"])

                with redirect_stdout(io.StringIO()), patch(
                    "ebook_bilingual.app.convert_epub_to_bilingual",
                    return_value=ConversionStats(documents=1, translated_segments=1),
                ) as convert:
                    self.assertEqual(run_from_args(args, parser), 0)

                self.assertEqual(convert.call_args.kwargs["layout"], "clean")
                self.assertEqual(convert.call_args.kwargs["style_css"], marker)
            finally:
                os.chdir(old_cwd)

    def test_fail_on_skipped_returns_nonzero_for_malformed_xhtml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "bad.epub"
            output_path = Path(tmpdir) / "bad.out.epub"
            write_bad_xhtml_epub(input_path)

            with redirect_stdout(io.StringIO()):
                code = main([str(input_path), str(output_path), "--mock", "--fail-on-skipped"])

        self.assertEqual(code, 1)

    def test_verbose_skipped_output_does_not_include_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "bad.epub"
            output_path = Path(tmpdir) / "bad.out.epub"
            write_bad_xhtml_epub(input_path)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(
                    [
                        str(input_path),
                        str(output_path),
                        "--mock",
                        "--verbose",
                        "--api-key",
                        "secret-key-value",
                    ]
                )

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("Skipped documents:", output)
        self.assertIn("collect_segments", output)
        self.assertNotIn("secret-key-value", output)

    def test_verbose_dry_run_skipped_output_does_not_include_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "bad.epub"
            write_bad_xhtml_epub(input_path)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main([str(input_path), "--dry-run", "--verbose", "--api-key", "secret-key-value"])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("Skipped documents:", output)
        self.assertIn("collect_segments", output)
        self.assertNotIn("secret-key-value", output)

    def test_tiny_epub_dry_run_cli_smoke(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            code = main([str(FIXTURE_EPUB), "--dry-run"])

        self.assertEqual(code, 0)
        self.assertIn("Dry run", stdout.getvalue())
        self.assertIn("Segments: 3", stdout.getvalue())

    def test_tiny_epub_mock_preserve_cli_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "tiny.preserve.epub"

            with redirect_stdout(io.StringIO()):
                code = main([str(FIXTURE_EPUB), str(output_path), "--mock", "--quiet"])

            self.assertEqual(code, 0)
            with zipfile.ZipFile(output_path, "r") as zf:
                chapter = zf.read("OPS/chapter1.xhtml").decode("utf-8")
            self.assertIn("[译文占位] Tiny Test Book", chapter)

    def test_tiny_epub_mock_clean_numbered_cli_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "tiny.clean.epub"

            with redirect_stdout(io.StringIO()):
                code = main(
                    [
                        str(FIXTURE_EPUB),
                        str(output_path),
                        "--mock",
                        "--quiet",
                        "--layout",
                        "clean",
                        "--number-headings",
                    ]
                )

            self.assertEqual(code, 0)
            with zipfile.ZipFile(output_path, "r") as zf:
                chapter = zf.read("OPS/chapter1.xhtml").decode("utf-8")
            self.assertIn("bilingual-clean-style", chapter)
            self.assertIn("bilingual-heading-number", chapter)


if __name__ == "__main__":
    unittest.main()
