from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from rich.console import Console

from ebook_bilingual.interactive import (
    WizardConfig,
    build_conversion_args,
    initial_config,
    redact_args,
    render_status_panel,
    render_status_box,
    run_interactive,
    save_wizard_snapshot,
    suggest_epub_path,
    update_env_file,
    wizard_config_from_seed,
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
    def test_initial_config_prefers_styles_eink_for_clean_without_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"")
            marker = ":root {}\n"
            styles = root / "styles"
            styles.mkdir()
            (styles / "other.css").write_text("{}", encoding="utf-8")
            (styles / "eink-10.3.css").write_text(marker, encoding="utf-8")
            seed = seed_args(input_path=input_path)
            seed.layout = "clean"
            cfg = initial_config(seed, root)
            self.assertEqual(cfg.layout, "clean")
            self.assertEqual(cfg.style_css, styles / "eink-10.3.css")

    def test_initial_config_keeps_explicit_style_when_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"")
            styles = root / "styles"
            styles.mkdir()
            (styles / "eink-10.3.css").write_text("e{}", encoding="utf-8")
            custom = styles / "custom.css"
            custom.write_text("c{}", encoding="utf-8")
            seed = seed_args(input_path=input_path)
            seed.layout = "clean"
            seed.style_css = custom
            cfg = initial_config(seed, root)
            self.assertEqual(cfg.style_css, custom)

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

        self.assertIn("状态: 可以开始 - 开始转换会先 dry-run", text)
        self.assertIn("输入 EPUB: books/book.epub", text)
        self.assertIn("翻译模型: test-model", text)
        self.assertIn("API Key: 已配置", text)
        self.assertIn("布局: clean", text)
        self.assertIn("批大小: 4", text)
        self.assertNotIn("\x1b[", text)
        self.assertNotIn("secret", text)

    def test_status_box_shows_missing_start_requirements(self) -> None:
        text = "\n".join(render_status_box(sample_config(api_key="")))

        self.assertIn("状态: 还需配置", text)
        self.assertIn("API Key: 缺失", text)

    def test_status_panel_uses_rich_color_without_api_key_value(self) -> None:
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, color_system="standard", width=100, highlight=False)

        console.print(render_status_panel(sample_config()))
        text = output.getvalue()

        self.assertIn("\x1b[", text)
        self.assertIn("books/book.epub", text)
        self.assertIn("API Key", text)
        self.assertIn("已配置", text)
        self.assertNotIn("secret", text)

    def test_language_menu_explicitly_switches_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "more",
                    "language",
                    "en",
                    "exit",
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
        self.assertIn("输入数字选择；也可输入选项名称。", output_text)
        self.assertIn("1. 开始转换 EPUB（先 dry-run）", output_text)
        self.assertIn("2. 选择电子书", output_text)
        self.assertIn("更多…", output_text)
        self.assertIn("更多选项（高级、环境与语言）", output_text)
        self.assertIn("界面语言 / Interface Language", output_text)
        self.assertIn("Interface language set to English.", output_text)
        self.assertIn("2. EPUB", output_text)
        self.assertIn("翻译与模型", output_text)
        self.assertIn("4. More…", output_text)
        self.assertIn("What do you want to do next?", output_text)
        self.assertIn("1. Start EPUB conversion (dry-run first)", output_text)
        self.assertIn("Translation & model", output_text)

    def test_wizard_restores_prior_session_model_from_snapshot_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            snap_cfg = replace(
                wizard_config_from_seed(seed_args(input_path, api_key="secret"), root),
                model="from-last-session-model",
                base_url="https://persisted.example/v1",
            )
            save_wizard_snapshot(snap_cfg, root)
            outs: list[str] = []

            run_interactive(
                seed_args(input_path),
                execute=lambda _: 0,
                input_func=lambda _: "exit",
                getpass_func=lambda _: "",
                print_func=outs.append,
                cwd=root,
            )
            text = "\n".join(outs)

            self.assertIn("from-last-session-model", text)
            self.assertIn("已载入上次向导会话的配置。", text)
            snap = root / ".ebook-bilingual" / "wizard-last.json"
            self.assertTrue(snap.exists())
            self.assertIn("persisted.example", snap.read_text(encoding="utf-8"))

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
                    "model",
                    "model",
                    "new-model",
                    "back",
                    "exit",
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

    def test_model_menu_can_apply_provider_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "model",
                    "provider",
                    "provider:deepseek",
                    "back",
                    "exit",
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
        self.assertIn("已应用模型厂商模板: DeepSeek", output_text)
        self.assertIn("翻译模型: deepseek-chat", output_text)

    def test_model_menu_can_apply_ollama_provider_and_select_fetched_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "model",
                    "provider",
                    "provider:ollama",
                    "model:qwen2.5:7b",
                    "back",
                    "start",
                    "n",
                    "exit",
                ]
            )
            calls: list[list[str]] = []
            outputs: list[str] = []

            with patch("ebook_bilingual.interactive.fetch_ollama_models", return_value=["llama3.1:8b", "qwen2.5:7b"]):
                code = run_interactive(
                    seed_args(input_path, api_key=""),
                    execute=lambda args: calls.append(args) or 0,
                    input_func=lambda _: next(answers),
                    getpass_func=lambda _: "",
                    print_func=outputs.append,
                    cwd=root,
                )
            output_text = "\n".join(outputs)

        self.assertEqual(code, 0)
        self.assertIn("已应用模型厂商模板: Ollama 本地", output_text)
        self.assertIn("翻译模型: qwen2.5:7b", output_text)
        self.assertIn("API Key: 不需要", output_text)
        self.assertEqual(calls[0][calls[0].index("--base-url") + 1], "http://localhost:11434/v1")
        self.assertEqual(calls[0][calls[0].index("--model") + 1], "qwen2.5:7b")
        self.assertNotIn("--api-key", calls[0])

    def test_ollama_provider_uses_changed_base_url_for_model_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            remote_base_url = "http://ollama.example.test:8080/v1"
            answers = iter(
                [
                    "model",
                    "provider",
                    "provider:ollama",
                    "base_url",
                    remote_base_url,
                    "model",
                    "back",
                    "exit",
                ]
            )
            outputs: list[str] = []
            fetched_urls: list[str] = []

            def fetch_models(base_url: str) -> list[str]:
                fetched_urls.append(base_url)
                return ["local-model" if len(fetched_urls) == 1 else "remote-model"]

            with patch("ebook_bilingual.interactive.fetch_ollama_models", side_effect=fetch_models):
                code = run_interactive(
                    seed_args(input_path, api_key=""),
                    execute=lambda _: 0,
                    input_func=lambda _: next(answers),
                    getpass_func=lambda _: "",
                    print_func=outputs.append,
                    cwd=root,
                )
            output_text = "\n".join(outputs)

        self.assertEqual(code, 0)
        self.assertEqual(fetched_urls, ["http://localhost:11434/v1", remote_base_url])
        self.assertIn("选择模型厂商模板: Ollama 本地", output_text)
        self.assertIn(f"Base URL: {remote_base_url}", output_text)
        self.assertIn("翻译模型: remote-model", output_text)
        self.assertIn("API Key: 不需要", output_text)

    def test_advanced_menu_can_set_conversion_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "more",
                    "advanced",
                    "batch_size",
                    "4",
                    "concurrency",
                    "2",
                    "cache",
                    "cache.json",
                    "work_dir",
                    "run",
                    "quiet",
                    "back",
                    "start",
                    "n",
                    "exit",
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
        dry_run_args = calls[0]
        self.assertEqual(dry_run_args[dry_run_args.index("--batch-size") + 1], "4")
        self.assertEqual(dry_run_args[dry_run_args.index("--concurrency") + 1], "2")
        self.assertEqual(dry_run_args[dry_run_args.index("--cache") + 1], "cache.json")
        self.assertEqual(dry_run_args[dry_run_args.index("--work-dir") + 1], "run")
        self.assertIn("--quiet", dry_run_args)

    def test_output_menu_can_set_custom_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(
                [
                    "more",
                    "advanced",
                    "output",
                    "custom",
                    "custom.epub",
                    "back",
                    "back",
                    "exit",
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

    def test_existing_cache_marks_conversion_as_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            (root / "book.bilingual.epub.translation-cache.json").write_text("{}", encoding="utf-8")
            answers = iter(["start", "n", "exit"])
            calls: list[list[str]] = []
            outputs: list[str] = []

            code = run_interactive(
                seed_args(input_path, api_key="secret"),
                execute=lambda args: calls.append(args) or 0,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )
            output_text = "\n".join(outputs)

        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("继续转换 EPUB（先 dry-run）", output_text)
        self.assertIn("检测到翻译缓存，将跳过已缓存段落。", output_text)

    def test_start_conversion_does_not_continue_when_dry_run_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "book.epub"
            input_path.write_bytes(b"epub")
            answers = iter(["start"])
            calls: list[list[str]] = []
            outputs: list[str] = []

            code = run_interactive(
                seed_args(input_path, api_key="secret"),
                execute=lambda args: calls.append(args) or 7,
                input_func=lambda _: next(answers),
                getpass_func=lambda _: "",
                print_func=outputs.append,
                cwd=root,
            )

        self.assertEqual(code, 7)
        self.assertEqual(len(calls), 1)
        self.assertIn("dry-run 失败，退出码 7.", "\n".join(outputs))

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
                    "ebook",
                    "2",  # books/b.epub
                    "back",
                    "start",
                    "n",  # stop after dry-run
                    "exit",
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
        output_text = "\n".join(outputs)
        self.assertIn("1. books/a.epub", output_text)
        self.assertIn("2. books/b.epub", output_text)

    def test_ebook_menu_reprompts_for_invalid_manual_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "notes.txt").write_text("not epub", encoding="utf-8")
            (root / "book.epub").write_bytes(b"epub")
            answers = iter(
                [
                    "ebook",
                    "manual",
                    "",
                    "missing.epub",
                    "notes.txt",
                    "book.epub",
                    "back",
                    "exit",
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
            answers = iter(["start", "exit"])
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
            answers = iter(["start", "n", "exit"])
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
                    "more",
                    "save_env",
                    "y",  # save defaults
                    "n",  # do not save API key
                    "exit",
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
