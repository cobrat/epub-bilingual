from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from ebook_bilingual.config import load_env_file


class ConfigTests(unittest.TestCase):
    def test_load_env_file_sets_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                """
# comment
LLM_API_KEY=test-key
export LLM_MODEL="Qwen/Qwen3-30B-A3B-Instruct-2507"
LLM_TARGET_LANG='Simplified Chinese'
""",
                encoding="utf-8",
            )
            old_values = {key: os.environ.get(key) for key in ("LLM_API_KEY", "LLM_MODEL", "LLM_TARGET_LANG")}
            try:
                for key in old_values:
                    os.environ.pop(key, None)

                load_env_file(env_path)

                self.assertEqual(os.environ["LLM_API_KEY"], "test-key")
                self.assertEqual(os.environ["LLM_MODEL"], "Qwen/Qwen3-30B-A3B-Instruct-2507")
                self.assertEqual(os.environ["LLM_TARGET_LANG"], "Simplified Chinese")
            finally:
                for key, value in old_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_load_env_file_does_not_override_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("LLM_API_KEY=file-key\n", encoding="utf-8")
            old_value = os.environ.get("LLM_API_KEY")
            try:
                os.environ["LLM_API_KEY"] = "shell-key"
                load_env_file(env_path)
                self.assertEqual(os.environ["LLM_API_KEY"], "shell-key")
            finally:
                if old_value is None:
                    os.environ.pop("LLM_API_KEY", None)
                else:
                    os.environ["LLM_API_KEY"] = old_value
