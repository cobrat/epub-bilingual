from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ebook_bilingual.paths import copy_into_work_dir, default_output_path, prepare_run_paths


class PathTests(unittest.TestCase):
    def test_default_output_path_uses_same_directory(self) -> None:
        self.assertEqual(
            default_output_path(Path("books/tiny.epub")),
            Path("books/tiny.bilingual.epub"),
        )

    def test_default_output_path_handles_missing_suffix(self) -> None:
        self.assertEqual(
            default_output_path(Path("books/tiny")),
            Path("books/tiny.bilingual.epub"),
        )

    def test_prepare_run_paths_copies_input_into_work_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "AI Engineering.epub"
            input_path.write_bytes(b"epub data")
            work_dir = root / "AI Engineering.run"

            run_input, run_output, run_cache = prepare_run_paths(input_path, None, None, work_dir)

            self.assertEqual(run_input, work_dir / "AI Engineering.epub")
            self.assertEqual(run_output, work_dir / "AI Engineering.bilingual.epub")
            self.assertEqual(run_cache, work_dir / "AI Engineering.bilingual.epub.translation-cache.json")
            self.assertEqual(run_input.read_bytes(), b"epub data")

    def test_copy_into_work_dir_copies_terminology(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            terminology_path = root / "terms.csv"
            terminology_path.write_text("source,target\nagent,智能体\n", encoding="utf-8")
            work_dir = root / "book.run"

            run_terminology = copy_into_work_dir(terminology_path, work_dir)

            self.assertEqual(run_terminology, work_dir / "terms.csv")
            self.assertEqual(run_terminology.read_text(encoding="utf-8"), "source,target\nagent,智能体\n")


if __name__ == "__main__":
    unittest.main()
