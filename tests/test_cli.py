from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ebook_bilingual.cli import main


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


if __name__ == "__main__":
    unittest.main()
