#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import statistics
import tempfile
import time
import tracemalloc
import zipfile

from ebook_bilingual.app import ConversionOptions, run_conversion
from ebook_bilingual.epub import convert_epub_to_bilingual
from ebook_bilingual.profiling import ProfileMetrics


@dataclass(frozen=True)
class Scenario:
    name: str
    documents: list[str]
    layout: str = "preserve"
    number_headings: bool = False
    cache_warm: bool = False
    sleep_translator: bool = False


class SleepTranslator:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    def translate_batch(self, texts: list[str]) -> list[str]:
        time.sleep(self.delay)
        return [f"[bench] {text}" for text in texts]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic local EPUB conversion benchmarks.")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.03, help="Per-request delay for concurrency-sleep.")
    parser.add_argument("--ndjson", action="store_true", help="Write one scenario result per line.")
    parser.add_argument("--scenario", action="append", choices=sorted(scenarios()), help="Run only the selected scenario; repeatable.")
    args = parser.parse_args()

    selected = set(args.scenario or scenarios().keys())
    results = [
        run_scenario(scenario, iterations=args.iterations, batch_size=args.batch_size, concurrency=args.concurrency, sleep=args.sleep)
        for name, scenario in scenarios().items()
        if name in selected
    ]
    if args.ndjson:
        for result in results:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


def run_scenario(scenario: Scenario, *, iterations: int, batch_size: int, concurrency: int, sleep: float) -> dict[str, object]:
    runs = [run_once(scenario, batch_size=batch_size, concurrency=concurrency, sleep=sleep) for _ in range(iterations)]
    elapsed = [float(run["elapsed_seconds"]) for run in runs]
    segments = int(runs[-1]["segments"])
    characters = int(runs[-1]["characters"])
    median_elapsed = statistics.median(elapsed)
    return {
        "scenario": scenario.name,
        "iterations": iterations,
        "median_seconds": median_elapsed,
        "min_seconds": min(elapsed),
        "p90_seconds": percentile(elapsed, 0.9),
        "segments_per_second": segments / median_elapsed if median_elapsed else 0.0,
        "characters_per_second": characters / median_elapsed if median_elapsed else 0.0,
        "peak_memory_bytes": max(int(run["peak_memory_bytes"]) for run in runs),
        "profile": runs[-1]["profile"],
    }


def run_once(scenario: Scenario, *, batch_size: int, concurrency: int, sleep: float) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        input_path = root / "input.epub"
        output_path = root / "output.epub"
        write_epub(input_path, scenario.documents)
        cache_path = root / "cache.json"
        if scenario.cache_warm and not scenario.sleep_translator:
            run_conversion(
                ConversionOptions(
                    input_path=input_path,
                    output_path=root / "warmup.epub",
                    mock=True,
                    quiet=True,
                    batch_size=batch_size,
                    concurrency=concurrency,
                    cache_path=cache_path,
                    layout=scenario.layout,
                    number_headings=scenario.number_headings,
                    profile_json=root / "warmup-profile.json",
                )
            )
        tracemalloc.start()
        started = time.perf_counter()
        if scenario.sleep_translator:
            profile_timings: dict[str, float] = {}
            metrics = ProfileMetrics()
            stats = convert_epub_to_bilingual(
                input_path,
                output_path,
                SleepTranslator(sleep),
                batch_size=batch_size,
                concurrency=concurrency,
                profile_timings=profile_timings,
                profile_metrics=metrics,
            )
            profile: dict[str, object] = {
                "stages": profile_timings,
                "metrics": metrics.to_dict(),
                "output_size": output_path.stat().st_size if output_path.exists() else 0,
            }
        else:
            profile_json = root / "profile.json"
            options = ConversionOptions(
                input_path=input_path,
                output_path=output_path,
                mock=True,
                quiet=True,
                batch_size=batch_size,
                concurrency=concurrency,
                cache_path=cache_path,
                layout=scenario.layout,
                number_headings=scenario.number_headings,
                profile_json=profile_json,
            )
            result = run_conversion(options)
            stats = result.stats
            profile = json.loads(profile_json.read_text(encoding="utf-8"))
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "elapsed_seconds": elapsed,
            "segments": stats.total_segments,
            "characters": stats.characters,
            "peak_memory_bytes": peak,
            "profile": profile,
        }


def percentile(values: list[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def scenarios() -> dict[str, Scenario]:
    return {
        "tiny": Scenario("tiny", [html_doc(["<h1>Tiny</h1>", paragraph_lines(3)])]),
        "medium-single-doc": Scenario("medium-single-doc", [html_doc(["<h1>Medium</h1>", paragraph_lines(400)])]),
        "large-multi-doc": Scenario("large-multi-doc", [html_doc([f"<h1>Chapter {index}</h1>", paragraph_lines(160)]) for index in range(8)]),
        "html-heavy": Scenario("html-heavy", [html_doc(["<h1>HTML Heavy</h1>", html_heavy_lines(120)])]),
        "clean-numbered": Scenario(
            "clean-numbered",
            [html_doc(["<h1>Chapter 1</h1>", heading_lines(60), paragraph_lines(180)])],
            layout="clean",
            number_headings=True,
        ),
        "cache-warm": Scenario("cache-warm", [html_doc(["<h1>Warm Cache</h1>", paragraph_lines(300)])], cache_warm=True),
        "concurrency-sleep": Scenario("concurrency-sleep", [html_doc(["<h1>Sleep</h1>", paragraph_lines(80)])], sleep_translator=True),
    }


def paragraph_lines(count: int) -> str:
    return "\n".join(f"<p>Benchmark paragraph {index} with repeatable text for conversion speed.</p>" for index in range(count))


def heading_lines(count: int) -> str:
    tags = ["h2", "h3", "h4", "h5", "h6"]
    return "\n".join(f"<{tags[index % len(tags)]}>Heading {index}</{tags[index % len(tags)]}>" for index in range(count))


def html_heavy_lines(count: int) -> str:
    lines = []
    for index in range(count):
        lines.append(f"<p>Paragraph {index} with <code>inline_code_{index}()</code> kept intact.</p>")
        lines.append(f"<figcaption>Figure caption {index}</figcaption>")
        lines.append(f"<dl><dt>Term {index}</dt><dd>Definition {index}</dd></dl>")
        lines.append(f"<table><tr><th>Key {index}</th><td>Value {index}</td></tr></table>")
    return "\n".join(lines)


def html_doc(body_parts: list[str]) -> str:
    body = "\n".join(body_parts)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Benchmark</title></head>
  <body>
{body}
  </body>
</html>"""


def write_epub(path: Path, documents: list[str]) -> None:
    manifest_items = "\n".join(
        f'    <item id="chap{index}" href="chapter{index}.xhtml" media-type="application/xhtml+xml"/>'
        for index in range(len(documents))
    )
    spine_items = "\n".join(f'    <itemref idref="chap{index}"/>' for index in range(len(documents)))
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
        )
        zf.writestr(
            "OPS/content.opf",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0"
         unique-identifier="bookid">
  <metadata>
    <dc:identifier id="bookid">urn:uuid:00000000-0000-4000-8000-00000000bench</dc:identifier>
    <dc:title>Benchmark</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
{manifest_items}
  </manifest>
  <spine>
{spine_items}
  </spine>
</package>""",
        )
        for index, document in enumerate(documents):
            zf.writestr(f"OPS/chapter{index}.xhtml", document)


if __name__ == "__main__":
    main()
