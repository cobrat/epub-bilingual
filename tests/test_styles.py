from __future__ import annotations

from pathlib import Path
import unittest

from ebook_bilingual.styles import CLEAN_BILINGUAL_CSS


class StylesTests(unittest.TestCase):
    def test_eink_style_matches_clean_default(self) -> None:
        path = Path(__file__).parents[1] / "styles" / "eink-10.3.css"

        self.assertEqual(path.read_text(encoding="utf-8").strip(), CLEAN_BILINGUAL_CSS)

    def test_eink_style_justifies_body_text(self) -> None:
        path = Path(__file__).parents[1] / "styles" / "eink-10.3.css"
        css = path.read_text(encoding="utf-8")

        self.assertIn("text-align: justify;", css)
        self.assertIn("hyphens: auto;", css)
        self.assertIn("text-decoration: none;", css)

    def test_eink_style_formats_notes_as_blocks(self) -> None:
        path = Path(__file__).parents[1] / "styles" / "eink-10.3.css"
        css = path.read_text(encoding="utf-8")

        self.assertIn('[data-type="note"]', css)
        self.assertIn('[data-type="tip"]', css)
        self.assertIn("border-left: 0.3em solid #555;", css)
        self.assertIn("page-break-inside: avoid;", css)

    def test_eink_style_controls_figures_and_table_captions(self) -> None:
        path = Path(__file__).parents[1] / "styles" / "eink-10.3.css"
        css = path.read_text(encoding="utf-8")

        self.assertIn("figure img,", css)
        self.assertIn("width: 100%;", css)
        self.assertIn("figure h6.bilingual-original", css)
        self.assertIn("caption {", css)
        self.assertIn("font-size: 1.2em;", css)


if __name__ == "__main__":
    unittest.main()
