from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
from typing import Any

from .cli import main as cli_main, optional_float_env
from .config import load_env_file


LAYOUT_CHOICES = ("preserve", "clean")


@dataclass
class TuiConfig:
    input_path: str = ""
    output_path: str = ""
    work_dir: str = ""
    cache_path: str = ""
    terminology_path: str = ""
    style_css_path: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    source_lang: str = "auto"
    target_lang: str = "Simplified Chinese"
    layout: str = "clean"
    batch_size: int = 8
    concurrency: int = 1
    min_chars: int = 2
    timeout: int = 120
    retries: int = 3
    limit: int | None = None
    number_headings: bool = False
    dry_run: bool = True
    mock: bool = False
    quiet: bool = False
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    price_currency: str = "USD"
    output_token_ratio: float = 1.15


@dataclass(frozen=True)
class TuiField:
    label: str
    attr: str = ""
    kind: str = "text"
    choices: tuple[str, ...] = ()
    action: str = ""
    secret: bool = False


FIELDS = (
    TuiField("Book", kind="section"),
    TuiField("Input EPUB", "input_path"),
    TuiField("Output EPUB", "output_path"),
    TuiField("Work dir", "work_dir"),
    TuiField("Cache path", "cache_path"),
    TuiField("Terminology CSV/TSV", "terminology_path"),
    TuiField("Model", kind="section"),
    TuiField("Model name", "model"),
    TuiField("API key override", "api_key", secret=True),
    TuiField("Base URL", "base_url"),
    TuiField("Source language", "source_lang"),
    TuiField("Target language", "target_lang"),
    TuiField("Conversion", kind="section"),
    TuiField("Layout", "layout", kind="choice", choices=LAYOUT_CHOICES),
    TuiField("Style CSS", "style_css_path"),
    TuiField("Number headings", "number_headings", kind="bool"),
    TuiField("Dry run", "dry_run", kind="bool"),
    TuiField("Mock translator", "mock", kind="bool"),
    TuiField("Quiet output", "quiet", kind="bool"),
    TuiField("Batch size", "batch_size", kind="int"),
    TuiField("Concurrency", "concurrency", kind="int"),
    TuiField("Min chars", "min_chars", kind="int"),
    TuiField("Timeout seconds", "timeout", kind="int"),
    TuiField("Retries", "retries", kind="int"),
    TuiField("Limit segments", "limit", kind="optional_int"),
    TuiField("Dry-run Cost", kind="section"),
    TuiField("Input price / 1M", "input_price_per_1m", kind="optional_float"),
    TuiField("Output price / 1M", "output_price_per_1m", kind="optional_float"),
    TuiField("Currency", "price_currency"),
    TuiField("Output token ratio", "output_token_ratio", kind="float"),
    TuiField("Actions", kind="section"),
    TuiField("Run conversion", kind="action", action="run"),
    TuiField("Quit", kind="action", action="quit"),
)


def main() -> int:
    load_env_file(Path.cwd() / ".env")
    selected = run_tui(default_config())
    if selected is None:
        print("Cancelled.")
        return 0
    return cli_main(build_cli_args(selected))


def default_config(cwd: Path | None = None) -> TuiConfig:
    root = cwd or Path.cwd()
    env_style = os.getenv("LLM_STYLE_CSS")
    default_style = env_style or relative_path(root / "styles" / "eink-10.3.css", root)
    layout = os.getenv("LLM_LAYOUT") or ("clean" if default_style else "preserve")
    if layout not in LAYOUT_CHOICES:
        layout = "preserve"

    return TuiConfig(
        input_path=suggest_epub_path(root),
        style_css_path=default_style,
        model=os.getenv("LLM_MODEL", ""),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        source_lang=os.getenv("LLM_SOURCE_LANG", "auto"),
        target_lang=os.getenv("LLM_TARGET_LANG", "Simplified Chinese"),
        layout=layout,
        concurrency=int_env("LLM_CONCURRENCY", 1),
        terminology_path=os.getenv("LLM_TERMINOLOGY", ""),
        input_price_per_1m=optional_float_env("LLM_INPUT_PRICE_PER_1M"),
        output_price_per_1m=optional_float_env("LLM_OUTPUT_PRICE_PER_1M"),
        price_currency=os.getenv("LLM_PRICE_CURRENCY", "USD"),
        output_token_ratio=float_env("LLM_OUTPUT_TOKEN_RATIO", 1.15),
    )


def suggest_epub_path(cwd: Path) -> str:
    books_dir = cwd / "books"
    if not books_dir.exists():
        return ""
    for path in sorted(books_dir.glob("*.epub")):
        if ".bilingual" not in path.name:
            return relative_path(path, cwd)
    return ""


