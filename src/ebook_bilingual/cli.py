from __future__ import annotations

import argparse
import os
from pathlib import Path

from .app import (
    ConversionConfigError,
    ConversionOptions,
    ConversionRunResult,
    DryRunResult,
    options_from_namespace,
    run_conversion,
    run_dry_run,
)
from .config import load_env_file
from .epub import DryRunStats, SkippedDocument, TranslationProgress


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ebook-bilingual",
        description="Convert an EPUB into a bilingual EPUB by inserting LLM translations under original paragraphs.",
    )
    parser.add_argument("input", type=Path, nargs="?", default=None, help="Input .epub file")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=None,
        help="Output bilingual .epub file. Defaults to <input>.bilingual.epub in the same directory.",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Run a plain terminal wizard that asks for conversion options.",
    )

    model_group = parser.add_argument_group("model configuration")
    model_group.add_argument("--model", default=os.getenv("LLM_MODEL"), help="LLM model name. Defaults to LLM_MODEL.")
    model_group.add_argument(
        "--api-key",
        default=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        help="API key. Defaults to LLM_API_KEY or OPENAI_API_KEY.",
    )
    model_group.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        help="OpenAI-compatible API base URL.",
    )
    model_group.add_argument("--source-lang", default=os.getenv("LLM_SOURCE_LANG", "auto"), help="Source language hint.")
    model_group.add_argument(
        "--target-lang",
        default=os.getenv("LLM_TARGET_LANG", "Simplified Chinese"),
        help="Target translation language.",
    )

    conversion_group = parser.add_argument_group("conversion options")
    conversion_group.add_argument(
        "--layout",
        choices=("preserve", "clean"),
        default=os.getenv("LLM_LAYOUT", "preserve"),
        help="EPUB layout mode. preserve keeps original XHTML/CSS; clean restyles readable bilingual XHTML.",
    )
    conversion_group.add_argument(
        "--style-css",
        type=Path,
        default=optional_path_env("LLM_STYLE_CSS"),
        help=(
            "CSS file for --layout clean. If omitted and LLM_STYLE_CSS is unset, uses ./styles/eink-10.3.css when "
            "present, otherwise the first ./styles/*.css; if no styles/ CSS is found, a built-in e-ink default is used."
        ),
    )
    conversion_group.add_argument(
        "--number-headings",
        action="store_true",
        help="Prefix h1-h3 headings with generated hierarchical numbers in --layout clean output.",
    )
    conversion_group.add_argument("--dry-run", action="store_true", help="Analyze the EPUB and estimate cost without calling an LLM.")
    conversion_group.add_argument(
        "--mock",
        action="store_true",
        help="Do not call an LLM; insert placeholder translations. Useful for EPUB structure testing.",
    )

    advanced_group = parser.add_argument_group("advanced options")
    advanced_group.add_argument("--batch-size", type=int, default=8, help="Paragraphs per LLM request.")
    advanced_group.add_argument(
        "--concurrency",
        type=int,
        default=int_env(parser, "LLM_CONCURRENCY", 1),
        help="Concurrent translation requests. Defaults to LLM_CONCURRENCY or 1.",
    )
    advanced_group.add_argument("--min-chars", type=int, default=2, help="Skip text shorter than this many characters.")
    advanced_group.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds.")
    advanced_group.add_argument("--retries", type=int, default=3, help="LLM request retries.")
    advanced_group.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="Translation cache path. Defaults to <output>.translation-cache.json.",
    )
    advanced_group.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help=(
            "Isolated directory for this book run. Input EPUB, terminology, and style CSS are copied there; "
            "default output/cache files are written there."
        ),
    )
    advanced_group.add_argument("--limit", type=int, default=None, help="Translate only the first N segments.")
    advanced_group.add_argument(
        "--terminology",
        type=Path,
        default=optional_path_env("LLM_TERMINOLOGY"),
        help="CSV/TSV glossary with source,target[,note] columns.",
    )
    advanced_group.add_argument("--quiet", action="store_true", help="Hide translation progress output.")
    advanced_group.add_argument(
        "--fail-on-skipped",
        action="store_true",
        help="Return a non-zero exit code when any EPUB document is skipped.",
    )
    advanced_group.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed diagnostic information for skipped documents and failed operations.",
    )
    advanced_group.add_argument(
        "--profile",
        action="store_true",
        help="Print coarse stage timings for planning, LLM, cache, XHTML, and ZIP work.",
    )
    advanced_group.add_argument(
        "--profile-json",
        type=Path,
        default=None,
        help="Write machine-readable conversion profile metrics to this JSON file.",
    )

    pricing_group = parser.add_argument_group("dry-run cost estimates")
    pricing_group.add_argument(
        "--input-price-per-1m",
        type=float,
        default=optional_float_env("LLM_INPUT_PRICE_PER_1M", parser=parser),
        help="Input token price per 1M tokens for dry-run cost estimates.",
    )
    pricing_group.add_argument(
        "--output-price-per-1m",
        type=float,
        default=optional_float_env("LLM_OUTPUT_PRICE_PER_1M", parser=parser),
        help="Output token price per 1M tokens for dry-run cost estimates.",
    )
    pricing_group.add_argument(
        "--price-currency",
        default=os.getenv("LLM_PRICE_CURRENCY", "USD"),
        help="Currency label for dry-run cost estimates.",
    )
    pricing_group.add_argument(
        "--output-token-ratio",
        type=float,
        default=float_env(parser, "LLM_OUTPUT_TOKEN_RATIO", 1.15),
        help="Estimated output/input token ratio for dry-run. Defaults to 1.15.",
    )
    return parser


