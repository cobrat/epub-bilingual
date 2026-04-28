from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import load_env_file
from .epub import DryRunStats, TranslationProgress, analyze_epub, convert_epub_to_bilingual
from .llm import (
    CachedTranslator,
    MockTranslator,
    OpenAICompatibleTranslator,
    TranslationCache,
    cache_key,
    load_terminology,
    terminology_fingerprint,
)
from .paths import copy_into_work_dir, prepare_run_paths
from .pricing import resolve_prices


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ebook-bilingual",
        description="Convert an EPUB into a bilingual EPUB by inserting LLM translations under original paragraphs.",
    )
    parser.add_argument("input", type=Path, help="Input .epub file")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=None,
        help="Output bilingual .epub file. Defaults to <input>.bilingual.epub in the same directory.",
    )
    parser.add_argument("--model", default=os.getenv("LLM_MODEL"), help="LLM model name. Defaults to LLM_MODEL.")
    parser.add_argument(
        "--api-key",
        default=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        help="API key. Defaults to LLM_API_KEY or OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        help="OpenAI-compatible API base URL.",
    )
    parser.add_argument("--source-lang", default=os.getenv("LLM_SOURCE_LANG", "auto"), help="Source language hint.")
    parser.add_argument(
        "--target-lang",
        default=os.getenv("LLM_TARGET_LANG", "Simplified Chinese"),
        help="Target translation language.",
    )
    parser.add_argument("--batch-size", type=int, default=8, help="Paragraphs per LLM request.")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("LLM_CONCURRENCY", "1")),
        help="Concurrent translation requests. Defaults to LLM_CONCURRENCY or 1.",
    )
    parser.add_argument("--min-chars", type=int, default=2, help="Skip text shorter than this many characters.")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="LLM request retries.")
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="Translation cache path. Defaults to <output>.translation-cache.json.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help=(
            "Isolated directory for this book run. Input EPUB, terminology, and style CSS are copied there; "
            "default output/cache files are written there."
        ),
    )
    parser.add_argument(
        "--layout",
        choices=("preserve", "clean"),
        default=os.getenv("LLM_LAYOUT", "preserve"),
        help="EPUB layout mode. preserve keeps original XHTML/CSS; clean restyles readable bilingual XHTML.",
    )
    parser.add_argument(
        "--style-css",
        type=Path,
        default=Path(os.getenv("LLM_STYLE_CSS")) if os.getenv("LLM_STYLE_CSS") else None,
        help="Custom CSS file for --layout clean. Defaults to a 10.3-inch e-ink friendly style.",
    )
    parser.add_argument(
        "--number-headings",
        action="store_true",
        help="Prefix h1-h3 headings with generated hierarchical numbers in --layout clean output.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Translate only the first N segments.")
    parser.add_argument("--dry-run", action="store_true", help="Analyze the EPUB and estimate cost without calling an LLM.")
    parser.add_argument(
        "--input-price-per-1m",
        type=float,
        default=optional_float_env("LLM_INPUT_PRICE_PER_1M"),
        help="Input token price per 1M tokens for dry-run cost estimates.",
    )
    parser.add_argument(
        "--output-price-per-1m",
        type=float,
        default=optional_float_env("LLM_OUTPUT_PRICE_PER_1M"),
        help="Output token price per 1M tokens for dry-run cost estimates.",
    )
    parser.add_argument(
        "--price-currency",
        default=os.getenv("LLM_PRICE_CURRENCY", "USD"),
        help="Currency label for dry-run cost estimates.",
    )
    parser.add_argument(
        "--output-token-ratio",
        type=float,
        default=float(os.getenv("LLM_OUTPUT_TOKEN_RATIO", "1.15")),
        help="Estimated output/input token ratio for dry-run. Defaults to 1.15.",
    )
    parser.add_argument(
        "--terminology",
        type=Path,
        default=Path(os.getenv("LLM_TERMINOLOGY")) if os.getenv("LLM_TERMINOLOGY") else None,
        help="CSV/TSV glossary with source,target[,note] columns.",
    )
    parser.add_argument("--quiet", action="store_true", help="Hide translation progress output.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Do not call an LLM; insert placeholder translations. Useful for EPUB structure testing.",
    )
    return parser


def optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return float(value)


