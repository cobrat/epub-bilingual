from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import getpass
import json
from pathlib import Path
import shlex
import sys
from typing import Literal, Protocol
from urllib import error

import questionary
from questionary import Choice, Style

from .app import ConversionOptions, run_conversion, run_dry_run
from .llm import fetch_ollama_models, is_ollama_base_url
from .paths import default_output_path, discover_style_css
from .providers import ProviderTemplate, PROVIDER_TEMPLATES, provider_id_for_base_url, provider_template_by_id


InputFunc = Callable[[str], str]
SecretFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]
ExecuteFunc = Callable[[list[str]], int]
UiLang = Literal["zh", "en"]

WIZARD_SNAPSHOT_SCHEMA = 1


TEXT: dict[str, dict[UiLang, str]] = {
    "title": {"zh": "EPUB 双语转换器", "en": "EPUB Bilingual Converter"},
    "select": {"zh": "选择", "en": "Select"},
    "select_hint": {"zh": "输入数字选择；也可输入选项名称。", "en": "Enter a number, or type an option name."},
    "next_action": {"zh": "下一步要做什么？", "en": "What do you want to do next?"},
    "choose_menu": {"zh": "请输入菜单数字。", "en": "Please choose a menu number."},
    "bye": {"zh": "再见。", "en": "Bye."},
    "cancelled": {"zh": "已取消。", "en": "Cancelled."},
    "not_selected": {"zh": "未选择", "en": "not selected"},
    "not_set": {"zh": "未设置", "en": "not set"},
    "configured": {"zh": "已配置", "en": "configured"},
    "missing": {"zh": "缺失", "en": "missing"},
    "not_required": {"zh": "不需要", "en": "not required"},
    "auto": {"zh": "自动", "en": "auto"},
    "auto_after_ebook": {"zh": "选择 EPUB 后自动生成", "en": "auto after EPUB selection"},
    "all": {"zh": "全部", "en": "all"},
    "none": {"zh": "无", "en": "none"},
    "default": {"zh": "默认", "en": "default"},
    "unset": {"zh": "未设置", "en": "unset"},
    "yes": {"zh": "是", "en": "yes"},
    "no": {"zh": "否", "en": "no"},
    "language_zh": {"zh": "中文", "en": "Chinese"},
    "language_en": {"zh": "英文", "en": "English"},
    "language_menu_title": {"zh": "界面语言 / Interface Language", "en": "Interface Language / 界面语言"},
    "current_language": {"zh": "当前语言", "en": "Current language"},
    "language_menu": {"zh": "界面语言 / Language", "en": "Language / 界面语言"},
    "language_set_zh": {"zh": "界面语言已设置为中文。", "en": "Interface language set to Chinese."},
    "language_set_en": {"zh": "界面语言已设置为英文。", "en": "Interface language set to English."},
    "menu_start": {"zh": "开始", "en": "Start"},
    "menu_ebook": {"zh": "电子书", "en": "Book"},
    "menu_model": {"zh": "翻译", "en": "Translation"},
    "menu_output": {"zh": "设置输出位置", "en": "Set output location"},
    "menu_conversion": {"zh": "设置译文显示方式", "en": "Set bilingual layout"},
    "menu_options": {"zh": "选项", "en": "Options"},
    "menu_save_env": {"zh": "保存当前配置到 .env", "en": "Save current settings to .env"},
    "menu_exit": {"zh": "退出", "en": "Exit"},
    "status": {"zh": "状态", "en": "Status"},
    "ready": {"zh": "可以开始", "en": "Ready"},
    "needs_setup": {"zh": "还需配置", "en": "needs setup"},
    "will_dry_run": {"zh": "开始转换会先 dry-run", "en": "dry-run first"},
    "resume_ready": {"zh": "检测到缓存，可断点继续", "en": "cache found, ready to resume"},
    "cache_resume_hint": {
        "zh": "检测到翻译缓存，将跳过已缓存段落。",
        "en": "Translation cache found; cached segments will be skipped.",
    },
    "no_cache_yet": {"zh": "暂无缓存", "en": "no cache yet"},
    "ebook": {"zh": "书籍", "en": "Book"},
    "output": {"zh": "输出", "en": "Output"},
    "model": {"zh": "模型", "en": "Model"},
    "choose_provider": {"zh": "选择模型厂商模板", "en": "Choose provider template"},
    "custom_provider": {"zh": "自定义 OpenAI-compatible", "en": "Custom OpenAI-compatible"},
    "custom_model": {"zh": "自定义模型", "en": "Custom model"},
    "ollama_models": {"zh": "Ollama 本地模型", "en": "Ollama local models"},
    "ollama_fetch_failed": {"zh": "无法从 Ollama 获取模型", "en": "Could not fetch models from Ollama"},
    "ollama_no_models": {"zh": "Ollama 暂无可用模型，请先运行 ollama pull。", "en": "No Ollama models found. Run ollama pull first."},
    "provider_applied": {"zh": "已应用模型厂商模板", "en": "Applied provider template"},
    "advanced_model_settings": {"zh": "手动模型参数", "en": "Manual model settings"},
    "api_key": {"zh": "API Key", "en": "API key"},
    "base_url": {"zh": "Base URL", "en": "Base URL"},
    "layout": {"zh": "布局", "en": "Layout"},
    "mock": {"zh": "模拟翻译", "en": "Mock"},
    "number_headings": {"zh": "标题编号", "en": "Number headings"},
    "batch": {"zh": "批大小", "en": "Batch"},
    "concurrency": {"zh": "并发", "en": "Concurrency"},
    "min_chars": {"zh": "最少字符", "en": "Min chars"},
    "work_dir": {"zh": "工作目录", "en": "Work dir"},
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
    "choose_one_of": {"zh": "请选择其中之一", "en": "Please choose one of"},
    "answer_yes_no": {"zh": "请回答 yes 或 no。", "en": "Please answer yes or no."},
    "must_integer": {"zh": "必须是整数。", "en": "must be an integer."},
    "must_number": {"zh": "必须是数字。", "en": "must be a number."},
    "preserve_desc": {"zh": "保留原书样式", "en": "keep original EPUB styling"},
    "clean_desc": {"zh": "清爽双语排版", "en": "clean bilingual reading layout"},
    "session_loaded": {"zh": "已载入上次向导会话的配置。", "en": "Loaded settings from your last wizard session."},
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
    provider_id: str | None = None
    session_was_restored: bool = False


@dataclass(frozen=True)
class MenuChoice:
    value: str
    label: str


@dataclass(frozen=True)
class MenuSection:
    label: str


MenuEntry = MenuChoice | MenuSection

QUESTIONARY_STYLE = Style(
    [
        ("qmark", "fg:#22d3ee bold"),
        ("question", "bold"),
        ("answer", "fg:#10b981 bold"),
        ("pointer", "fg:#22d3ee bold"),
        ("highlighted", "fg:#22d3ee bold"),
        ("selected", "fg:#10b981"),
        ("separator", "fg:#6b7280"),
        ("instruction", "fg:#6b7280"),
        ("text", ""),
        ("disabled", "fg:#6b7280 italic"),
    ]
)


def t(lang: UiLang, key: str) -> str:
    return TEXT[key][lang]


def wizard_snapshot_path(cwd: Path) -> Path:
    return cwd / ".ebook-bilingual" / "wizard-last.json"


def wizard_config_from_snapshot(data: dict) -> WizardConfig | None:
    version = data.get("schema_version")
    if version != WIZARD_SNAPSHOT_SCHEMA:
        return None

    def optional_path(raw: object | None) -> Path | None:
        if raw is None:
            return None
        if isinstance(raw, str) and raw:
            return Path(raw)
        return None

    return WizardConfig(
        input_path=optional_path(data.get("input_path")),
        output_path=optional_path(data.get("output_path")),
        model=str(data.get("model") or ""),
        api_key="",  # never restored from disk; filled from seed/env below
        base_url=str(data.get("base_url") or ""),
        source_lang=str(data.get("source_lang") or ""),
        target_lang=str(data.get("target_lang") or ""),
        layout=str(data.get("layout") or "preserve"),
        style_css=optional_path(data.get("style_css")),
        number_headings=bool(data.get("number_headings")),
        mock=bool(data.get("mock")),
        batch_size=int(data.get("batch_size") or 8),
        concurrency=int(data.get("concurrency") or 1),
        min_chars=int(data.get("min_chars") or 2),
        timeout=int(data.get("timeout") or 120),
        retries=int(data.get("retries") or 3),
        cache_path=optional_path(data.get("cache_path")),
        work_dir=optional_path(data.get("work_dir")),
        limit=int(data["limit"]) if data.get("limit") is not None else None,
        terminology_path=optional_path(data.get("terminology_path")),
        quiet=bool(data.get("quiet")),
        input_price_per_1m=float(data["input_price_per_1m"]) if data.get("input_price_per_1m") is not None else None,
        output_price_per_1m=float(data["output_price_per_1m"]) if data.get("output_price_per_1m") is not None else None,
        price_currency=str(data.get("price_currency") or "USD"),
        output_token_ratio=float(data.get("output_token_ratio") or 1.15),
        ui_lang="zh" if data.get("ui_lang") != "en" else "en",
        provider_id=data.get("provider_id"),
        session_was_restored=True,
    )


def wizard_snapshot_from_config(config: WizardConfig) -> dict:
    return {
        "schema_version": WIZARD_SNAPSHOT_SCHEMA,
        "input_path": None if config.input_path is None else str(config.input_path),
        "output_path": None if config.output_path is None else str(config.output_path),
        "model": config.model,
        "base_url": config.base_url,
        "source_lang": config.source_lang,
        "target_lang": config.target_lang,
        "layout": config.layout,
        "style_css": None if config.style_css is None else str(config.style_css),
        "number_headings": config.number_headings,
        "mock": config.mock,
        "batch_size": config.batch_size,
        "concurrency": config.concurrency,
        "min_chars": config.min_chars,
        "timeout": config.timeout,
        "retries": config.retries,
        "cache_path": None if config.cache_path is None else str(config.cache_path),
        "work_dir": None if config.work_dir is None else str(config.work_dir),
        "limit": config.limit,
        "terminology_path": None if config.terminology_path is None else str(config.terminology_path),
        "quiet": config.quiet,
        "input_price_per_1m": config.input_price_per_1m,
        "output_price_per_1m": config.output_price_per_1m,
        "price_currency": config.price_currency,
        "output_token_ratio": config.output_token_ratio,
        "ui_lang": config.ui_lang,
        "provider_id": config.provider_id,
    }


def load_wizard_snapshot(cwd: Path) -> WizardConfig | None:
    path = wizard_snapshot_path(cwd)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return wizard_config_from_snapshot(payload)


def save_wizard_snapshot(config: WizardConfig, cwd: Path) -> None:
    path = wizard_snapshot_path(cwd)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(wizard_snapshot_from_config(config), ensure_ascii=False, indent=2)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(body + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def merge_loaded_wizard_into_fresh(config: WizardConfig, fresh: WizardConfig, *, seed_has_input: bool, seed_has_output: bool) -> WizardConfig:
    next_input = fresh.input_path if seed_has_input else config.input_path
    next_output = fresh.output_path if seed_has_output else config.output_path
    return replace(
        config,
        api_key=fresh.api_key,
        input_path=next_input,
        output_path=next_output,
        session_was_restored=True,
    )


def wizard_config_from_seed(seed: SeedArgs, cwd: Path) -> WizardConfig:
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
        provider_id=provider_id_for_base_url(seed.base_url),
        session_was_restored=False,
    )


def run_interactive(
    seed: SeedArgs,
    *,
    execute: ExecuteFunc | None = None,
    input_func: InputFunc = input,
    getpass_func: SecretFunc = getpass.getpass,
    print_func: PrintFunc = print,
    cwd: Path | None = None,
) -> int:
    root = cwd or Path.cwd()
    config = initial_config(seed, root)
    try:
        printed_intro = False
        while True:
            if not printed_intro:
                print_intro(config, print_func)
                printed_intro = True
            print_main_screen(config, print_func, cwd=root)
            choice = prompt_main_action(config, cwd=root, input_func=input_func, print_func=print_func)
            if choice == "start":
                exit_code = start_conversion(config, cwd=root, execute=execute, input_func=input_func, print_func=print_func)
                if exit_code is not None:
                    return exit_code
            elif choice == "ebook":
                configure_ebook(config, cwd=root, input_func=input_func, print_func=print_func)
            elif choice == "model":
                configure_model(config, input_func=input_func, getpass_func=getpass_func, print_func=print_func)
            elif choice == "options":
                prompt_options_menu(config, root=root, input_func=input_func, print_func=print_func)
            elif choice == "language":
                configure_language(config, input_func=input_func, print_func=print_func)
            elif choice == "exit":
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
    finally:
        save_wizard_snapshot(config, root)


def maybe_apply_discovered_style_css(config: WizardConfig, cwd: Path) -> WizardConfig:
    if config.layout != "clean" or config.style_css is not None:
        return config
    found = discover_style_css(cwd)
    return replace(config, style_css=found) if found is not None else config


def initial_config(seed: SeedArgs, cwd: Path) -> WizardConfig:
    fresh = wizard_config_from_seed(seed, cwd)
    loaded = load_wizard_snapshot(cwd)
    base = (
        merge_loaded_wizard_into_fresh(loaded, fresh, seed_has_input=seed.input is not None, seed_has_output=seed.output is not None)
        if loaded
        else fresh
    )
    return maybe_apply_discovered_style_css(base, cwd)


def use_questionary_input(input_func: InputFunc) -> bool:
    return input_func is input and sys.stdin.isatty() and sys.stdout.isatty()


def print_intro(config: WizardConfig, print_func: PrintFunc) -> None:
    if config.session_was_restored:
        print_func(t(config.ui_lang, "session_loaded"))


def print_main_screen(
    config: WizardConfig,
    print_func: PrintFunc,
    *,
    cwd: Path | None = None,
) -> None:
    print_func("")
    for line in render_home_lines(config, cwd=cwd):
        print_func(line)


def render_home_lines(config: WizardConfig, *, cwd: Path | None = None) -> list[str]:
    lang = config.ui_lang
    errors = readiness_errors(config, cwd)
    if errors:
        status = f"{t(lang, 'needs_setup')}: {'; '.join(errors)}"
    elif cache_available(config, cwd):
        status = f"{t(lang, 'ready')}, {t(lang, 'resume_ready')}"
    else:
        status = f"{t(lang, 'ready')}, {t(lang, 'will_dry_run')}"

    model = f"{provider_name_for_config(config)} / {model_summary(config, lang)} / {t(lang, 'api_key')}: {api_key_status(config.api_key, lang, required=config_requires_api_key(config))}"
    return [
        t(lang, "title"),
        f"{t(lang, 'status')}: {status}",
        "",
        f"{t(lang, 'ebook')}: {path_default_text(config.input_path) or t(lang, 'not_selected')}",
        f"{t(lang, 'output')}: {display_output_path(config)}",
        f"{t(lang, 'model')}: {model}",
        f"{t(lang, 'menu_options')}: {default_options_summary(config, lang)}",
    ]


def prompt_main_action(
    config: WizardConfig,
    *,
    cwd: Path | None,
    input_func: InputFunc,
    print_func: PrintFunc,
) -> str:
    lang = config.ui_lang
    return prompt_menu(
        t(lang, "next_action"),
        [
            MenuChoice("start", start_menu_label(config, cwd, lang)),
            MenuChoice("ebook", t(lang, "menu_ebook")),
            MenuChoice("model", t(lang, "menu_model")),
            MenuChoice("options", t(lang, "menu_options")),
            MenuChoice("language", f"{t(lang, 'language_menu')}: {current_language_name(config)}"),
            MenuChoice("exit", t(lang, "menu_exit")),
        ],
        input_func=input_func,
        print_func=print_func,
        lang=lang,
    )


def config_requires_api_key(config: WizardConfig) -> bool:
    if config.mock:
        return False
    template = provider_template_for_config(config)
    if template is not None:
        return template.api_key_required
    return not is_ollama_base_url(config.base_url)


def readiness_errors(config: WizardConfig, cwd: Path | None) -> list[str]:
    if cwd is not None:
        return validate_start_config(config, cwd)
    errors: list[str] = []
    if config.input_path is None:
        errors.append(t(config.ui_lang, "epub_required"))
    elif config.input_path.suffix.lower() != ".epub":
        errors.append(t(config.ui_lang, "epub_suffix"))
    if not config.mock:
        if not config.model:
            errors.append(t(config.ui_lang, "model_required"))
        if config_requires_api_key(config) and not config.api_key:
            errors.append(t(config.ui_lang, "api_key_required"))
    return errors


def start_menu_label(config: WizardConfig, cwd: Path | None, lang: UiLang) -> str:
    _ = (config, cwd)
    return t(lang, "menu_start")


def model_summary(config: WizardConfig, lang: UiLang) -> str:
    if config.mock:
        return f"{t(lang, 'mock_translator')}: {yes_no(True, lang)}"
    return config.model or f"({t(lang, 'not_set')})"


def default_options_summary(config: WizardConfig, lang: UiLang) -> str:
    parts = [
        f"{t(lang, 'layout')}: {config.layout}",
        f"{t(lang, 'batch')}: {config.batch_size}",
        f"{t(lang, 'concurrency')}: {config.concurrency}",
    ]
    if config.mock:
        parts.append(f"{t(lang, 'mock')}: {yes_no(True, lang)}")
    return " | ".join(parts)


def cache_status_text(config: WizardConfig, cwd: Path | None, lang: UiLang) -> str:
    cache_path = effective_cache_path(config)
    if cache_path is None:
        return t(lang, "auto")
    label = path_default_text(cache_path)
    return f"{label} ({t(lang, 'resume_ready') if cache_available(config, cwd) else t(lang, 'no_cache_yet')})"


def cache_available(config: WizardConfig, cwd: Path | None) -> bool:
    cache_path = effective_cache_path(config)
    if cache_path is None:
        return False
    check_path = cache_path if cache_path.is_absolute() or cwd is None else cwd / cache_path
    return check_path.exists() and check_path.is_file()


def effective_cache_path(config: WizardConfig) -> Path | None:
    if config.cache_path is not None:
        return config.cache_path
    output_path = effective_output_path(config)
    if output_path is None:
        return None
    return output_path.with_suffix(output_path.suffix + ".translation-cache.json")


def effective_output_path(config: WizardConfig) -> Path | None:
    if config.output_path is not None:
        return config.output_path
    if config.input_path is None:
        return None
    if config.work_dir is not None:
        return config.work_dir / default_output_path(config.input_path).name
    return default_output_path(config.input_path)


def menu_label(label: str, detail: str, lang: UiLang) -> str:
    return f"{label}{parenthesize(detail, lang)}"


def parenthesize(text: str, lang: UiLang) -> str:
    if lang == "zh":
        return f"（{text}）"
    return f" ({text})"


def prompt_menu(
    title: str,
    entries: list[MenuEntry],
    *,
    input_func: InputFunc,
    print_func: PrintFunc,
    lang: UiLang,
) -> str:
    choices = [entry for entry in entries if isinstance(entry, MenuChoice)]
    while True:
        print_func("")
        print_func(title)
        print_func(t(lang, "select_hint"))
        index_by_number: dict[str, str] = {}
        number = 1
        needs_section_gap = False
        for entry in entries:
            if isinstance(entry, MenuSection):
                if needs_section_gap:
                    print_func("")
                suffix = "" if entry.label.endswith(":") else ":"
                print_func(f"{entry.label}{suffix}")
                needs_section_gap = False
            elif entry.value in {"back", "exit"}:
                print_func(f"  0. {entry.label}")
                needs_section_gap = True
            else:
                print_func(f"  {number}. {entry.label}")
                index_by_number[str(number)] = entry.value
                number += 1
                needs_section_gap = True
        raw = prompt_text(t(lang, "select"), "", input_func=input_func)
        if raw in index_by_number:
            return index_by_number[raw]
        if raw == "0":
            for entry in choices:
                if entry.value in {"back", "exit"}:
                    return entry.value
        for entry in choices:
            if raw == entry.value:
                return raw
        print_func(t(lang, "choose_menu"))


def configure_language(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    while True:
        lang = config.ui_lang
        choice = prompt_menu(
            f"{t(lang, 'language_menu_title')} ({t(lang, 'current_language')}: {current_language_name(config)})",
            [
                MenuChoice("zh", "中文"),
                MenuChoice("en", "English"),
                MenuChoice("back", t(lang, "back")),
            ],
            input_func=input_func,
            print_func=print_func,
            lang=lang,
        )
        if choice == "zh":
            config.ui_lang = "zh"
            print_func(t(config.ui_lang, "language_set_zh"))
            return
        if choice == "en":
            config.ui_lang = "en"
            print_func(t(config.ui_lang, "language_set_en"))
            return
        if choice == "back":
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
        books = list_epub_paths(cwd)
        entries: list[MenuEntry] = []
        if books:
            entries.append(MenuSection(t(lang, "available_books")))
            entries.extend(MenuChoice(f"book:{index}", str(path)) for index, path in enumerate(books))
        entries.extend(
            [
                MenuChoice("manual", t(lang, "enter_epub_path")),
                MenuChoice("output", menu_label(t(lang, "menu_output"), display_output_path(config), lang)),
                MenuChoice("back", t(lang, "back")),
            ]
        )
        title = f"{t(lang, 'menu_ebook')} ({t(lang, 'current_ebook')}: {path_default_text(config.input_path) or '(' + t(lang, 'not_selected') + ')'})"
        choice = prompt_menu(title, entries, input_func=input_func, print_func=print_func, lang=lang)
        if choice == "back":
            return
        if choice.startswith("book:"):
            config.input_path = books[int(choice.split(":", 1)[1])]
            print_func(f"{t(lang, 'selected_ebook')}: {config.input_path}")
            continue
        if choice == "manual":
            config.input_path = prompt_epub_path(
                config.input_path,
                input_func=input_func,
                print_func=print_func,
                cwd=cwd,
                lang=lang,
            )
        if choice == "output":
            configure_output(config, input_func=input_func, print_func=print_func)


def configure_output(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    while True:
        lang = config.ui_lang
        choice = prompt_menu(
            f"{t(lang, 'output_menu_title')} ({t(lang, 'current_output')}: {display_output_path(config)})",
            [
                MenuChoice("custom", t(lang, "set_output_path")),
                MenuChoice("auto", t(lang, "auto_output_path")),
                MenuChoice("back", t(lang, "back")),
            ],
            input_func=input_func,
            print_func=print_func,
            lang=lang,
        )
        if choice == "custom":
            config.output_path = prompt_output_path(config.output_path, input_func=input_func, lang=lang)
        elif choice == "auto":
            config.output_path = None
            print_func(t(lang, "output_auto"))
        elif choice == "back":
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
        title = (
            f"{t(lang, 'menu_model')} "
            f"({t(lang, 'model')}: {config.model or t(lang, 'not_set')}; "
            f"{t(lang, 'api_key')}: {api_key_status(config.api_key, lang, required=config_requires_api_key(config))})"
        )
        choice = prompt_menu(
            title,
            [
                MenuChoice("provider", f"{t(lang, 'choose_provider')}: {provider_name_for_config(config)}"),
                MenuChoice("base_url", f"{t(lang, 'base_url')}: {config.base_url}"),
                MenuChoice("model", f"{t(lang, 'model')}: {config.model or '(' + t(lang, 'not_set') + ')'}"),
                MenuChoice("api_key", f"{t(lang, 'api_key')}: {api_key_status(config.api_key, lang, required=config_requires_api_key(config))}"),
                MenuSection(t(lang, "advanced_model_settings")),
                MenuChoice("source_lang", f"{t(lang, 'source_language')}: {config.source_lang}"),
                MenuChoice("target_lang", f"{t(lang, 'target_language')}: {config.target_lang}"),
                MenuChoice("back", t(lang, "back")),
            ],
            input_func=input_func,
            print_func=print_func,
            lang=lang,
        )
        if choice == "provider":
            configure_provider_template(config, input_func=input_func, print_func=print_func)
        elif choice == "base_url":
            config.base_url = prompt_text(t(lang, "base_url"), config.base_url, input_func=input_func)
            if config.provider_id != "ollama":
                config.provider_id = provider_id_for_base_url(config.base_url)
        elif choice == "model":
            configure_model_name(config, input_func=input_func, print_func=print_func)
        elif choice == "api_key":
            config.api_key = prompt_secret(t(lang, "api_key"), config.api_key, getpass_func=getpass_func, lang=lang)
        elif choice == "source_lang":
            config.source_lang = prompt_text(t(lang, "source_language"), config.source_lang, input_func=input_func)
        elif choice == "target_lang":
            config.target_lang = prompt_text(t(lang, "target_language"), config.target_lang, input_func=input_func)
        elif choice == "back":
            return
        else:
            print_func(t(lang, "choose_menu"))


def provider_template_for_config(config: WizardConfig) -> ProviderTemplate | None:
    template = provider_template_by_id(config.provider_id)
    if template is not None:
        return template
    provider_id = provider_id_for_base_url(config.base_url)
    return provider_template_by_id(provider_id)


def provider_name_for_config(config: WizardConfig) -> str:
    template = provider_template_for_config(config)
    if template is not None:
        return template.name
    return "Custom"


def configure_provider_template(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    lang = config.ui_lang
    entries: list[MenuEntry] = [
        MenuChoice(f"provider:{template.id}", f"{template.name} - {template.default_model or t(lang, 'auto')}")
        for template in PROVIDER_TEMPLATES
    ]
    entries.extend(
        [
            MenuChoice("custom", t(lang, "custom_provider")),
            MenuChoice("back", t(lang, "back")),
        ]
    )
    choice = prompt_menu(
        t(lang, "choose_provider"),
        entries,
        input_func=input_func,
        print_func=print_func,
        lang=lang,
    )
    if choice == "back":
        return
    if choice == "custom":
        config.provider_id = None
        config.base_url = prompt_text(t(lang, "base_url"), config.base_url, input_func=input_func)
        config.model = prompt_text(t(lang, "model"), config.model, input_func=input_func)
        return
    if choice.startswith("provider:"):
        template_id = choice.split(":", 1)[1]
        template = next(template for template in PROVIDER_TEMPLATES if template.id == template_id)
        apply_provider_template(config, template)
        if template.id == "ollama":
            configure_ollama_model(config, input_func=input_func, print_func=print_func)
        print_func(f"{t(lang, 'provider_applied')}: {template.name}")


def configure_ollama_model(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> bool:
    lang = config.ui_lang
    try:
        models = fetch_ollama_models(config.base_url)
    except (OSError, ValueError, error.URLError) as exc:
        print_func(f"{t(lang, 'ollama_fetch_failed')}: {exc}")
        return False
    if not models:
        print_func(t(lang, "ollama_no_models"))
        return False
    if len(models) == 1:
        config.model = models[0]
        return True
    entries: list[MenuEntry] = [MenuChoice(f"model:{model}", model) for model in models]
    entries.extend([MenuChoice("custom", t(lang, "custom_model")), MenuChoice("back", t(lang, "back"))])
    choice = prompt_menu(
        t(lang, "ollama_models"),
        entries,
        input_func=input_func,
        print_func=print_func,
        lang=lang,
    )
    if choice == "custom":
        config.model = prompt_text(t(lang, "model"), config.model, input_func=input_func)
        return True
    elif choice.startswith("model:"):
        config.model = choice.split(":", 1)[1]
        return True
    return False


def apply_provider_template(config: WizardConfig, template: ProviderTemplate) -> None:
    config.provider_id = template.id
    config.base_url = template.base_url
    config.model = template.default_model
    if template.input_price_per_1m is not None:
        config.input_price_per_1m = template.input_price_per_1m
    if template.output_price_per_1m is not None:
        config.output_price_per_1m = template.output_price_per_1m
    config.price_currency = template.price_currency
    if template.output_token_ratio is not None:
        config.output_token_ratio = template.output_token_ratio
    if template.recommended_batch_size is not None:
        config.batch_size = template.recommended_batch_size
    if template.recommended_concurrency is not None:
        config.concurrency = template.recommended_concurrency


def configure_model_name(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    lang = config.ui_lang
    if config.provider_id == "ollama" or is_ollama_base_url(config.base_url):
        configure_ollama_model(config, input_func=input_func, print_func=print_func)
        return
    template = provider_template_for_config(config)
    if template is None or not template.models:
        config.model = prompt_text(t(lang, "model"), config.model, input_func=input_func)
        return
    entries: list[MenuEntry] = [MenuChoice(f"model:{model}", model) for model in template.models]
    entries.extend([MenuChoice("custom", t(lang, "custom_model")), MenuChoice("back", t(lang, "back"))])
    choice = prompt_menu(
        t(lang, "model"),
        entries,
        input_func=input_func,
        print_func=print_func,
        lang=lang,
    )
    if choice == "back":
        return
    if choice == "custom":
        config.model = prompt_text(t(lang, "model"), config.model, input_func=input_func)
    elif choice.startswith("model:"):
        config.model = choice.split(":", 1)[1]


def configure_conversion(config: WizardConfig, *, input_func: InputFunc, print_func: PrintFunc) -> None:
    while True:
        lang = config.ui_lang
        title = f"{t(lang, 'menu_conversion')} ({t(lang, 'layout')}: {config.layout} - {layout_description(config.layout, lang)})"
        choice = prompt_menu(
            title,
            [
                MenuChoice("layout", f"{t(lang, 'layout')}: {config.layout} ({layout_description(config.layout, lang)})"),
                MenuChoice("mock", f"{t(lang, 'mock_translator')}: {yes_no(config.mock, lang)}"),
                MenuChoice("number_headings", f"{t(lang, 'number_headings')}: {yes_no(config.number_headings, lang)}"),
                MenuChoice("style_css", f"{t(lang, 'style_css')}: {path_default_text(config.style_css) or '(' + t(lang, 'default') + ')'}"),
                MenuChoice("back", t(lang, "back")),
            ],
            input_func=input_func,
            print_func=print_func,
            lang=lang,
        )
        if choice == "layout":
            config.layout = prompt_layout(config.layout, input_func=input_func, print_func=print_func, lang=lang)
            if config.layout != "clean":
                config.number_headings = False
                config.style_css = None
        elif choice == "mock":
            config.mock = not config.mock
            print_func(f"{t(lang, 'mock_translator')}: {yes_no(config.mock, lang)}")
        elif choice == "number_headings":
            if config.layout != "clean":
                print_func(t(lang, "heading_numbers_require_clean"))
            else:
                config.number_headings = not config.number_headings
                print_func(f"{t(lang, 'number_headings')}: {yes_no(config.number_headings, lang)}")
        elif choice == "style_css":
            if config.layout != "clean":
                print_func(t(lang, "style_css_requires_clean"))
            else:
                config.style_css = prompt_optional_path(t(lang, "style_css"), config.style_css, input_func=input_func)
        elif choice == "back":
            return
        else:
            print_func(t(lang, "choose_menu"))


def prompt_options_menu(config: WizardConfig, *, root: Path, input_func: InputFunc, print_func: PrintFunc) -> None:
    while True:
        lang = config.ui_lang
        choice = prompt_menu(
            t(lang, "menu_options"),
            [
                MenuSection(t(lang, "menu_conversion")),
                MenuChoice("layout", f"{t(lang, 'layout')}: {config.layout} ({layout_description(config.layout, lang)})"),
                MenuChoice("mock", f"{t(lang, 'mock_translator')}: {yes_no(config.mock, lang)}"),
                MenuChoice("number_headings", f"{t(lang, 'number_headings')}: {yes_no(config.number_headings, lang)}"),
                MenuChoice("style_css", f"{t(lang, 'style_css')}: {path_default_text(config.style_css) or '(' + t(lang, 'default') + ')'}"),
                MenuSection(t(lang, "menu_options")),
                MenuChoice("batch_size", f"{t(lang, 'batch_size')}: {config.batch_size}"),
                MenuChoice("concurrency", f"{t(lang, 'concurrency')}: {config.concurrency}"),
                MenuChoice("min_chars", f"{t(lang, 'min_chars')}: {config.min_chars}"),
                MenuChoice("timeout", f"{t(lang, 'timeout_seconds')}: {config.timeout}"),
                MenuChoice("retries", f"{t(lang, 'retries')}: {config.retries}"),
                MenuChoice("cache", f"{t(lang, 'cache_path')}: {path_default_text(config.cache_path) or t(lang, 'auto')}"),
                MenuChoice("work_dir", f"{t(lang, 'work_dir')}: {path_default_text(config.work_dir) or t(lang, 'auto')}"),
                MenuChoice("limit", f"{t(lang, 'limit_segments')}: {optional_text(config.limit) or t(lang, 'all')}"),
                MenuChoice("terminology", f"{t(lang, 'terminology_csv')}: {path_default_text(config.terminology_path) or '(' + t(lang, 'none') + ')'}"),
                MenuChoice("quiet", f"{t(lang, 'toggle_quiet')}: {yes_no(config.quiet, lang)}"),
                MenuChoice("input_price", f"{t(lang, 'input_price')}: {optional_text(config.input_price_per_1m) or '(' + t(lang, 'unset') + ')'}"),
                MenuChoice("output_price", f"{t(lang, 'output_price')}: {optional_text(config.output_price_per_1m) or '(' + t(lang, 'unset') + ')'}"),
                MenuChoice("price_currency", f"{t(lang, 'price_currency')}: {config.price_currency}"),
                MenuChoice("output_token_ratio", f"{t(lang, 'output_token_ratio')}: {config.output_token_ratio}"),
                MenuChoice("save_env", t(lang, "menu_save_env")),
                MenuChoice("back", t(lang, "back")),
            ],
            input_func=input_func,
            print_func=print_func,
            lang=lang,
        )
        if choice == "layout":
            config.layout = prompt_layout(config.layout, input_func=input_func, print_func=print_func, lang=lang)
            if config.layout != "clean":
                config.number_headings = False
                config.style_css = None
        elif choice == "mock":
            config.mock = not config.mock
            print_func(f"{t(lang, 'mock_translator')}: {yes_no(config.mock, lang)}")
        elif choice == "number_headings":
            if config.layout != "clean":
                print_func(t(lang, "heading_numbers_require_clean"))
            else:
                config.number_headings = not config.number_headings
                print_func(f"{t(lang, 'number_headings')}: {yes_no(config.number_headings, lang)}")
        elif choice == "style_css":
            if config.layout != "clean":
                print_func(t(lang, "style_css_requires_clean"))
            else:
                config.style_css = prompt_optional_path(t(lang, "style_css"), config.style_css, input_func=input_func)
        elif choice == "batch_size":
            config.batch_size = prompt_int(t(lang, "batch_size"), config.batch_size, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "concurrency":
            config.concurrency = prompt_int(t(lang, "concurrency"), config.concurrency, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "min_chars":
            config.min_chars = prompt_int(t(lang, "min_chars"), config.min_chars, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "timeout":
            config.timeout = prompt_int(t(lang, "timeout_seconds"), config.timeout, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "retries":
            config.retries = prompt_int(t(lang, "retries"), config.retries, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "cache":
            config.cache_path = prompt_optional_path(t(lang, "cache_path"), config.cache_path, input_func=input_func)
        elif choice == "work_dir":
            config.work_dir = prompt_optional_path(t(lang, "work_dir"), config.work_dir, input_func=input_func)
        elif choice == "limit":
            config.limit = prompt_optional_int(t(lang, "limit_segments"), config.limit, input_func=input_func, print_func=print_func, lang=lang)
        elif choice == "terminology":
            config.terminology_path = prompt_optional_path(t(lang, "terminology_csv"), config.terminology_path, input_func=input_func)
        elif choice == "quiet":
            config.quiet = not config.quiet
            print_func(f"{t(lang, 'quiet')}: {yes_no(config.quiet, lang)}")
        elif choice == "input_price":
            config.input_price_per_1m = prompt_optional_float(
                t(lang, "input_price"),
                config.input_price_per_1m,
                input_func=input_func,
                print_func=print_func,
                lang=lang,
            )
        elif choice == "output_price":
            config.output_price_per_1m = prompt_optional_float(
                t(lang, "output_price"),
                config.output_price_per_1m,
                input_func=input_func,
                print_func=print_func,
                lang=lang,
            )
        elif choice == "price_currency":
            config.price_currency = prompt_text(t(lang, "price_currency"), config.price_currency, input_func=input_func)
        elif choice == "output_token_ratio":
            config.output_token_ratio = prompt_float(
                t(lang, "output_token_ratio"),
                config.output_token_ratio,
                input_func=input_func,
                print_func=print_func,
                lang=lang,
            )
        elif choice == "save_env":
            save_env_defaults(config, root, input_func=input_func, print_func=print_func)
        elif choice == "back":
            return
        else:
            print_func(t(lang, "choose_menu"))


def start_conversion(
    config: WizardConfig,
    *,
    cwd: Path,
    execute: ExecuteFunc | None,
    input_func: InputFunc,
    print_func: PrintFunc,
) -> int | None:
    lang = config.ui_lang
    errors = validate_start_config(config, cwd)
    if errors:
        print_errors(t(lang, "cannot_start"), errors, print_func)
        return None

    print_summary(config, print_func)
    print_func("")
    if cache_available(config, cwd):
        print_func(t(lang, "cache_resume_hint"))
    print_func(t(lang, "dry_run_first"))
    dry_run_code = execute_conversion(config, cwd=cwd, dry_run=True, execute=execute)
    if dry_run_code != 0:
        print_func(f"{t(lang, 'dry_run_failed')} {dry_run_code}.")
        return dry_run_code

    if not confirm(t(lang, "start_real"), default=False, input_func=input_func, print_func=print_func, lang=lang):
        print_func(t(lang, "stopped_after_dry_run"))
        return None

    return execute_conversion(config, cwd=cwd, dry_run=False, execute=execute)


def execute_conversion(
    config: WizardConfig,
    *,
    cwd: Path,
    dry_run: bool,
    execute: ExecuteFunc | None,
) -> int:
    if execute is not None:
        return execute(build_conversion_args(config, dry_run=dry_run))

    from .cli import print_conversion_result, print_dry_run_result, print_progress

    options = conversion_options_from_config(config, cwd=cwd, dry_run=dry_run)
    if dry_run:
        dry_run_result = run_dry_run(options)
        print_dry_run_result(dry_run_result, options)
        return 0

    progress_callback = None if config.quiet else print_progress
    conversion_result = run_conversion(options, progress_callback=progress_callback)
    print_conversion_result(conversion_result, options)
    return 0


def conversion_options_from_config(config: WizardConfig, *, cwd: Path, dry_run: bool) -> ConversionOptions:
    return ConversionOptions(
        input_path=config.input_path,
        output_path=config.output_path,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        source_lang=config.source_lang,
        target_lang=config.target_lang,
        layout=config.layout,
        style_css=config.style_css,
        number_headings=config.number_headings,
        dry_run=dry_run,
        mock=config.mock,
        batch_size=config.batch_size,
        concurrency=config.concurrency,
        min_chars=config.min_chars,
        timeout=config.timeout,
        retries=config.retries,
        cache_path=config.cache_path,
        work_dir=config.work_dir,
        limit=config.limit,
        terminology_path=config.terminology_path,
        quiet=config.quiet,
        input_price_per_1m=config.input_price_per_1m,
        output_price_per_1m=config.output_price_per_1m,
        price_currency=config.price_currency,
        output_token_ratio=config.output_token_ratio,
        cwd=cwd,
    )


def print_errors(title: str, errors: list[str], print_func: PrintFunc) -> None:
    print_func("")
    print_func(title)
    for message in errors:
        print_func(f"  - {message}")


def validate_start_config(config: WizardConfig, cwd: Path) -> list[str]:
    errors = validate_epub_path(config.input_path, cwd, config.ui_lang)
    if not config.mock:
        if not config.model:
            errors.append(t(config.ui_lang, "model_required"))
        if config_requires_api_key(config) and not config.api_key:
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
        value = prompt_path_value(t(lang, "input_epub"), default, input_func=input_func).strip()
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
        for validation_error in errors:
            print_func(validation_error)


def prompt_layout(default: str, *, input_func: InputFunc, print_func: PrintFunc, lang: UiLang) -> str:
    if use_questionary_input(input_func):
        answer = questionary.select(
            t(lang, "layout"),
            choices=[
                Choice(f"preserve - {t(lang, 'preserve_desc')}", value="preserve"),
                Choice(f"clean - {t(lang, 'clean_desc')}", value="clean"),
            ],
            default=default,
            qmark="",
            style=QUESTIONARY_STYLE,
        ).ask()
        if answer is None:
            raise EOFError
        return str(answer)
    print_func(f"  preserve = {t(lang, 'preserve_desc')}")
    print_func(f"  clean    = {t(lang, 'clean_desc')}")
    return prompt_choice(t(lang, "layout"), ("preserve", "clean"), default, input_func=input_func, print_func=print_func, lang=lang)


def prompt_output_path(default: Path | None, *, input_func: InputFunc, lang: UiLang) -> Path | None:
    value = prompt_path_value(t(lang, "custom_output_epub"), default, input_func=input_func).strip()
    return Path(value).expanduser() if value else default


def prompt_text(label: str, default: str, *, input_func: InputFunc) -> str:
    if use_questionary_input(input_func):
        answer = questionary.text(label, default=default, style=QUESTIONARY_STYLE).ask()
        if answer is None:
            raise EOFError
        return answer.strip() or default
    value = input_func(f"{label}{format_default(default)}: ").strip()
    return value or default


def prompt_secret(label: str, default: str, *, getpass_func: SecretFunc, lang: UiLang) -> str:
    if getpass_func is getpass.getpass and sys.stdin.isatty() and sys.stdout.isatty():
        answer = questionary.password(label, style=QUESTIONARY_STYLE).ask()
        if answer is None:
            raise EOFError
        return answer.strip() or default
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
    if use_questionary_input(input_func):
        answer = questionary.confirm(label, default=default, style=QUESTIONARY_STYLE).ask()
        if answer is None:
            raise EOFError
        return bool(answer)
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
        value = prompt_text(label, optional_text(default), input_func=input_func).strip()
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
        value = prompt_text(label, optional_text(default), input_func=input_func).strip()
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            print_func(f"{label} {t(lang, 'must_number')}")


def prompt_optional_path(label: str, default: Path | None, *, input_func: InputFunc) -> Path | None:
    value = prompt_path_value(label, default, input_func=input_func).strip()
    if not value:
        return default
    return Path(value).expanduser()


def prompt_path_value(label: str, default: Path | None, *, input_func: InputFunc) -> str:
    default_text = path_default_text(default)
    if use_questionary_input(input_func):
        answer = questionary.path(label, default=default_text, style=QUESTIONARY_STYLE).ask()
        if answer is None:
            raise EOFError
        return answer
    return input_func(f"{label}{format_default(default_text)}: ")


def optional_text(value: object | None) -> str:
    return "" if value is None else str(value)


def path_default_text(value: Path | None) -> str:
    return "" if value is None else str(value)


def format_default(default: str) -> str:
    return f" [{default}]" if default else ""


def yes_no(value: bool, lang: UiLang) -> str:
    return t(lang, "yes") if value else t(lang, "no")


def print_summary(config: WizardConfig, print_func: PrintFunc) -> None:
    lang = config.ui_lang
    command = shlex.join(["ebook-bilingual", *redact_args(build_conversion_args(config, dry_run=False))])
    print_func("")
    print_func(t(lang, "command_preview"))
    print_func("  " + command)


def display_output_path(config: WizardConfig) -> str:
    lang = config.ui_lang
    if config.output_path is not None:
        return str(config.output_path)
    if config.input_path is None:
        return parenthesize(t(lang, "auto_after_ebook"), lang)
    if config.work_dir is not None:
        return f"{config.work_dir / default_output_path(config.input_path).name}{parenthesize(t(lang, 'auto'), lang)}"
    return f"{default_output_path(config.input_path)}{parenthesize(t(lang, 'auto'), lang)}"


def api_key_status(api_key: str, lang: UiLang, *, required: bool = True) -> str:
    if not required and not api_key:
        return t(lang, "not_required")
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