def int_env(parser: argparse.ArgumentParser, name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        parser.error(f"{name} must be an integer")


def float_env(parser: argparse.ArgumentParser, name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        parser.error(f"{name} must be a number")


def optional_float_env(name: str, *, parser: argparse.ArgumentParser | None = None) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        if parser is not None:
            parser.error(f"{name} must be a number")
        raise


def optional_path_env(name: str) -> Path | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return Path(value)


def main(argv: list[str] | None = None) -> int:
    load_env_file(Path.cwd() / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.interactive:
        from .interactive import run_interactive

        return run_interactive(args)
    return run_from_args(args, parser)


def run_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        options = options_from_namespace(args)
        if options.dry_run:
            dry_run_result = run_dry_run(options)
            print_dry_run_result(dry_run_result, options)
            return dry_run_result.exit_code if options.fail_on_skipped else 0

        progress_callback = None if options.quiet else print_progress
        conversion_result = run_conversion(options, progress_callback=progress_callback)
        print_conversion_result(conversion_result, options)
        return conversion_result.exit_code if options.fail_on_skipped else 0
    except ConversionConfigError as exc:
        parser.error(str(exc))


def print_progress(progress: TranslationProgress) -> None:
    if progress.total_segments == 0:
        return
    percent = progress.completed_segments / progress.total_segments * 100
    print(
        f"Progress: {progress.completed_segments}/{progress.total_segments} segments | "
        f"batches {progress.completed_batches}/{progress.total_batches} | "
        f"{percent:.1f}% | {progress.current_document}",
        flush=True,
    )


def print_conversion_result(result: ConversionRunResult, options: ConversionOptions) -> None:
    print(f"Wrote: {result.output_path}")
    print(f"Documents: {result.stats.documents}")
    print(f"Segments: {result.stats.translated_segments}")
    print_skipped_documents(result.stats.skipped_documents, verbose=options.verbose)
    if options.profile:
        print_profile(result.profile_timings)


def print_dry_run_result(result: DryRunResult, options: ConversionOptions) -> None:
    print_dry_run(result.stats, result.input_price, result.output_price, result.price_currency, verbose=options.verbose)
    if options.profile:
        print_profile(result.profile_timings)


def print_dry_run(
    stats: DryRunStats,
    input_price: float | None,
    output_price: float | None,
    currency: str,
    *,
    verbose: bool = False,
) -> None:
    print("Dry run")
    print(f"Documents: {stats.documents}")
    print(f"HTML documents: {stats.html_documents}")
    print(f"Segments: {stats.segments}")
    print(f"Characters: {stats.characters}")
    print(f"Batches: {stats.batches}")
    print(f"Cached: {stats.cached_segments}")
    print(f"Uncached: {stats.uncached_segments}")
    print(f"Tokens: input {stats.estimated_input_tokens}, output {stats.estimated_output_tokens}")
    print(f"Uncached tokens: input {stats.estimated_uncached_input_tokens}, output {stats.estimated_uncached_output_tokens}")
    if input_price is None or output_price is None:
        print("Estimated cost: unavailable (set --input-price-per-1m and --output-price-per-1m)")
    else:
        cost = (
            stats.estimated_uncached_input_tokens / 1_000_000 * input_price
            + stats.estimated_uncached_output_tokens / 1_000_000 * output_price
        )
        print(f"Estimated cost: {cost:.4f} {currency}")
    if stats.skipped_documents:
        print_skipped_documents(stats.skipped_documents, verbose=verbose)


def print_skipped_documents(skipped_documents: list[SkippedDocument] | None, *, verbose: bool) -> None:
    if not skipped_documents:
        return
    print("Skipped documents:")
    for item in skipped_documents:
        print(f"  - {item}")
        if verbose and item.traceback:
            for line in item.traceback.rstrip().splitlines():
                print(f"      {line}")


def print_profile(profile_timings: dict[str, float]) -> None:
    print("Profile timings:")
    preferred = ("plan", "llm", "cache_save", "html_insert_restyle", "zip_write")
    seen = set()
    for key in preferred:
        if key in profile_timings:
            seen.add(key)
            print(f"  - {key}: {profile_timings[key]:.3f}s")
    for key in sorted(set(profile_timings) - seen):
        print(f"  - {key}: {profile_timings[key]:.3f}s")