def relative_path(path: Path, cwd: Path) -> str:
    if not path.exists():
        return ""
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return str(path)


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def build_cli_args(config: TuiConfig) -> list[str]:
    args = [config.input_path]
    if config.output_path:
        args.append(config.output_path)

    append_value(args, "--model", config.model)
    append_value(args, "--api-key", config.api_key)
    append_value(args, "--base-url", config.base_url)
    append_value(args, "--source-lang", config.source_lang)
    append_value(args, "--target-lang", config.target_lang)
    append_value(args, "--batch-size", str(config.batch_size))
    append_value(args, "--concurrency", str(config.concurrency))
    append_value(args, "--min-chars", str(config.min_chars))
    append_value(args, "--timeout", str(config.timeout))
    append_value(args, "--retries", str(config.retries))
    append_value(args, "--layout", config.layout)
    append_value(args, "--work-dir", config.work_dir)
    append_value(args, "--cache", config.cache_path)
    append_value(args, "--terminology", config.terminology_path)
    if config.layout == "clean":
        append_value(args, "--style-css", config.style_css_path)
        if config.number_headings:
            args.append("--number-headings")
    if config.limit is not None:
        append_value(args, "--limit", str(config.limit))
    if config.dry_run:
        args.append("--dry-run")
    if config.mock:
        args.append("--mock")
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


def command_preview(config: TuiConfig) -> str:
    args = build_cli_args(config)
    redacted = []
    hide_next = False
    for arg in args:
        if hide_next:
            redacted.append("***")
            hide_next = False
            continue
        redacted.append(arg)
        hide_next = arg == "--api-key"
    return shlex.join(["uv", "run", "ebook-bilingual", *redacted])


