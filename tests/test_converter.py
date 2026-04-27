from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from ebook_bilingual.epub import convert_epub_to_bilingual


FIXTURE_EPUB = Path(__file__).parents[1] / "books" / "tiny.epub"


class PrefixTranslator:
    def translate_batch(self, texts: list[str]) -> list[str]:
        return [f"译文：{text}" for text in texts]


def write_minimal_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
        )
        zf.writestr(
            "OPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0"
         unique-identifier="bookid">
  <metadata>
    <dc:identifier id="bookid">urn:uuid:00000000-0000-4000-8000-000000000001</dc:identifier>
    <dc:title>Test</dc:title>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-04-27T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  </manifest>
  <spine>
    <itemref idref="chap1"/>
  </spine>
</package>""",
        )
        zf.writestr(
            "OPS/chapter1.xhtml",
            """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <h1>Chapter One</h1>
    <p>Hello world.</p>
    <p>Another paragraph.</p>
  </body>
</html>""",
        )
        zf.writestr(
            "OPS/nav.xhtml",
            """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Table of Contents</title></head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>Table of Contents</h1>
      <ol>
        <li><a href="chapter1.xhtml">Chapter One</a></li>
      </ol>
    </nav>
  </body>
</html>""",
        )


class ConverterTests(unittest.TestCase):
    def test_converts_minimal_epub(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.epub"
            output_path = Path(tmpdir) / "output.epub"
            write_minimal_epub(input_path)

            stats = convert_epub_to_bilingual(input_path, output_path, PrefixTranslator(), batch_size=2)

            self.assertEqual(stats.documents, 1)
            self.assertEqual(stats.translated_segments, 3)
            with zipfile.ZipFile(output_path, "r") as zf:
                opf = zf.read("OPS/content.opf").decode("utf-8")
                chapter = zf.read("OPS/chapter1.xhtml").decode("utf-8")
                self.assertIn("<metadata>", opf)
                self.assertIn("<dc:title>Test</dc:title>", opf)
                self.assertIn("OPS/nav.xhtml", zf.namelist())
                self.assertIn("<!DOCTYPE html>", chapter)
                self.assertIn("<!DOCTYPE html>", zf.read("OPS/nav.xhtml").decode("utf-8"))
                self.assertIn("bilingual-translation", chapter)
                self.assertIn("译文：Hello world.", chapter)
                self.assertEqual(zf.read("mimetype"), b"application/epub+zip")

    def test_limit_counts_only_inserted_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.epub"
            output_path = Path(tmpdir) / "output.epub"
            write_minimal_epub(input_path)

            stats = convert_epub_to_bilingual(
                input_path,
                output_path,
                PrefixTranslator(),
                batch_size=2,
                limit=1,
            )

            self.assertEqual(stats.translated_segments, 1)
            with zipfile.ZipFile(output_path, "r") as zf:
                chapter = zf.read("OPS/chapter1.xhtml").decode("utf-8")
                self.assertIn("译文：Chapter One", chapter)
                self.assertNotIn("译文：Hello world.", chapter)

    def test_converts_fixture_epub(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "tiny.output.epub"

            stats = convert_epub_to_bilingual(FIXTURE_EPUB, output_path, PrefixTranslator(), batch_size=2)

            self.assertEqual(stats.documents, 1)
            self.assertEqual(stats.translated_segments, 3)
            with zipfile.ZipFile(output_path, "r") as zf:
                opf = zf.read("OPS/content.opf").decode("utf-8")
                chapter = zf.read("OPS/chapter1.xhtml").decode("utf-8")
                self.assertIn("<metadata>", opf)
                self.assertIn("<dc:title>Tiny Test</dc:title>", opf)
                self.assertIn("OPS/nav.xhtml", zf.namelist())
                self.assertIn("<!DOCTYPE html>", chapter)
                self.assertIn("<!DOCTYPE html>", zf.read("OPS/nav.xhtml").decode("utf-8"))
                self.assertIn("译文：Tiny Test Book", chapter)
                self.assertIn("译文：The moon rose over the quiet river.", chapter)

    def test_clean_layout_restyles_xhtml_with_custom_style(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.epub"
            output_path = Path(tmpdir) / "output.epub"
            write_minimal_epub(input_path)

            stats = convert_epub_to_bilingual(
                input_path,
                output_path,
                PrefixTranslator(),
                batch_size=2,
                layout="clean",
                style_css="body { font-size: 1.1em; }",
            )

            self.assertEqual(stats.translated_segments, 3)
            with zipfile.ZipFile(output_path, "r") as zf:
                chapter = zf.read("OPS/chapter1.xhtml").decode("utf-8")
                self.assertIn("bilingual-clean-style", chapter)
                self.assertIn("body { font-size: 1.1em; }", chapter)
                self.assertIn('class="bilingual-clean"', chapter)
                self.assertIn('class="bilingual-original"', chapter)
                self.assertIn("译文：Hello world.", chapter)


if __name__ == "__main__":
    unittest.main()
