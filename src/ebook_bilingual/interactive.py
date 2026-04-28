from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import getpass
from pathlib import Path
import shlex
from typing import Literal, Protocol
import unicodedata

from .paths import default_output_path


InputFunc = Callable[[str], str]
SecretFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
ExecuteFunc = Callable[[list[str]], int]
UiLang = Literal["zh", "en"]


TEXT: dict[str, dict[UiLang, str]] = {
    "title": {"zh": "EPUB 双语转换器", "en": "EPUB Bilingual Converter"},
    "intro": {
        "zh": "先选择 EPUB 文件，再配置翻译模型，最后开始转换。",
        "en": "Select an EPUB file, configure the translation model, then start conversion.",
    },
    "select": {"zh": "选择", "en": "Select"},
    "choose_menu": {"zh": "请输入菜单数字。", "en": "Please choose a menu number."},
    "bye": {"zh": "再见。", "en": "Bye."},
    "cancelled": {"zh": "已取消。", "en": "Cancelled."},
    "not_selected": {"zh": "未选择", "en": "not selected"},
    "not_set": {"zh": "未设置", "en": "not set"},
    "configured": {"zh": "已配置", "en": "configured"},
    "missing": {"zh": "缺失", "en": "missing"},
    "auto": {"zh": "自动", "en": "auto"},
    "auto_after_ebook": {"zh": "选择 EPUB 后自动生成", "en": "auto after EPUB selection"},
    "all": {"zh": "全部", "en": "all"},
    "none": {"zh": "无", "en": "none"},
    "default": {"zh": "默认", "en": "default"},
    "unset": {"zh": "未设置", "en": "unset"},
    "yes": {"zh": "是", "en": "yes"},
    "no": {"zh": "否", "en": "no"},
    "interface_language": {"zh": "界面语言", "en": "Interface language"},
    "language_zh": {"zh": "中文", "en": "Chinese"},
    "language_en": {"zh": "英文", "en": "English"},
    "language_menu_title": {"zh": "界面语言 / Interface Language", "en": "Interface Language / 界面语言"},
    "current_language": {"zh": "当前语言", "en": "Current language"},
    "language_menu": {"zh": "界面语言 / Language", "en": "Language / 界面语言"},
    "language_set_zh": {"zh": "界面语言已设置为中文。", "en": "Interface language set to Chinese."},
    "language_set_en": {"zh": "界面语言已设置为英文。", "en": "Interface language set to English."},
    "menu_common": {"zh": "常用操作", "en": "Common tasks"},
    "menu_optional": {"zh": "可选调整", "en": "Optional settings"},
    "menu_other": {"zh": "其他", "en": "Other"},
    "menu_start": {"zh": "开始转换 EPUB", "en": "Start EPUB conversion"},
    "menu_ebook": {"zh": "选择 EPUB 文件", "en": "Select EPUB file"},
    "menu_model": {"zh": "配置翻译模型", "en": "Configure translation model"},
    "menu_output": {"zh": "设置输出位置", "en": "Set output location"},
    "menu_conversion": {"zh": "设置译文显示方式", "en": "Set bilingual layout"},
    "menu_advanced": {"zh": "高级参数", "en": "Advanced parameters"},
    "menu_save_env": {"zh": "保存当前配置到 .env", "en": "Save current settings to .env"},
    "menu_exit": {"zh": "退出", "en": "Exit"},
    "ebook": {"zh": "输入 EPUB", "en": "Input EPUB"},
    "output": {"zh": "输出 EPUB", "en": "Output EPUB"},
    "model": {"zh": "翻译模型", "en": "Translation model"},
    "api_key": {"zh": "API Key", "en": "API key"},
    "base_url": {"zh": "Base URL", "en": "Base URL"},
    "languages": {"zh": "翻译语言", "en": "Translation languages"},
    "layout": {"zh": "布局", "en": "Layout"},
    "mock": {"zh": "模拟翻译", "en": "Mock"},
    "number_headings": {"zh": "标题编号", "en": "Number headings"},
    "batch": {"zh": "批大小", "en": "Batch"},
    "concurrency": {"zh": "并发", "en": "Concurrency"},
    "min_chars": {"zh": "最少字符", "en": "Min chars"},
    "cache": {"zh": "缓存", "en": "Cache"},
    "work_dir": {"zh": "工作目录", "en": "Work dir"},
    "limit": {"zh": "限制", "en": "Limit"},
    "quiet": {"zh": "静默输出", "en": "Quiet"},
    "current_ebook": {"zh": "当前 EPUB", "en": "Current EPUB"},
    "current_output": {"zh": "当前输出 EPUB", "en": "Current output EPUB"},
    "output_menu_title": {"zh": "设置输出位置", "en": "Set output location"},
    "available_books": {"zh": "books/ 下可选 EPUB:", "en": "Available EPUB files in books/:"},
    "enter_epub_path": {"zh": "输入 EPUB 路径", "en": "Enter EPUB path"},
    "set_output_path": {"zh": "设置输出路径", "en": "Set output path"},
    "auto_output_path": {"zh": "使用自动输出路径", "en": "Use automatic output path"},
    "back": {"zh": "返回", "en": "Back"},
    "selected_ebook": {"zh": "已选择 EPUB", "en": "Selected EPUB"},
    "output_auto": {"zh": "输出路径已设置为自动。", "en": "Output path set to automatic."},
    "source_language": {"zh": "源语言", "en": "Source language"},
    "target_language": {"zh": "目标语言", "en": "Target language"},
    "mock_translator": {"zh": "模拟翻译器", "en": "Mock translator"},
    "style_css": {"zh": "样式 CSS", "en": "Style CSS"},
    "toggle_mock": {"zh": "切换模拟翻译器", "en": "Toggle mock translator"},
    "toggle_heading_numbers": {"zh": "切换标题编号", "en": "Toggle heading numbers"},
    "heading_numbers_require_clean": {
        "zh": "标题编号需要 clean 布局。",
        "en": "Heading numbers require clean layout.",
    },
    "style_css_requires_clean": {"zh": "样式 CSS 需要 clean 布局。", "en": "Style CSS requires clean layout."},
    "batch_size": {"zh": "批大小", "en": "Batch size"},
    "timeout_seconds": {"zh": "超时秒数", "en": "Timeout seconds"},
    "retries": {"zh": "重试次数", "en": "Retries"},
    "cache_path": {"zh": "缓存路径", "en": "Cache path"},
    "limit_segments": {"zh": "限制段落数", "en": "Limit segments"},
    "terminology": {"zh": "术语表", "en": "Terminology"},
    "terminology_csv": {"zh": "术语表 CSV/TSV", "en": "Terminology CSV/TSV"},
    "toggle_quiet": {"zh": "切换静默输出", "en": "Toggle quiet output"},
    "input_price": {"zh": "输入价格/百万 tokens", "en": "Input price per 1M tokens"},
    "output_price": {"zh": "输出价格/百万 tokens", "en": "Output price per 1M tokens"},
    "price_currency": {"zh": "价格币种", "en": "Price currency"},
    "output_token_ratio": {"zh": "输出 token 比例", "en": "Output token ratio"},
    "cannot_start": {"zh": "无法开始转换:", "en": "Cannot start conversion:"},
    "command_preview": {"zh": "命令预览:", "en": "Command preview:"},
    "dry_run_first": {"zh": "先执行 dry-run...", "en": "Running dry-run first..."},
    "dry_run_failed": {"zh": "dry-run 失败，退出码", "en": "Dry-run failed with exit code"},
    "start_real": {"zh": "现在开始真实转换?", "en": "Start the real conversion now?"},
    "stopped_after_dry_run": {"zh": "已在 dry-run 后停止。", "en": "Stopped after dry-run."},
    "save_model_defaults": {"zh": "保存模型默认配置到 .env?", "en": "Save model defaults to .env?"},
    "save_api_key": {"zh": "保存 API Key 到 .env?", "en": "Save API key to .env?"},
    "saved_defaults": {"zh": "已保存默认配置到", "en": "Saved defaults to"},
    "input_epub": {"zh": "输入 EPUB", "en": "Input EPUB"},
    "enter_epub_required": {"zh": "请输入 EPUB 路径。", "en": "Please enter an EPUB path."},
    "epub_required": {"zh": "必须选择电子书。", "en": "Ebook is required."},
    "epub_suffix": {"zh": "电子书必须是 .epub 文件。", "en": "Ebook must be an .epub file."},
    "epub_missing": {"zh": "电子书文件不存在", "en": "Ebook file does not exist"},
    "epub_not_file": {"zh": "电子书路径不是文件", "en": "Ebook path is not a file"},
    "model_required": {"zh": "除非启用模拟翻译器，否则必须配置模型。", "en": "Model is required unless mock translator is enabled."},
    "api_key_required": {"zh": "除非启用模拟翻译器，否则必须配置 API Key。", "en": "API key is required unless mock translator is enabled."},
    "custom_output_epub": {"zh": "自定义输出 EPUB", "en": "Custom output EPUB"},
    "blank_for_auto": {"zh": "留空自动", "en": "blank for auto"},
    "choose_one_of": {"zh": "请选择其中之一", "en": "Please choose one of"},
    "answer_yes_no": {"zh": "请回答 yes 或 no。", "en": "Please answer yes or no."},
    "must_integer": {"zh": "必须是整数。", "en": "must be an integer."},
    "must_number": {"zh": "必须是数字。", "en": "must be a number."},
    "preserve_desc": {"zh": "保留原书样式", "en": "keep original EPUB styling"},
    "clean_desc": {"zh": "清爽双语排版", "en": "clean bilingual reading layout"},
}