def main(argv: list[str] | None = None) -> int:
    load_env_file(Path.cwd() / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.input.exists():
        parser.error(f"Input file does not exist: {args.input}")
    if args.output is not None and args.output.resolve() == args.input.resolve():
        parser.error("Output file must be different from input file")
    input_path, output_path, cache_path = prepare_run_paths(args.input, args.output, args.cache, args.work_dir)

    if output_path.resolve() == input_path.resolve():
        parser.error("Output file must be different from input file")
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.min_chars < 1:
        parser.error("--min-chars must be >= 1")
    if args.timeout < 1:
        parser.error("--timeout must be >= 1")
    if args.retries < 1:
        parser.error("--retries must be >= 1")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.output_token_ratio <= 0:
        parser.error("--output-token-ratio must be > 0")
    if args.style_css is not None and args.layout != "clean":
        parser.error("--style-css requires --layout clean")
    if args.number_headings and args.layout != "clean":
        parser.error("--number-headings requires --layout clean")
    if args.input_price_per_1m is not None and args.input_price_per_1m < 0:
        parser.error("--input-price-per-1m must be >= 0")
    if args.output_price_per_1m is not None and args.output_price_per_1m < 0:
        parser.error("--output-price-per-1m must be >= 0")

    terminology = []
    if args.terminology is not None:
        if not args.terminology.exists():
            parser.error(f"Terminology file does not exist: {args.terminology}")
        terminology_path = copy_into_work_dir(args.terminology, args.work_dir)
        terminology = load_terminology(terminology_path)
    cache_namespace = terminology_fingerprint(terminology)

    style_css = None
    if args.style_css is not None:
        if not args.style_css.exists():
            parser.error(f"Style CSS file does not exist: {args.style_css}")
        style_css_path = copy_into_work_dir(args.style_css, args.work_dir)
        style_css = style_css_path.read_text(encoding="utf-8")

    if args.mock:
        raw_translator = MockTranslator()
        model_name = "mock"
    else:
        if not args.model and not args.dry_run:
            parser.error("--model is required unless LLM_MODEL is set")
        if not args.api_key and not args.dry_run:
            parser.error("--api-key is required unless LLM_API_KEY or OPENAI_API_KEY is set")
        model_name = args.model or "unknown"
        raw_translator = None
        if not args.dry_run:
            raw_translator = OpenAICompatibleTranslator(
                api_key=args.api_key,
                model=args.model,
                base_url=args.base_url,
                source_language=args.source_lang,
                target_language=args.target_lang,
                timeout=args.timeout,
                retries=args.retries,
                terminology=terminology,
            )

    cache = TranslationCache.load(cache_path)

    input_price, output_price = resolve_prices(args.model, args.base_url, args.input_price_per_1m, args.output_price_per_1m)
    if args.dry_run:
        stats = analyze_epub(
            input_path,
            batch_size=args.batch_size,
            min_chars=args.min_chars,
            limit=args.limit,
            output_token_ratio=args.output_token_ratio,
            is_cached=lambda text: cache.get(
                cache_key(model_name, args.source_lang, args.target_lang, text, cache_namespace)
            )
            is not None,
        )
        print_dry_run(stats, input_price, output_price, args.price_currency)
        return 0

    assert raw_translator is not None
    translator = CachedTranslator(
        raw_translator,
        cache,
        model=model_name,
        source_language=args.source_lang,
        target_language=args.target_lang,
        cache_namespace=cache_namespace,
    )

    progress_callback = None if args.quiet else print_progress
    stats = convert_epub_to_bilingual(
        input_path,
        output_path,
        translator,
        batch_size=args.batch_size,
        min_chars=args.min_chars,
        limit=args.limit,
        concurrency=args.concurrency,
        layout=args.layout,
        style_css=style_css,
        number_headings=args.number_headings,
        progress_callback=progress_callback,
    )

    print(f"Wrote: {output_path}")
    print(f"Documents scanned: {stats.documents}")
    print(f"Segments translated: {stats.translated_segments}")
    if stats.skipped_documents:
        print("Skipped documents:")
        for item in stats.skipped_documents:
            print(f"  - {item}")
    return 0


def print_progress(progress: TranslationProgress) -> None:
    if progress.total_segments == 0:
        return
    percent = progress.completed_segments / progress.total_segments * 100
    print(
        f"Progress: {progress.completed_segments}/{progress.total_segments} segments "
        f"({progress.completed_batches}/{progress.total_batches} batches, {percent:.1f}%) "
        f"{progress.current_document}",
        flush=True,
    )


def print_dry_run(
    stats: DryRunStats,
    input_price: float | None,
    output_price: float | None,
    currency: str,
) -> None:
    print("Dry run only. No LLM requests were made.")
    print(f"Documents scanned: {stats.documents}")
    print(f"HTML documents: {stats.html_documents}")
    print(f"Segments to translate: {stats.segments}")
    print(f"Characters to translate: {stats.characters}")
    print(f"Batches: {stats.batches}")
    print(f"Cached segments: {stats.cached_segments}")
    print(f"Uncached segments: {stats.uncached_segments}")
    print(f"Estimated input tokens: {stats.estimated_input_tokens}")
    print(f"Estimated output tokens: {stats.estimated_output_tokens}")
    print(f"Estimated uncached input tokens: {stats.estimated_uncached_input_tokens}")
    print(f"Estimated uncached output tokens: {stats.estimated_uncached_output_tokens}")
    if input_price is None or output_price is None:
        print("Estimated cost: unavailable (set --input-price-per-1m and --output-price-per-1m)")
    else:
        cost = (
            stats.estimated_uncached_input_tokens / 1_000_000 * input_price
            + stats.estimated_uncached_output_tokens / 1_000_000 * output_price
        )
        print(f"Estimated cost: {cost:.4f} {currency}")
    if stats.skipped_documents:
        print("Skipped documents:")
        for item in stats.skipped_documents:
            print(f"  - {item}")
