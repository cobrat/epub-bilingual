from __future__ import annotations

import xml.etree.ElementTree as ET
import unittest

from ebook_bilingual.html_bilingual import collect_segments, ensure_xhtml_doctype


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


if __name__ == "__main__":
    unittest.main()