class SeedArgs(Protocol):
    input: Path | None
    output: Path | None
    model: str | None
    api_key: str | None
    base_url: str
    source_lang: str
    target_lang: str
    layout: str
    style_css: Path | None
    number_headings: bool
    dry_run: bool
    mock: bool
    batch_size: int
    concurrency: int
    min_chars: int
    timeout: int
    retries: int
    cache: Path | None
    work_dir: Path | None
    limit: int | None
    terminology: Path | None
    quiet: bool
    input_price_per_1m: float | None
    output_price_per_1m: float | None
    price_currency: str
    output_token_ratio: float


@dataclass
class WizardConfig:
    input_path: Path | None
    output_path: Path | None
    model: str
    api_key: str
    base_url: str
    source_lang: str
    target_lang: str
    layout: str
    style_css: Path | None
    number_headings: bool
    mock: bool
    batch_size: int
    concurrency: int
    min_chars: int
    timeout: int
    retries: int
    cache_path: Path | None
    work_dir: Path | None
    limit: int | None
    terminology_path: Path | None
    quiet: bool
    input_price_per_1m: float | None
    output_price_per_1m: float | None
    price_currency: str
    output_token_ratio: float
    ui_lang: UiLang = "zh"


def t(lang: UiLang, key: str) -> str:
    return TEXT[key][lang]


