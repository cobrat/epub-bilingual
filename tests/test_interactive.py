from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from ebook_bilingual.interactive import (
    WizardConfig,
    build_conversion_args,
    redact_args,
    render_status_box,
    run_interactive,
    suggest_epub_path,
    update_env_file,
)


def seed_args(
    input_path: Path | None = None,
    *,
    model: str = "test-model",
    api_key: str = "",
    mock: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        input=input_path,
        output=None,
        model=model,
        api_key=api_key,
        base_url="https://api.example.com/v1",
        source_lang="English",
        target_lang="Simplified Chinese",
        layout="preserve",
        style_css=None,
        number_headings=False,
        dry_run=False,
        mock=mock,
        batch_size=8,
        concurrency=1,
        min_chars=2,
        timeout=120,
        retries=3,
        cache=None,
        work_dir=None,
        limit=None,
        terminology=None,
        quiet=False,
        input_price_per_1m=None,
        output_price_per_1m=None,
        price_currency="USD",
        output_token_ratio=1.15,
    )


def sample_config(api_key: str = "secret") -> WizardConfig:
    return WizardConfig(
        input_path=Path("books/book.epub"),
        output_path=None,
        model="test-model",
        api_key=api_key,
        base_url="https://api.example.com/v1",
        source_lang="English",
        target_lang="Simplified Chinese",
        layout="clean",
        style_css=Path("styles/eink-10.3.css"),
        number_headings=True,
        mock=False,
        batch_size=4,
        concurrency=2,
        min_chars=2,
        timeout=120,
        retries=3,
        cache_path=None,
        work_dir=None,
        limit=10,
        terminology_path=None,
        quiet=True,
        input_price_per_1m=None,
        output_price_per_1m=None,
        price_currency="USD",
        output_token_ratio=1.15,
    )


