from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
import time

from .epub import (
    ConversionStats,
    DryRunStats,
    ProgressCallback,
    analyze_epub,
    convert_epub_to_bilingual,
)
from .llm import (
    CachedTranslator,
    MockTranslator,
    is_ollama_base_url,
    OpenAICompatibleTranslator,
    TranslationCache,
    Translator,
    cache_key,
    load_terminology,
    terminology_fingerprint,
)
from .paths import copy_into_work_dir, discover_style_css, prepare_run_paths
from .pricing import resolve_prices


@dataclass(frozen=True)
class ConversionOptions:
    input_path: Path | None
    output_path: Path | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    source_lang: str = "auto"
    target_lang: str = "Simplified Chinese"
    layout: str = "preserve"
    style_css: Path | None = None
    number_headings: bool = False
    dry_run: bool = False
    mock: bool = False
    batch_size: int = 8
    concurrency: int = 1
    min_chars: int = 2
    timeout: int = 120
    retries: int = 3
    cache_path: Path | None = None
    work_dir: Path | None = None
    limit: int | None = None
    terminology_path: Path | None = None
    quiet: bool = False
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    price_currency: str = "USD"
    output_token_ratio: float = 1.15
    fail_on_skipped: bool = False
    verbose: bool = False
    profile: bool = False
    cwd: Path = field(default_factory=Path.cwd)


@dataclass
class PreparedConversion:
    input_path: Path
    output_path: Path
    cache_path: Path
    cache: TranslationCache
    model_name: str
    cache_namespace: str
    style_css: str | None
    input_price: float | None
    output_price: float | None
    raw_translator: Translator | None


@dataclass
class DryRunResult:
    stats: DryRunStats
    input_price: float | None
    output_price: float | None
    price_currency: str
    profile_timings: dict[str, float] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return 1 if self.stats.skipped_documents else 0


@dataclass
class ConversionRunResult:
    output_path: Path
    cache_path: Path
    stats: ConversionStats
    profile_timings: dict[str, float] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return 1 if self.stats.skipped_documents else 0


class ConversionConfigError(ValueError):
    pass


def options_from_namespace(args: Namespace, *, cwd: Path | None = None) -> ConversionOptions:
    return ConversionOptions(
        input_path=args.input,
        output_path=args.output,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        layout=args.layout,
        style_css=args.style_css,
        number_headings=args.number_headings,
        dry_run=args.dry_run,
        mock=args.mock,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        min_chars=args.min_chars,
        timeout=args.timeout,
        retries=args.retries,
        cache_path=args.cache,
        work_dir=args.work_dir,
        limit=args.limit,
        terminology_path=args.terminology,
        quiet=args.quiet,
        input_price_per_1m=args.input_price_per_1m,
        output_price_per_1m=args.output_price_per_1m,
        price_currency=args.price_currency,
        output_token_ratio=args.output_token_ratio,
        fail_on_skipped=args.fail_on_skipped,
        verbose=args.verbose,
        profile=args.profile,
        cwd=cwd or Path.cwd(),
    )


def run_dry_run(options: ConversionOptions) -> DryRunResult:
    validate_options(options)
    profile_timings: dict[str, float] = {}
    prepared = prepare_conversion(options, need_translator=False)

    started = time.perf_counter()
    stats = analyze_epub(
        prepared.input_path,
        batch_size=options.batch_size,
        min_chars=options.min_chars,
        limit=options.limit,
        output_token_ratio=options.output_token_ratio,
        is_cached=lambda text: prepared.cache.get(
            cache_key(prepared.model_name, options.source_lang, options.target_lang, text, prepared.cache_namespace)
        )
        is not None,
    )
    add_timing(profile_timings, "plan", started)

    return DryRunResult(
        stats=stats,
        input_price=prepared.input_price,
        output_price=prepared.output_price,
        price_currency=options.price_currency,
        profile_timings=profile_timings,
    )


def run_conversion(
    options: ConversionOptions,
    *,
    progress_callback: ProgressCallback | None = None,
) -> ConversionRunResult:
    validate_options(options)
    profile_timings: dict[str, float] = {}
    prepared = prepare_conversion(options, need_translator=True)
    assert prepared.raw_translator is not None

    translator = CachedTranslator(
        prepared.raw_translator,
        prepared.cache,
        model=prepared.model_name,
        source_language=options.source_lang,
        target_language=options.target_lang,
        cache_namespace=prepared.cache_namespace,
        autosave=False,
    )

    stats: ConversionStats | None = None
    try:
        stats = convert_epub_to_bilingual(
            prepared.input_path,
            prepared.output_path,
            translator,
            batch_size=options.batch_size,
            min_chars=options.min_chars,
            limit=options.limit,
            concurrency=options.concurrency,
            layout=options.layout,
            style_css=prepared.style_css,
            number_headings=options.number_headings,
            progress_callback=progress_callback,
            profile_timings=profile_timings,
        )
    finally:
        started = time.perf_counter()
        prepared.cache.save()
        add_timing(profile_timings, "cache_save", started)

    assert stats is not None
    return ConversionRunResult(
        output_path=prepared.output_path,
        cache_path=prepared.cache_path,
        stats=stats,
        profile_timings=profile_timings,
    )