def run_interactive(
    seed: SeedArgs,
    *,
    execute: ExecuteFunc,
    input_func: InputFunc = input,
    getpass_func: SecretFunc = getpass.getpass,
    print_func: PrintFunc = print,
    cwd: Path | None = None,
) -> int:
    root = cwd or Path.cwd()
    config = initial_config(seed, root)
    try:
        print_func(t(config.ui_lang, "title"))
        print_func(t(config.ui_lang, "intro"))
        while True:
            print_main_screen(config, print_func)
            choice = prompt_text(t(config.ui_lang, "select"), "", input_func=input_func)
            if choice == "1":
                exit_code = start_conversion(config, cwd=root, execute=execute, input_func=input_func, print_func=print_func)
                if exit_code is not None:
                    return exit_code
            elif choice == "2":
                configure_ebook(config, cwd=root, input_func=input_func, print_func=print_func)
            elif choice == "3":
                configure_model(config, input_func=input_func, getpass_func=getpass_func, print_func=print_func)
            elif choice == "4":
                configure_output(config, input_func=input_func, print_func=print_func)
            elif choice == "5":
                configure_conversion(config, input_func=input_func, print_func=print_func)
            elif choice == "6":
                configure_advanced(config, input_func=input_func, print_func=print_func)
            elif choice == "7":
                save_env_defaults(config, root, input_func=input_func, print_func=print_func)
            elif choice == "8":
                configure_language(config, input_func=input_func, print_func=print_func)
            elif choice == "0":
                print_func(t(config.ui_lang, "bye"))
                return 0
            else:
                print_func(t(config.ui_lang, "choose_menu"))
    except EOFError:
        print_func("")
        print_func(t(config.ui_lang, "cancelled"))
        return 0
    except KeyboardInterrupt:
        print_func("")
        print_func(t(config.ui_lang, "cancelled"))
        return 130


def initial_config(seed: SeedArgs, cwd: Path) -> WizardConfig:
    input_path = seed.input or suggest_epub_path(cwd)
    return WizardConfig(
        input_path=input_path,
        output_path=seed.output,
        model=seed.model or "",
        api_key=seed.api_key or "",
        base_url=seed.base_url,
        source_lang=seed.source_lang,
        target_lang=seed.target_lang,
        layout=seed.layout,
        style_css=seed.style_css if seed.layout == "clean" else None,
        number_headings=seed.number_headings if seed.layout == "clean" else False,
        mock=seed.mock,
        batch_size=seed.batch_size,
        concurrency=seed.concurrency,
        min_chars=seed.min_chars,
        timeout=seed.timeout,
        retries=seed.retries,
        cache_path=seed.cache,
        work_dir=seed.work_dir,
        limit=seed.limit,
        terminology_path=seed.terminology,
        quiet=seed.quiet,
        input_price_per_1m=seed.input_price_per_1m,
        output_price_per_1m=seed.output_price_per_1m,
        price_currency=seed.price_currency,
        output_token_ratio=seed.output_token_ratio,
    )


def print_main_screen(config: WizardConfig, print_func: PrintFunc) -> None:
    lang = config.ui_lang
    print_func("")
    for line in render_status_box(config):
        print_func(line)
    print_func("")
    print_func(f"{t(lang, 'menu_common')}:")
    print_func(f"1. {t(lang, 'menu_start')}")
    print_func(f"2. {t(lang, 'menu_ebook')}")
    print_func(f"3. {t(lang, 'menu_model')}")
    print_func(f"{t(lang, 'menu_optional')}:")
    print_func(f"4. {t(lang, 'menu_output')}")
    print_func(f"5. {t(lang, 'menu_conversion')}")
    print_func(f"6. {t(lang, 'menu_advanced')}")
    print_func(f"{t(lang, 'menu_other')}:")
    print_func(f"7. {t(lang, 'menu_save_env')}")
    print_func(f"8. {t(lang, 'language_menu')}: {current_language_name(config)}")
    print_func(f"0. {t(lang, 'menu_exit')}")