class InteractiveTests(unittest.TestCase):
    def test_suggest_epub_path_skips_generated_bilingual_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            books = root / "books"
            books.mkdir()
            (books / "book.bilingual.epub").write_bytes(b"generated")
            (books / "book.epub").write_bytes(b"source")

            self.assertEqual(suggest_epub_path(root), Path("books/book.epub"))

    def test_status_box_shows_settings_without_api_key_value(self) -> None:
        text = "\n".join(render_status_box(sample_config()))

        self.assertIn("输入 EPUB: books/book.epub", text)
        self.assertIn("翻译模型: test-model", text)
        self.assertIn("API Key: 已配置", text)
        self.assertIn("布局: clean", text)
        self.assertIn("批大小: 4", text)
        self.assertNotIn("secret", text)

    def test_language_menu_explicitly_switches_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "8",  # language menu
                    "2",  # English
                    "0",  # exit
                ]
            )
            outputs: list[str] = []

            code = run_interactive(
                seed_args(input_path, api_key="secret"),
                execute=lambda _: 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )
            output_text = "\n".join(outputs)

        self.assertEqual(code, 0)
        self.assertIn("常用操作:", output_text)
        self.assertIn("1. 开始转换 EPUB", output_text)
        self.assertIn("2. 选择 EPUB 文件", output_text)
        self.assertIn("8. 界面语言 / Language: 中文", output_text)
        self.assertIn("界面语言 / Interface Language", output_text)
        self.assertIn("Interface language set to English.", output_text)
        self.assertIn("Common tasks:", output_text)
        self.assertIn("1. Start EPUB conversion", output_text)
        self.assertIn("2. Select EPUB file", output_text)
        self.assertIn("8. Language / 界面语言: English", output_text)

    def test_redact_args_hides_api_key_value(self) -> None:
        redacted = redact_args(["book.epub", "--api-key", "secret", "--model", "test-model"])

        self.assertEqual(redacted, ["book.epub", "--api-key", "***", "--model", "test-model"])

    def test_build_conversion_args_can_force_dry_run(self) -> None:
        args = build_conversion_args(sample_config(), dry_run=True)

        self.assertIn("--dry-run", args)
        self.assertIn("--number-headings", args)
        self.assertIn("--quiet", args)
        self.assertEqual(args[args.index("--batch-size") + 1], "4")
        self.assertEqual(args[args.index("--limit") + 1], "10")

    def test_start_conversion_runs_dry_run_before_real_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "1",  # start conversion
                    "y",  # continue after dry-run
                ]
            )
            calls: list[list[str]] = []

            code = run_interactive(
                seed_args(input_path, api_key="secret"),
                execute=lambda args: calls.append(args) or 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=lambda _: None,
                cwd=root,
            )

        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        self.assertIn("--dry-run", calls[0])
        self.assertNotIn("--dry-run", calls[1])

    def test_main_menu_can_enter_model_menu_and_update_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "3",  # model menu
                    "2",  # model
                    "new-model",
                    "0",  # back
                    "0",  # exit
                ]
            )
            outputs: list[str] = []

            code = run_interactive(
                seed_args(input_path, api_key="secret"),
                execute=lambda _: 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )
            output_text = "\n".join(outputs)

        self.assertEqual(code, 0)
        self.assertIn("翻译模型: new-model", output_text)

    def test_output_menu_can_set_custom_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "4",  # output menu
                    "1",  # set output path
                    "custom.epub",
                    "0",  # back
                    "0",  # exit
                ]
            )
            outputs: list[str] = []

            code = run_interactive(
                seed_args(input_path, api_key="secret"),
                execute=lambda _: 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )
            output_text = "\n".join(outputs)

        self.assertEqual(code, 0)
        self.assertIn("设置输出位置", output_text)
        self.assertIn("输出 EPUB: custom.epub", output_text)

    def test_ebook_menu_can_select_detected_book_by_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            books = root / "books"
            books.mkdir()
            (books / "a.epub").write_bytes(b"a")
            (books / "b.epub").write_bytes(b"b")
            (books / "b.bilingual.epub").write_bytes(b"generated")
            answers = iter(
                [
                    "2",  # ebook menu
                    "2",  # books/b.epub
                    "0",  # back
                    "1",  # start conversion
                    "n",  # stop after dry-run
                    "0",  # exit
                ]
            )
            calls: list[list[str]] = []
            outputs: list[str] = []

            code = run_interactive(
                seed_args(None, api_key="secret"),
                execute=lambda args: calls.append(args) or 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "books/b.epub")
        self.assertIn("books/ 下可选 EPUB:", outputs)
        self.assertIn("  1. books/a.epub", outputs)
        self.assertIn("  2. books/b.epub", outputs)

    def test_ebook_menu_reprompts_for_invalid_manual_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes.txt").write_text("not epub", encoding="utf-8")
            (root / "book.epub").write_bytes(b"epub")
            answers = iter(
                [
                    "2",  # ebook menu
                    "1",  # manual path because no books are listed
                    "",
                    "missing.epub",
                    "notes.txt",
                    "book.epub",
                    "0",  # back
                    "0",  # exit
                ]
            )
            outputs: list[str] = []

            code = run_interactive(
                seed_args(None, api_key="secret"),
                execute=lambda _: 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )

        self.assertEqual(code, 0)
        self.assertIn("请输入 EPUB 路径。", outputs)
        self.assertIn("电子书文件不存在: missing.epub", outputs)
        self.assertIn("电子书必须是 .epub 文件。", outputs)

    def test_start_conversion_validates_missing_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(["1", "0"])
            calls: list[list[str]] = []
            outputs: list[str] = []

            code = run_interactive(
                seed_args(input_path, api_key=""),
                execute=lambda args: calls.append(args) or 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertIn("除非启用模拟翻译器，否则必须配置 API Key。", "\n".join(outputs))

    def test_run_interactive_never_prints_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(["1", "n", "0"])
            outputs: list[str] = []

            run_interactive(
                seed_args(input_path, api_key="secret"),
                execute=lambda _: 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )
            output_text = "\n".join(outputs)

        self.assertNotIn("secret", output_text)
        self.assertIn("API Key: 已配置", output_text)
        self.assertIn("***", output_text)

    def test_run_interactive_handles_keyboard_interrupt_cleanly(self) -> None:
        outputs: list[str] = []
        calls: list[list[str]] = []

        def interrupt(_: str) -> str:
            raise KeyboardInterrupt

        code = run_interactive(
            seed_args(None),
            execute=lambda args: calls.append(args) or 0,
            input_func=interrupt,
            getpass_func=lambda _: "",
            print_func=outputs.append,
        )

        self.assertEqual(code, 130)
        self.assertEqual(calls, [])
        self.assertIn("已取消。", outputs)

    def test_run_interactive_handles_eof_cleanly(self) -> None:
        outputs: list[str] = []
        calls: list[list[str]] = []

        def eof(_: str) -> str:
            raise EOFError

        code = run_interactive(
            seed_args(None),
            execute=lambda args: calls.append(args) or 0,
            input_func=eof,
            getpass_func=lambda _: "",
            print_func=outputs.append,
        )

        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertIn("已取消。", outputs)

    def test_run_interactive_does_not_save_api_key_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "7",  # save env
                    "y",  # save defaults
                    "n",  # do not save API key
                    "0",  # exit
                ]
            )

            run_interactive(
                seed_args(input_path, api_key="secret"),
                execute=lambda _: 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=lambda _: None,
                cwd=root,
            )
            env_text = (root / ".env").read_text(encoding="utf-8")

        self.assertIn("LLM_MODEL=test-model", env_text)
        self.assertNotIn("LLM_API_KEY", env_text)
        self.assertNotIn("secret", env_text)

    def test_update_env_file_replaces_existing_values_and_appends_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("LLM_MODEL=old\nOTHER=value\n", encoding="utf-8")

            update_env_file(env_path, {"LLM_MODEL": "new", "LLM_BASE_URL": "https://api.example.com/v1"})

            self.assertEqual(
                env_path.read_text(encoding="utf-8"),
                "LLM_MODEL=new\nOTHER=value\nLLM_BASE_URL=https://api.example.com/v1\n",
            )


if __name__ == "__main__":
    unittest.main()
