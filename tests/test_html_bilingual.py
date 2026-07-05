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

    def test_collect_segments_skips_container_blocks_with_nested_blocks(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <dl>
      <dt>Term</dt>
      <dd><p>Definition text.</p></dd>
    </dl>
    <figcaption><p>Caption text.</p></figcaption>
  </body>
</html>"""

        _, segments = bilingualize_xhtml(content)
        result = bilingualize_xhtml(content, {segment.id: f"译文：{segment.text}" for segment in segments})
        output = result.content.decode("utf-8")

        self.assertEqual([segment.text for segment in segments], ["Term", "Definition text.", "Caption text."])
        self.assertEqual(output.count("译文：Definition text."), 1)
        self.assertEqual(output.count("译文：Caption text."), 1)

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

    def test_bilingualize_batch_insert_preserves_mixed_html_structures(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <p>Call <code>foo_bar()</code> before retrying.</p>
    <p>Formula <math><mi>x</mi></math> stays inline.</p>
    <figcaption>Figure caption.</figcaption>
    <dl><dt>Term</dt><dd>Definition text.</dd></dl>
    <table><tr><td>Table cell stays untouched.</td></tr></table>
    <pre><code>do_not_translate()</code></pre>
  </body>
</html>"""

        _, segments = bilingualize_xhtml(content)
        result = bilingualize_xhtml(content, {segment.id: f"译文：{segment.text}" for segment in segments})
        output = result.content.decode("utf-8")

        self.assertIn("<code>foo_bar()</code>", output)
        self.assertIn("<math>", output)
        self.assertIn("译文：Figure caption.", output)
        self.assertIn("译文：Term", output)
        self.assertIn("译文：Definition text.", output)
        self.assertIn("Table cell stays untouched.", output)
        self.assertIn("译文：Table cell stays untouched.", output)
        self.assertIn("<pre>", output)
        self.assertIn("do_not_translate()", output)
        self.assertNotIn("__EBOOK_BILINGUAL_KEEP_0__", output)
        self.assertEqual(output.count('class="bilingual-translation"'), len(segments))

    def test_bilingualize_translates_table_cells_and_list_items_inside_their_container(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <table>
      <caption><span>Table 2-6.</span> Examples from <a href="https://example.com">InstructGPT</a>.</caption>
      <tr><th>Input (context)</th><td><span>Interpreters and translators</span></td></tr>
    </table>
    <ul><li><a href="https://example.com">InstructGPT</a></li></ul>
  </body>
</html>"""

        _, segments = bilingualize_xhtml(content)
        result = bilingualize_xhtml(content, {segment.id: f"译文：{segment.text}" for segment in segments})
        output = result.content.decode("utf-8")

        self.assertEqual([segment.tag for segment in segments], ["caption", "th", "td", "li"])
        self.assertIn("<th", output)
        self.assertIn("<td", output)
        self.assertIn("<li", output)
        self.assertIn("译文：Table 2-6. Examples from InstructGPT.", output)
        self.assertIn("译文：Input (context)", output)
        self.assertIn("译文：Interpreters and translators", output)
        self.assertIn("译文：InstructGPT", output)
        self.assertNotIn("<tr><th>Input (context)</th><p", output)
        self.assertNotIn("</li><p", output)

    def test_bilingualize_translates_nested_index_list_item_prefixes(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <ul>
      <li><span data-type="index-term">agents</span>, <a href="ch06.html">Agents</a>
        <ul>
          <li><span data-type="index-term">planning agents</span>, <a href="ch06.html#p">Planning</a></li>
        </ul>
      </li>
    </ul>
  </body>
</html>"""

        _, segments = bilingualize_xhtml(content)
        result = bilingualize_xhtml(content, {segment.id: f"译文：{segment.text}" for segment in segments})
        output = result.content.decode("utf-8")

        self.assertEqual([segment.text for segment in segments], ["agents, Agents", "planning agents, Planning"])
        self.assertIn("译文：agents, Agents", output)
        self.assertIn("译文：planning agents, Planning", output)
        self.assertLess(output.index("译文：agents, Agents"), output.index("planning agents"))

    def test_restyle_can_number_headings(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <h1>Chapter 1</h1>
    <h1>Overview</h1>
    <h2>Details</h2>
    <h3>Implementation</h3>
    <h4>Step</h4>
    <h5>Substep</h5>
    <h6>Fine point</h6>
    <h1>Second Topic</h1>
  </body>
</html>"""

        output = restyle_bilingual_xhtml(content, number_headings=True).decode("utf-8")

        self.assertIn('class="bilingual-heading bilingual-heading-level-1"', output)
        self.assertIn('class="bilingual-heading-marker bilingual-heading-marker-level-1">■</span>', output)
        self.assertIn('class="bilingual-heading-number bilingual-heading-number-level-1">1.1</span> Overview', output)
        self.assertIn('class="bilingual-heading-number bilingual-heading-number-level-2">1.1.1</span> Details', output)
        self.assertIn('class="bilingual-heading-number bilingual-heading-number-level-3">1.1.1.1</span> Implementation', output)
        self.assertIn('class="bilingual-heading-number bilingual-heading-number-level-4">1.1.1.1.1</span> Step', output)
        self.assertIn('class="bilingual-heading-number bilingual-heading-number-level-5">1.1.1.1.1.1</span> Substep', output)
        self.assertIn('class="bilingual-heading-marker bilingual-heading-marker-level-6">·</span>', output)
        self.assertIn('class="bilingual-heading-number bilingual-heading-number-level-6">1.1.1.1.1.2</span> Fine point', output)
        self.assertIn('class="bilingual-heading-number bilingual-heading-number-level-1">1.2</span> Second Topic', output)

    def test_restyle_does_not_number_figure_headings(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <h1>Chapter 1</h1>
    <h2>Topic</h2>
    <figure>
      <h6>Figure 1. Architecture overview</h6>
    </figure>
  </body>
</html>"""

        output = restyle_bilingual_xhtml(content, number_headings=True).decode("utf-8")

        self.assertIn("<h6>Figure 1. Architecture overview</h6>", output)
        self.assertNotIn('<h6 class="bilingual-heading', output)

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