def render_status_box(config: WizardConfig, width: int = 78) -> list[str]:
    lang = config.ui_lang
    lines = [
        t(lang, "title"),
        f"{t(lang, 'interface_language')}: {current_language_name(config)}",
        f"{t(lang, 'ebook')}: {path_default_text(config.input_path) or '(' + t(lang, 'not_selected') + ')'}",
        f"{t(lang, 'output')}: {display_output_path(config)}",
        f"{t(lang, 'model')}: {config.model or '(' + t(lang, 'not_set') + ')'}",
        f"{t(lang, 'api_key')}: {api_key_status(config.api_key, lang)}",
        f"{t(lang, 'base_url')}: {config.base_url}",
        f"{t(lang, 'languages')}: {config.source_lang} -> {config.target_lang}",
        f"{t(lang, 'layout')}: {config.layout} ({layout_description(config.layout, lang)})",
        f"{t(lang, 'mock')}: {yes_no(config.mock, lang)} | {t(lang, 'number_headings')}: {yes_no(config.number_headings, lang)}",
        f"{t(lang, 'batch')}: {config.batch_size} | {t(lang, 'concurrency')}: {config.concurrency} | {t(lang, 'min_chars')}: {config.min_chars}",
        f"{t(lang, 'cache')}: {path_default_text(config.cache_path) or t(lang, 'auto')} | {t(lang, 'work_dir')}: {path_default_text(config.work_dir) or t(lang, 'auto')}",
        f"{t(lang, 'limit')}: {optional_text(config.limit) or t(lang, 'all')} | {t(lang, 'quiet')}: {yes_no(config.quiet, lang)}",
    ]
    return box_lines(lines, width)


def box_lines(lines: list[str], width: int) -> list[str]:
    inner_width = max(20, width - 4)
    rendered = ["+" + "-" * (inner_width + 2) + "+"]
    for line in lines:
        rendered.append("| " + fit_cell(line, inner_width) + " |")
    rendered.append("+" + "-" * (inner_width + 2) + "+")
    return rendered


def fit_cell(text: str, width: int) -> str:
    fitted = []
    used = 0
    for char in text:
        char_width = display_width(char)
        if used + char_width > width:
            break
        fitted.append(char)
        used += char_width
    return "".join(fitted) + " " * (width - used)


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1 for char in text)


