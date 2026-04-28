from __future__ import annotations

import xml.etree.ElementTree as ET
import unittest

from ebook_bilingual.html_bilingual import bilingualize_xhtml, collect_segments, ensure_xhtml_doctype, restyle_bilingual_xhtml


class HtmlBilingualTests(unittest.TestCase):
    def test_ensure_xhtml_doctype_inserts_after_xml_declaration(self) -> None:
        content = b"<?xml version='1.0' encoding='utf-8'?>\n<html></html>"

        self.assertEqual(
            ensure_xhtml_doctype(content),
            b"<?xml version='1.0' encoding='utf-8'?>\n<!DOCTYPE html>\n<html></html>",
        )

    def test_ensure_xhtml_doctype_does_not_duplicate(self) -> None:
        content = b"<?xml version='1.0'?>\n<!DOCTYPE html>\n<html></html>"

        self.assertEqual(ensure_xhtml_doctype(content), content)

    def test_collect_segments_skips_project_gutenberg_boilerplate(self) -> None:
        root = ET.fromstring(
            """<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <section class="pg-boilerplate pgheader" id="pg-header">
      <h2>Project Gutenberg Header</h2>
      <p>License text that should not be translated.</p>
    </section>
    <section>
      <h1>Alice's Adventures in Wonderland</h1>
      <p>Down the Rabbit-Hole</p>
    </section>
    <section id="pg-footer">
      <p>Project Gutenberg footer.</p>
    </section>
  </body>
</html>"""
        )

        segments = [segment.text for _, segment in collect_segments(root)]

        self.assertEqual(segments, ["Alice's Adventures in Wonderland", "Down the Rabbit-Hole"])

    def test_collect_segments_skips_project_gutenberg_text_not_in_boilerplate(self) -> None:
        root = ET.fromstring(
            """<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h4>There are several editions of this ebook in the Project Gutenberg collection.</h4>
    <h1>ALICE'S ADVENTURES IN WONDERLAND</h1>
  </body>
</html>"""
        )

        segments = [segment.text for _, segment in collect_segments(root)]

        self.assertEqual(segments, ["ALICE'S ADVENTURES IN WONDERLAND"])

    def test_collect_segments_keeps_block_tag(self) -> None:
        root = ET.fromstring(
            """<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>Chapter One</h1>
    <p>Hello world.</p>
  </body>
</html>"""
        )

        segments = [segment for _, segment in collect_segments(root)]

        self.assertEqual(segments[0].tag, "h1")
        self.assertEqual(segments[1].tag, "p")

    def test_collect_segments_protects_inline_code(self) -> None:
        root = ET.fromstring(
            """<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>Call <code>foo_bar()</code> before retrying.</p></body>
</html>"""
        )

        segments = [segment for _, segment in collect_segments(root)]

        self.assertEqual(segments[0].text, "Call __EBOOK_BILINGUAL_KEEP_0__ before retrying.")
        self.assertEqual(segments[0].protected_inlines[0].placeholder, "__EBOOK_BILINGUAL_KEEP_0__")

    def test_collect_segments_skips_code_only_paragraph(self) -> None:
        root = ET.fromstring(
            """<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p><code>foo_bar()</code></p></body>
</html>"""
        )

        self.assertEqual(collect_segments(root), [])

    def test_bilingualize_restores_protected_inline_code(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body><p>Call <code>foo_bar()</code> before retrying.</p></body>
</html>"""

        _, segments = bilingualize_xhtml(content)
        result = bilingualize_xhtml(
            content,
            {segments[0].id: f"Before retrying, call {segments[0].text}"},
        )
        output = result.content.decode("utf-8")

        self.assertIn("<code>foo_bar()</code>", output)
        self.assertNotIn("__EBOOK_BILINGUAL_KEEP_0__", output)

    def test_bilingualize_removes_generic_inline_placeholder_hint(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body><p>Search for libraries.</p></body>
</html>"""

        _, segments = bilingualize_xhtml(content)
        result = bilingualize_xhtml(
            content,
            {segments[0].id: "搜索库。__EBOOK_BILINGUAL_KEEP_N__"},
        )
        output = result.content.decode("utf-8")

        self.assertIn("搜索库。", output)
        self.assertNotIn("__EBOOK_BILINGUAL_KEEP_N__", output)

    def test_bilingualize_removes_unknown_inline_placeholder(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body><p>Search for libraries.</p></body>
</html>"""

        _, segments = bilingualize_xhtml(content)
        result = bilingualize_xhtml(
            content,
            {segments[0].id: "搜索库。__EBOOK_BILINGUAL_KEEP_9__"},
        )
        output = result.content.decode("utf-8")

        self.assertIn("搜索库。", output)
        self.assertNotIn("__EBOOK_BILINGUAL_KEEP_9__", output)

    def test_restyle_can_number_headings(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <h1>Chapter 1</h1>
    <h1>Overview</h1>
    <h2>Details</h2>
    <h1>Second Topic</h1>
  </body>
</html>"""

        output = restyle_bilingual_xhtml(content, number_headings=True).decode("utf-8")

        self.assertIn('class="bilingual-heading-number">1.1 </span>Overview', output)
        self.assertIn('class="bilingual-heading-number">1.1.1 </span>Details', output)
        self.assertIn('class="bilingual-heading-number">1.2 </span>Second Topic', output)

    def test_restyle_skips_front_matter_heading_numbers(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body><h1>Preface</h1></body>
</html>"""

        output = restyle_bilingual_xhtml(
            content,
            number_headings=True,
            document_path="OEBPS/preface01.html",
        ).decode("utf-8")

        self.assertIn("<h1>Preface</h1>", output)
        self.assertNotIn('class="bilingual-heading-number">1 </span>Preface', output)

    def test_restyle_removes_invisible_index_terms(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <p><a contenteditable="false" data-type="indexterm" id="idx1" />Visible text.</p>
  </body>
</html>"""

        output = restyle_bilingual_xhtml(content).decode("utf-8")

        self.assertNotIn("data-type=\"indexterm\"", output)
        self.assertIn("<span id=\"idx1\">", output)
        self.assertIn("Visible text.", output)

    def test_restyle_preserves_note_type_for_block_styling(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <div data-type="note" class="calibre22"><h6>Note</h6><p>Remember this.</p></div>
  </body>
</html>"""

        output = restyle_bilingual_xhtml(content).decode("utf-8")

        self.assertIn('data-type="note"', output)
        self.assertNotIn('class="calibre22"', output)
        self.assertIn("<h6>Note</h6>", output)


if __name__ == "__main__":
    unittest.main()