def validate_config(config: TuiConfig, cwd: Path | None = None) -> str | None:
    root = cwd or Path.cwd()
    if not config.input_path.strip():
        return "Input EPUB is required."
    input_path = resolve_path(config.input_path, root)
    if not input_path.exists():
        return f"Input EPUB does not exist: {config.input_path}"
    if config.output_path.strip() and resolve_path(config.output_path, root).resolve() == input_path.resolve():
        return "Output EPUB must be different from input EPUB."
    if config.layout not in LAYOUT_CHOICES:
        return "Layout must be preserve or clean."
    if config.layout == "clean" and config.style_css_path.strip() and not resolve_path(config.style_css_path, root).exists():
        return f"Style CSS does not exist: {config.style_css_path}"
    if config.terminology_path.strip() and not resolve_path(config.terminology_path, root).exists():
        return f"Terminology file does not exist: {config.terminology_path}"
    if config.batch_size < 1:
        return "Batch size must be >= 1."
    if config.concurrency < 1:
        return "Concurrency must be >= 1."
    if config.min_chars < 1:
        return "Min chars must be >= 1."
    if config.timeout < 1:
        return "Timeout must be >= 1."
    if config.retries < 1:
        return "Retries must be >= 1."
    if config.limit is not None and config.limit < 0:
        return "Limit must be >= 0."
    if config.output_token_ratio <= 0:
        return "Output token ratio must be > 0."
    if config.input_price_per_1m is not None and config.input_price_per_1m < 0:
        return "Input price must be >= 0."
    if config.output_price_per_1m is not None and config.output_price_per_1m < 0:
        return "Output price must be >= 0."
    if not config.dry_run and not config.mock:
        if not (config.model or os.getenv("LLM_MODEL")):
            return "Model is required unless dry run or mock is enabled."
        if not (config.api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")):
            return "API key is required unless dry run or mock is enabled."
    return None


def resolve_path(value: str, cwd: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return cwd / path


def run_tui(config: TuiConfig | None = None) -> TuiConfig | None:
    import curses

    return curses.wrapper(lambda stdscr: TuiApp(stdscr, config or default_config()).run())


class TuiApp:
    def __init__(self, screen: Any, config: TuiConfig) -> None:
        self.screen = screen
        self.config = config
        self.selected = first_selectable_index()
        self.top = 0
        self.status = "Enter edits, Space toggles, Left/Right changes choices, r runs, q quits."

    def run(self) -> TuiConfig | None:
        import curses

        set_cursor_visible(curses, False)
        self.screen.keypad(True)
        while True:
            self.render()
            key = self.screen.getch()
            if key in (ord("q"), 27):
                return None
            if key in (ord("r"),):
                error = validate_config(self.config)
                if error:
                    self.status = error
                    continue
                return self.config
            if key in (curses.KEY_UP, ord("k")):
                self.move_selection(-1)
            elif key in (curses.KEY_DOWN, ord("j")):
                self.move_selection(1)
            elif key in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(" ")):
                self.adjust_field(-1 if key == curses.KEY_LEFT else 1)
            elif key in (curses.KEY_ENTER, 10, 13):
                result = self.activate_field()
                if result in {"run", "quit"}:
                    return self.config if result == "run" else None

    def render(self) -> None:
        import curses

        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < 8 or width < 40:
            self.screen.addnstr(0, 0, "Terminal too small. Resize or press q.", max(width - 1, 1))
            self.screen.refresh()
            return
        self.screen.addnstr(0, 0, "EPUB Bilingual Converter TUI", width - 1, curses.A_BOLD)
        self.screen.addnstr(1, 0, self.status, width - 1)

        list_height = max(height - 7, 1)
        self.keep_selection_visible(list_height)
        for row, field_index in enumerate(range(self.top, min(len(FIELDS), self.top + list_height)), start=3):
            field = FIELDS[field_index]
            attr = curses.A_REVERSE if field_index == self.selected else curses.A_NORMAL
            text = self.format_field(field)
            if field.kind == "section":
                attr |= curses.A_BOLD
            self.screen.addnstr(row, 0, text, width - 1, attr)

        preview = command_preview(self.config)
        self.screen.addnstr(height - 3, 0, "Command:", width - 1, curses.A_BOLD)
        self.screen.addnstr(height - 2, 0, preview, width - 1)
        self.screen.refresh()

    def format_field(self, field: TuiField) -> str:
        if field.kind == "section":
            return f"[{field.label}]"
        if field.kind == "action":
            return f"> {field.label}"
        return f"{field.label:<22} {self.display_value(field)}"

    def display_value(self, field: TuiField) -> str:
        value = getattr(self.config, field.attr)
        if field.secret:
            return "<set>" if value else "<env/default>"
        if field.kind == "bool":
            return "yes" if value else "no"
        if value is None:
            return ""
        return str(value)

    def keep_selection_visible(self, list_height: int) -> None:
        if self.selected < self.top:
            self.top = self.selected
        if self.selected >= self.top + list_height:
            self.top = self.selected - list_height + 1

    def move_selection(self, delta: int) -> None:
        selectable = selectable_indices()
        position = selectable.index(self.selected)
        self.selected = selectable[(position + delta) % len(selectable)]

    def adjust_field(self, delta: int) -> None:
        field = FIELDS[self.selected]
        if field.kind == "bool":
            setattr(self.config, field.attr, not getattr(self.config, field.attr))
        elif field.kind == "choice":
            choices = field.choices
            current = getattr(self.config, field.attr)
            index = choices.index(current) if current in choices else 0
            setattr(self.config, field.attr, choices[(index + delta) % len(choices)])

    def activate_field(self) -> str | None:
        field = FIELDS[self.selected]
        if field.kind == "action":
            if field.action == "run":
                error = validate_config(self.config)
                if error:
                    self.status = error
                    return None
            return field.action
        if field.kind in {"bool", "choice"}:
            self.adjust_field(1)
            return None
        self.edit_field(field)
        return None

    def edit_field(self, field: TuiField) -> None:
        current = self.display_value(field) if not field.secret else ""
        value = self.prompt(f"{field.label}: ", current)
        if value is None:
            return
        try:
            parsed = parse_field_value(field, value)
        except ValueError as exc:
            self.status = str(exc)
            return
        setattr(self.config, field.attr, parsed)
        self.status = f"Updated {field.label}."

    def prompt(self, label: str, current: str) -> str | None:
        import curses

        height, width = self.screen.getmaxyx()
        self.screen.move(height - 1, 0)
        self.screen.clrtoeol()
        prompt = f"{label}[{current}] "
        self.screen.addnstr(height - 1, 0, prompt, width - 1)
        curses.echo()
        set_cursor_visible(curses, True)
        try:
            raw = self.screen.getstr(height - 1, min(len(prompt), width - 2), max(width - len(prompt) - 1, 1))
        finally:
            curses.noecho()
            set_cursor_visible(curses, False)
        value = raw.decode("utf-8").strip()
        return value if value else current


def set_cursor_visible(curses_module: Any, visible: bool) -> None:
    try:
        curses_module.curs_set(1 if visible else 0)
    except curses_module.error:
        return


def parse_field_value(field: TuiField, value: str) -> object:
    if field.kind == "int":
        return int(value)
    if field.kind == "float":
        return float(value)
    if field.kind == "optional_int":
        return int(value) if value else None
    if field.kind == "optional_float":
        return float(value) if value else None
    return value


def selectable_indices() -> list[int]:
    return [index for index, field in enumerate(FIELDS) if field.kind != "section"]


def first_selectable_index() -> int:
    return selectable_indices()[0]


if __name__ == "__main__":
    raise SystemExit(main())
