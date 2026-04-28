from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest

from ebook_bilingual.cli import main


class CliTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