def validate_options(options: ConversionOptions) -> None:
    if options.input_path is None:
        raise ConversionConfigError("input is required unless --interactive is used")
    input_path = resolve_path(options.input_path, options.cwd)
    if not input_path.exists():
        raise ConversionConfigError(f"Input file does not exist: {options.input_path}")
    if options.output_path is not None and resolve_path(options.output_path, options.cwd).resolve() == input_path.resolve():
        raise ConversionConfigError("Output file must be different from input file")
    if options.batch_size < 1:
        raise ConversionConfigError("--batch-size must be >= 1")
    if options.concurrency < 1:
        raise ConversionConfigError("--concurrency must be >= 1")
    if options.min_chars < 1:
        raise ConversionConfigError("--min-chars must be >= 1")
    if options.timeout < 1:
        raise ConversionConfigError("--timeout must be >= 1")
    if options.retries < 1:
        raise ConversionConfigError("--retries must be >= 1")
    if options.limit is not None and options.limit < 0:
        raise ConversionConfigError("--limit must be >= 0")
    if options.output_token_ratio <= 0:
        raise ConversionConfigError("--output-token-ratio must be > 0")
    if options.style_css is not None and options.layout != "clean":
        raise ConversionConfigError("--style-css requires --layout clean")
    if options.number_headings and options.layout != "clean":
        raise ConversionConfigError("--number-headings requires --layout clean")
    if options.input_price_per_1m is not None and options.input_price_per_1m < 0:
        raise ConversionConfigError("--input-price-per-1m must be >= 0")
    if options.output_price_per_1m is not None and options.output_price_per_1m < 0:
        raise ConversionConfigError("--output-price-per-1m must be >= 0")
    if options.terminology_path is not None and not resolve_path(options.terminology_path, options.cwd).exists():
        raise ConversionConfigError(f"Terminology file does not exist: {options.terminology_path}")
    if options.style_css is not None and not resolve_path(options.style_css, options.cwd).exists():
        raise ConversionConfigError(f"Style CSS file does not exist: {options.style_css}")
    if not options.mock and not options.dry_run:
        if not options.model:
            raise ConversionConfigError("--model is required unless LLM_MODEL is set")
        if not options.api_key and not is_ollama_base_url(options.base_url):
            raise ConversionConfigError("--api-key is required unless LLM_API_KEY or OPENAI_API_KEY is set")


def prepare_conversion(options: ConversionOptions, *, need_translator: bool) -> PreparedConversion:
    input_arg = require_path(options.input_path)
    input_path = resolve_path(input_arg, options.cwd)
    output_path = resolve_path(options.output_path, options.cwd) if options.output_path is not None else None
    cache_path = resolve_path(options.cache_path, options.cwd) if options.cache_path is not None else None
    work_dir = resolve_path(options.work_dir, options.cwd) if options.work_dir is not None else None
    terminology_path = resolve_path(options.terminology_path, options.cwd) if options.terminology_path is not None else None
    style_css_path = resolve_path(options.style_css, options.cwd) if options.style_css is not None else None

    run_input_path, run_output_path, run_cache_path = prepare_run_paths(input_path, output_path, cache_path, work_dir)
    if run_output_path.resolve() == run_input_path.resolve():
        raise ConversionConfigError("Output file must be different from input file")

    terminology = []
    if terminology_path is not None:
        terminology = load_terminology(copy_into_work_dir(terminology_path, work_dir))
    cache_namespace = terminology_fingerprint(terminology)

    style_css = None
    if options.layout == "clean" and style_css_path is None:
        discovered = discover_style_css(options.cwd)
        if discovered is not None:
            style_css_path = discovered
    if style_css_path is not None:
        style_css = copy_into_work_dir(style_css_path, work_dir).read_text(encoding="utf-8")

    raw_translator: Translator | None = None
    if options.mock:
        raw_translator = MockTranslator() if need_translator else None
        model_name = "mock"
    else:
        model_name = options.model or "unknown"
        if need_translator:
            raw_translator = OpenAICompatibleTranslator(
                api_key=options.api_key,
                model=require_model(options.model),
                base_url=options.base_url,
                source_language=options.source_lang,
                target_language=options.target_lang,
                timeout=options.timeout,
                retries=options.retries,
                terminology=terminology,
            )

    cache = TranslationCache.load(run_cache_path)
    input_price, output_price = resolve_prices(
        options.model,
        options.base_url,
        options.input_price_per_1m,
        options.output_price_per_1m,
    )
    return PreparedConversion(
        input_path=run_input_path,
        output_path=run_output_path,
        cache_path=run_cache_path,
        cache=cache,
        model_name=model_name,
        cache_namespace=cache_namespace,
        style_css=style_css,
        input_price=input_price,
        output_price=output_price,
        raw_translator=raw_translator,
    )


def resolve_path(path: Path, cwd: Path) -> Path:
    if path.is_absolute():
        return path
    try:
        if cwd.resolve() == Path.cwd().resolve():
            return path
    except OSError:
        pass
    return cwd / path


def require_path(path: Path | None) -> Path:
    if path is None:
        raise ConversionConfigError("input is required unless --interactive is used")
    return path


def require_model(model: str | None) -> str:
    if not model:
        raise ConversionConfigError("--model is required unless LLM_MODEL is set")
    return model


def add_timing(profile_timings: dict[str, float], key: str, started: float) -> None:
    profile_timings[key] = profile_timings.get(key, 0.0) + (time.perf_counter() - started)