def configure_language(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    while True:
        lang = config.ui_lang
        print_func("")
        print_func(t(lang, "language_menu_title"))
        print_func(f"{t(lang, 'current_language')}: {current_language_name(config)}")
        print_func("1. 中文")
        print_func("2. English")
        print_func(f"0. {t(lang, 'back')}")
        choice = prompt_text(t(lang, "select"), "", input_func=input_func)
        if choice == "1":
            config.ui_lang = "zh"
            print_func(t(config.ui_lang, "language_set_zh"))
            return
        if choice == "2":
            config.ui_lang = "en"
            print_func(t(config.ui_lang, "language_set_en"))
            return
        if choice == "0":
            return
        print_func(t(lang, "choose_menu"))


def current_language_name(config: WizardConfig) -> str:
    if config.ui_lang == "zh":
        return t(config.ui_lang, "language_zh")
    return t(config.ui_lang, "language_en")


def configure_ebook(config: WizardConfig, *, cwd: Path, input_func: InputFunc, print_func: PrintFunc) -> None:
    lang = config.ui_lang
    while True:
        lang = config.ui_lang
        choices = list_epub_paths(cwd)
        manual_option = len(choices) + 1
        print_func("")
        print_func(t(lang, "menu_ebook"))
        print_func(f"{t(lang, 'current_ebook')}: {path_default_text(config.input_path) or '(' + t(lang, 'not_selected') + ')'}")
        if choices:
            print_func(t(lang, "available_books"))
            for index, choice in enumerate(choices, start=1):
                print_func(f"  {index}. {choice}")
        print_func(f"{manual_option}. {t(lang, 'enter_epub_path')}")
        print_func(f"0. {t(lang, 'back')}")
        choice = prompt_text(t(lang, "select"), "", input_func=input_func)
        if choice == "0":
            return
        if choice.isdecimal():
            index = int(choice)
            if 1 <= index <= len(choices):
                config.input_path = choices[index - 1]
                print_func(f"{t(lang, 'selected_ebook')}: {config.input_path}")
            elif index == manual_option:
                config.input_path = prompt_epub_path(
                    config.input_path,
                    input_func=input_func,
                    print_func=print_func,
                    cwd=cwd,
                    lang=lang,
                )
            else:
                print_func(t(lang, "choose_menu"))
        else:
            print_func(t(lang, "choose_menu"))


def configure_output(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    while True:
        lang = config.ui_lang
        print_func("")
        print_func(t(lang, "output_menu_title"))
        print_func(f"{t(lang, 'current_output')}: {display_output_path(config)}")
        print_func(f"1. {t(lang, 'set_output_path')}")
        print_func(f"2. {t(lang, 'auto_output_path')}")
        print_func(f"0. {t(lang, 'back')}")
        choice = prompt_text(t(lang, "select"), "", input_func=input_func)
        if choice == "1":
            config.output_path = prompt_output_path(config.output_path, input_func=input_func, lang=lang)
        elif choice == "2":
            config.output_path = None
            print_func(t(lang, "output_auto"))
        elif choice == "0":
            return
        else:
            print_func(t(lang, "choose_menu"))


def configure_model(
    config: WizardConfig,
    *,
    input_func: InputFunc,
    getpass_func: SecretFunc,
    print_func: PrintFunc,
) -> None:
    while True:
        lang = config.ui_lang
        print_func("")
        print_func(t(lang, "menu_model"))
        print_func(f"{t(lang, 'base_url')}: {config.base_url}")
        print_func(f"{t(lang, 'model')}: {config.model or '(' + t(lang, 'not_set') + ')'}")
        print_func(f"{t(lang, 'api_key')}: {api_key_status(config.api_key, lang)}")
        print_func(f"{t(lang, 'source_language')}: {config.source_lang}")
        print_func(f"{t(lang, 'target_language')}: {config.target_lang}")
        print_func(f"1. {t(lang, 'base_url')}")
        print_func(f"2. {t(lang, 'model')}")
        print_func(f"3. {t(lang, 'api_key')}")
        print_func(f"4. {t(lang, 'source_language')}")
        print_func(f"5. {t(lang, 'target_language')}")
        print_func(f"0. {t(lang, 'back')}")
        choice = prompt_text(t(lang, "select"), "", input_func=input_func)
        if choice == "1":
            config.base_url = prompt_text(t(lang, "base_url"), config.base_url, input_func=input_func)
        elif choice == "2":
            config.model = prompt_text(t(lang, "model"), config.model, input_func=input_func)
        elif choice == "3":
            config.api_key = prompt_secret(t(lang, "api_key"), config.api_key, getpass_func=getpass_func, lang=lang)
        elif choice == "4":
            config.source_lang = prompt_text(t(lang, "source_language"), config.source_lang, input_func=input_func)
        elif choice == "5":
            config.target_lang = prompt_text(t(lang, "target_language"), config.target_lang, input_func=input_func)
        elif choice == "0":
            return
        else:
            print_func(t(lang, "choose_menu"))


def configure_conversion(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    while True:
        lang = config.ui_lang
        print_func("")
        print_func(t(lang, "menu_conversion"))
        print_func(f"{t(lang, 'layout')}: {config.layout} ({layout_description(config.layout, lang)})")
        print_func(f"{t(lang, 'mock_translator')}: {yes_no(config.mock, lang)}")
        print_func(f"{t(lang, 'number_headings')}: {yes_no(config.number_headings, lang)}")
        print_func(f"{t(lang, 'style_css')}: {path_default_text(config.style_css) or '(' + t(lang, 'default') + ')'}")
        print_func(f"1. {t(lang, 'layout')}")
        print_func(f"2. {t(lang, 'toggle_mock')}")
        print_func(f"3. {t(lang, 'toggle_heading_numbers')}")
        print_func(f"4. {t(lang, 'style_css')}")
        print_func(f"0. {t(lang, 'back')}")
        choice = prompt_text(t(lang, "select"), "", input_func=input_func)
        if choice == "1":
            config.layout = prompt_layout(config.layout, input_func=input_func, print_func=print_func, lang=lang)
            if config.layout != "clean":
                config.number_headings = False
                config.style_css = None
        elif choice == "2":
            config.mock = not config.mock
            print_func(f"{t(lang, 'mock_translator')}: {yes_no(config.mock, lang)}")
        elif choice == "3":
            if config.layout != "clean":
                print_func(t(lang, "heading_numbers_require_clean"))
            else:
                config.number_headings = not config.number_headings
                print_func(f"{t(lang, 'number_headings')}: {yes_no(config.number_headings, lang)}")
        elif choice == "4":
            if config.layout != "clean":
                print_func(t(lang, "style_css_requires_clean"))
            else:
                config.style_css = prompt_optional_path(t(lang, "style_css"), config.style_css, input_func=input_func)
        elif choice == "0":
            return
        else:
            print_func(t(lang, "choose_menu"))


def configure_advanced(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    while True:
        lang = config.ui_lang
        print_func("")
        print_func(t(lang, "menu_advanced"))
        print_func(f"{t(lang, 'batch_size')}: {config.batch_size}")
        print_func(f"{t(lang, 'concurrency')}: {config.concurrency}")
        print_func(f"{t(lang, 'min_chars')}: {config.min_chars}")
        print_func(f"{t(lang, 'timeout_seconds')}: {config.timeout}")
        print_func(f"{t(lang, 'retries')}: {config.retries}")
        print_func(f"{t(lang, 'cache_path')}: {path_default_text(config.cache_path) or t(lang, 'auto')}")
        print_func(f"{t(lang, 'work_dir')}: {path_default_text(config.work_dir) or t(lang, 'auto')}")
        print_func(f"{t(lang, 'limit_segments')}: {optional_text(config.limit) or t(lang, 'all')}")
        print_func(f"{t(lang, 'terminology')}: {path_default_text(config.terminology_path) or '(' + t(lang, 'none') + ')'}")
        print_func(f"{t(lang, 'quiet')}: {yes_no(config.quiet, lang)}")
        print_func(f"{t(lang, 'input_price')}: {optional_text(config.input_price_per_1m) or '(' + t(lang, 'unset') + ')'}")
        print_func(f"{t(lang, 'output_price')}: {optional_text(config.output_price_per_1m) or '(' + t(lang, 'unset') + ')'}")
        print_func(f"{t(lang, 'price_currency')}: {config.price_currency}")
        print_func(f"{t(lang, 'output_token_ratio')}: {config.output_token_ratio}")
        print_func(f"1. {t(lang, 'batch_size')}")
        print_func(f"2. {t(lang, 'concurrency')}")
        print_func(f"3. {t(lang, 'min_chars')}")
        print_func(f"4. {t(lang, 'timeout_seconds')}")
        print_func(f"5. {t(lang, 'retries')}")
        print_func(f"6. {t(lang, 'cache_path')}")
        print_func(f"7. {t(lang, 'work_dir')}")
        print_func(f"8. {t(lang, 'limit_segments')}")
        print_func(f"9. {t(lang, 'terminology_csv')}")
        print_func(f"10. {t(lang, 'toggle_quiet')}")
        print_func(f"11. {t(lang, 'input_price')}")
        print_func(f"12. {t(lang, 'output_price')}")
        print_func(f"13. {t(lang, 'price_currency')}")
        print_func(f"14. {t(lang, 'output_token_ratio')}")
        print_func(f"0. {t(lang, 'back')}")
        choice = prompt_text(t(lang, "select"), "", input_func=input_func)
        if choice == "1":
            config.batch_size = prompt_int(t(lang, "batch_size"), config.batch_size, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "2":
            config.concurrency = prompt_int(t(lang, "concurrency"), config.concurrency, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "3":
            config.min_chars = prompt_int(t(lang, "min_chars"), config.min_chars, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "4":
            config.timeout = prompt_int(t(lang, "timeout_seconds"), config.timeout, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "5":
            config.retries = prompt_int(t(lang, "retries"), config.retries, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "6":
            config.cache_path = prompt_optional_path(t(lang, "cache_path"), config.cache_path, input_func=input_func)
        elif choice == "7":
            config.work_dir = prompt_optional_path(t(lang, "work_dir"), config.work_dir, input_func=input_func)
        elif choice == "8":
            config.limit = prompt_optional_int(t(lang, "limit_segments"), config.limit, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "9":
            config.terminology_path = prompt_optional_path(t(lang, "terminology_csv"), config.terminology_path, input_func=input_func)
        elif choice == "10":
            config.quiet = not config.quiet
            print_func(f"{t(lang, 'quiet')}: {yes_no(config.quiet, lang)}")
        elif choice == "11":
            config.input_price_per_1m = prompt_optional_float(
                t(lang, "input_price"),
                config.input_price_per_1m,
                input_func=input_func,
                print_func=print_func,
                lang=lang,
            )
        elif choice == "12":
            config.output_price_per_1m = prompt_optional_float(
                t(lang, "output_price"),
                config.output_price_per_1m,
                input_func=input_func,
                print_func=print_func,
                lang=lang,
            )
        elif choice == "13":
            config.price_currency = prompt_text(t(lang, "price_currency"), config.price_currency, input_func=input_func)
        elif choice == "14":
            config.output_token_ratio = prompt_float(
                t(lang, "output_token_ratio"),
                config.output_token_ratio,
                input_func=input_func,
                print_func=print_func,
                lang=lang,
            )
        elif choice == "0":
            return
        else:
            print_func(t(lang, "choose_menu"))


def start_conversion(
    config: WizardConfig,
    *,
    cwd: Path,
    execute: ExecuteFunc,
    input_func: InputFunc,
    print_func: PrintFunc,
) -> int | None:
    lang = config.ui_lang
    errors = validate_start_config(config, cwd)
    if errors:
        print_func("")
        print_func(t(lang, "cannot_start"))
        for error in errors:
            print_func(f"  - {error}")
        return None

    print_summary(config, print_func)
    print_func("")
    print_func(t(lang, "dry_run_first"))
    dry_run_code = execute(build_conversion_args(config, dry_run=True))
    if dry_run_code != 0:
        print_func(f"{t(lang, 'dry_run_failed')} {dry_run_code}.")
        return dry_run_code

    if not confirm(t(lang, "start_real"), default=False, input_func=input_func, print_func=print_func, lang=lang):
        print_func(t(lang, "stopped_after_dry_run"))
        return None

    return execute(build_conversion_args(config, dry_run=False))


def validate_start_config(config: WizardConfig, cwd: Path) -> list[str]:
    errors = validate_epub_path(config.input_path, cwd, config.ui_lang)
    if not config.mock:
        if not config.model:
            errors.append(t(config.ui_lang, "model_required"))
        if not config.api_key:
            errors.append(t(config.ui_lang, "api_key_required"))
    return errors


def validate_epub_path(path: Path | None, cwd: Path, lang: UiLang) -> list[str]:
    if path is None:
        return [t(lang, "epub_required")]
    if path.suffix.lower() != ".epub":
        return [t(lang, "epub_suffix")]
    check_path = path if path.is_absolute() else cwd / path
    if not check_path.exists():
        return [f"{t(lang, 'epub_missing')}: {path}"]
    if not check_path.is_file():
        return [f"{t(lang, 'epub_not_file')}: {path}"]
    return []


def suggest_epub_path(cwd: Path) -> Path | None:
    return first_path(list_epub_paths(cwd))


def list_epub_paths(cwd: Path) -> list[Path]:
    books_dir = cwd / "books"
    if not books_dir.exists():
        return []
    paths = []
    for path in sorted(books_dir.glob("*.epub")):
        if ".bilingual" in path.name:
            continue
        try:
            paths.append(path.relative_to(cwd))
        except ValueError:
            paths.append(path)
    return paths


def first_path(paths: list[Path]) -> Path | None:
    return paths[0] if paths else None


def prompt_epub_path(
    default: Path | None,
    *,
    input_func: InputFunc,
    print_func: PrintFunc,
    cwd: Path,
    lang: UiLang,
) -> Path:
    while True:
        value = input_func(f"{t(lang, 'input_epub')}{format_default(path_default_text(default))}: ").strip()
        if not value:
            if default is None:
                print_func(t(lang, "enter_epub_required"))
                continue
            path = default
        else:
            path = Path(value).expanduser()
        errors = validate_epub_path(path, cwd, lang)
        if not errors:
            return path
        for error in errors:
            print_func(error)


def prompt_layout(default: str, *, input_func: InputFunc, print_func: PrintFunc, lang: UiLang) -> str:
    print_func(f"  preserve = {t(lang, 'preserve_desc')}")
    print_func(f"  clean    = {t(lang, 'clean_desc')}")
    return prompt_choice(t(lang, "layout"), ("preserve", "clean"), default, input_func=input_func, print_func=print_func, lang=lang)


def prompt_output_path(default: Path | None, *, input_func: InputFunc, lang: UiLang) -> Path | None:
    if default is None:
        value = input_func(f"{t(lang, 'custom_output_epub')} ({t(lang, 'blank_for_auto')}): ").strip()
        return Path(value).expanduser() if value else None
    value = input_func(f"{t(lang, 'custom_output_epub')}{format_default(str(default))}: ").strip()
    return Path(value).expanduser() if value else default


def prompt_text(label: str, default: str, *, input_func: InputFunc) -> str:
    value = input_func(f"{label}{format_default(default)}: ").strip()
    return value or default


def prompt_secret(label: str, default: str, *, getpass_func: SecretFunc, lang: UiLang) -> str:
    value = getpass_func(f"{label}{format_default(t(lang, 'configured') if default else '')}: ").strip()
    return value or default


def prompt_choice(
    label: str,
    choices: tuple[str, ...],
    default: str,
    *,
    input_func: InputFunc,
    print_func: PrintFunc,
    lang: UiLang,
) -> str:
    while True:
        value = prompt_text(f"{label} ({'/'.join(choices)})", default, input_func=input_func)
        if value in choices:
            return value
        print_func(f"{t(lang, 'choose_one_of')}: {', '.join(choices)}")


def confirm(label: str, *, default: bool, input_func: InputFunc, print_func: PrintFunc, lang: UiLang) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        value = input_func(f"{label} [{suffix}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print_func(t(lang, "answer_yes_no"))


def prompt_int(label: str, default: int, *, input_func: InputFunc, print_func: PrintFunc, lang: UiLang) -> int:
    while True:
        value = prompt_text(label, str(default), input_func=input_func)
        try:
            return int(value)
        except ValueError:
            print_func(f"{label} {t(lang, 'must_integer')}")


def prompt_float(label: str, default: float, *, input_func: InputFunc, print_func: PrintFunc, lang: UiLang) -> float:
    while True:
        value = prompt_text(label, str(default), input_func=input_func)
        try:
            return float(value)
        except ValueError:
            print_func(f"{label} {t(lang, 'must_number')}")


def prompt_optional_int(
    label: str,
    default: int | None,
    *,
    input_func: InputFunc,
    print_func: PrintFunc,
    lang: UiLang,
) -> int | None:
    while True:
        value = input_func(f"{label}{format_default(optional_text(default))}: ").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            print_func(f"{label} {t(lang, 'must_integer')}")


def prompt_optional_float(
    label: str,
    default: float | None,
    *,
    input_func: InputFunc,
    print_func: PrintFunc,
    lang: UiLang,
) -> float | None:
    while True:
        value = input_func(f"{label}{format_default(optional_text(default))}: ").strip()
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            print_func(f"{label} {t(lang, 'must_number')}")


def prompt_optional_path(label: str, default: Path | None, *, input_func: InputFunc) -> Path | None:
    value = input_func(f"{label}{format_default(path_default_text(default))}: ").strip()
    if not value:
        return default
    return Path(value).expanduser()


def optional_text(value: object | None) -> str:
    return "" if value is None else str(value)


def path_default_text(value: Path | None) -> str:
    return "" if value is None else str(value)


def format_default(default: str) -> str:
    return f" [{default}]" if default else ""


def yes_no(value: bool, lang: UiLang) -> str:
    return t(lang, "yes") if value else t(lang, "no")


def print_summary(config: WizardConfig, print_func: PrintFunc) -> None:
    print_func("")
    print_func(t(config.ui_lang, "command_preview"))
    print_func("  " + shlex.join(["ebook-bilingual", *redact_args(build_conversion_args(config, dry_run=False))]))


def display_output_path(config: WizardConfig) -> str:
    lang = config.ui_lang
    if config.output_path is not None:
        return str(config.output_path)
    if config.input_path is None:
        return f"({t(lang, 'auto_after_ebook')})"
    if config.work_dir is not None:
        return f"{config.work_dir / default_output_path(config.input_path).name} ({t(lang, 'auto')})"
    return f"{default_output_path(config.input_path)} ({t(lang, 'auto')})"


def api_key_status(api_key: str, lang: UiLang) -> str:
    return t(lang, "configured") if api_key else t(lang, "missing")


def layout_description(layout: str, lang: UiLang) -> str:
    if layout == "clean":
        return t(lang, "clean_desc")
    return t(lang, "preserve_desc")


def save_env_defaults(
    config: WizardConfig,
    root: Path,
    *,
    input_func: InputFunc,
    print_func: PrintFunc,
) -> None:
    lang = config.ui_lang
    if not confirm(t(lang, "save_model_defaults"), default=True, input_func=input_func, print_func=print_func, lang=lang):
        return
    values = env_values(config)
    if config.api_key and confirm(t(lang, "save_api_key"), default=False, input_func=input_func, print_func=print_func, lang=lang):
        values["LLM_API_KEY"] = config.api_key
    update_env_file(root / ".env", values)
    print_func(f"{t(lang, 'saved_defaults')} {root / '.env'}")


def build_conversion_args(config: WizardConfig, *, dry_run: bool) -> list[str]:
    if config.input_path is None:
        raise ValueError("Ebook is required.")
    args = [str(config.input_path)]
    if config.output_path is not None:
        args.append(str(config.output_path))
    append_value(args, "--model", config.model)
    append_value(args, "--api-key", config.api_key)
    append_value(args, "--base-url", config.base_url)
    append_value(args, "--source-lang", config.source_lang)
    append_value(args, "--target-lang", config.target_lang)
    append_value(args, "--layout", config.layout)
    if config.layout == "clean":
        append_path(args, "--style-css", config.style_css)
    if config.layout == "clean" and config.number_headings:
        args.append("--number-headings")
    if dry_run:
        args.append("--dry-run")
    if config.mock:
        args.append("--mock")
    append_value(args, "--batch-size", str(config.batch_size))
    append_value(args, "--concurrency", str(config.concurrency))
    append_value(args, "--min-chars", str(config.min_chars))
    append_value(args, "--timeout", str(config.timeout))
    append_value(args, "--retries", str(config.retries))
    append_path(args, "--cache", config.cache_path)
    append_path(args, "--work-dir", config.work_dir)
    if config.limit is not None:
        append_value(args, "--limit", str(config.limit))
    append_path(args, "--terminology", config.terminology_path)
    if config.quiet:
        args.append("--quiet")
    if config.input_price_per_1m is not None:
        append_value(args, "--input-price-per-1m", str(config.input_price_per_1m))
    if config.output_price_per_1m is not None:
        append_value(args, "--output-price-per-1m", str(config.output_price_per_1m))
    append_value(args, "--price-currency", config.price_currency)
    append_value(args, "--output-token-ratio", str(config.output_token_ratio))
    return args


def append_value(args: list[str], flag: str, value: str) -> None:
    if value:
        args.extend([flag, value])


def append_path(args: list[str], flag: str, value: Path | None) -> None:
    if value is not None:
        args.extend([flag, str(value)])


def redact_args(args: list[str]) -> list[str]:
    redacted = []
    hide_next = False
    for arg in args:
        if hide_next:
            redacted.append("***")
            hide_next = False
            continue
        redacted.append(arg)
        hide_next = arg == "--api-key"
    return redacted


def env_values(config: WizardConfig) -> dict[str, str]:
    values = {
        "LLM_BASE_URL": config.base_url,
        "LLM_MODEL": config.model,
        "LLM_SOURCE_LANG": config.source_lang,
        "LLM_TARGET_LANG": config.target_lang,
        "LLM_CONCURRENCY": str(config.concurrency),
        "LLM_LAYOUT": config.layout,
        "LLM_STYLE_CSS": path_default_text(config.style_css),
        "LLM_PRICE_CURRENCY": config.price_currency,
        "LLM_OUTPUT_TOKEN_RATIO": str(config.output_token_ratio),
    }
    if config.input_price_per_1m is not None:
        values["LLM_INPUT_PRICE_PER_1M"] = str(config.input_price_per_1m)
    if config.output_price_per_1m is not None:
        values["LLM_OUTPUT_PRICE_PER_1M"] = str(config.output_price_per_1m)
    return values


def update_env_file(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    updated: list[str] = []
    for line in lines:
        key = env_line_key(line)
        if key is not None and key in values:
            updated.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            updated.append(line)
    for key, value in values.items():
        if key not in seen:
            updated.append(f"{key}={value}")
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def env_line_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").strip()
    if "=" not in stripped:
        return None
    key, _ = stripped.split("=", 1)
    key = key.strip()
    return key or None
