from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import math
import posixpath
from pathlib import Path
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from .html_bilingual import (
    BilingualizeResult,
    Segment,
    bilingualize_xhtml,
    ensure_xhtml_doctype,
    restyle_bilingual_xhtml,
)
from .llm import Translator


CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}
XHTML_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}


@dataclass(frozen=True)
class SpineDocument:
    path: str
    media_type: str


@dataclass
class ConversionStats:
    documents: int = 0
    translated_segments: int = 0
    skipped_documents: list[str] | None = None

    def __post_init__(self) -> None:
        if self.skipped_documents is None:
            self.skipped_documents = []


@dataclass
class TranslationPlan:
    documents: list[SpineDocument]
    html_documents: list[SpineDocument]
    segments_by_doc: dict[str, list[Segment]]
    skipped_documents: list[str]

    @property
    def total_segments(self) -> int:
        return sum(len(segments) for segments in self.segments_by_doc.values())

    @property
    def total_characters(self) -> int:
        return sum(len(segment.text) for segments in self.segments_by_doc.values() for segment in segments)


@dataclass
class DryRunStats:
    documents: int
    html_documents: int
    segments: int
    characters: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    batches: int
    cached_segments: int = 0
    skipped_documents: list[str] | None = None

    def __post_init__(self) -> None:
        if self.skipped_documents is None:
            self.skipped_documents = []

    @property
    def uncached_segments(self) -> int:
        return max(self.segments - self.cached_segments, 0)

    @property
    def uncached_ratio(self) -> float:
        if self.segments == 0:
            return 0.0
        return self.uncached_segments / self.segments

    @property
    def estimated_uncached_input_tokens(self) -> int:
        return math.ceil(self.estimated_input_tokens * self.uncached_ratio)

    @property
    def estimated_uncached_output_tokens(self) -> int:
        return math.ceil(self.estimated_output_tokens * self.uncached_ratio)


@dataclass(frozen=True)
class TranslationProgress:
    completed_segments: int
    total_segments: int
    completed_batches: int
    total_batches: int
    current_document: str


ProgressCallback = Callable[[TranslationProgress], None]


def find_opf_path(epub: zipfile.ZipFile) -> str:
    try:
        container_data = epub.read("META-INF/container.xml")
    except KeyError as exc:
        raise ValueError("EPUB is missing META-INF/container.xml") from exc

    root = ET.fromstring(container_data)
    rootfile = root.find(".//c:rootfile", CONTAINER_NS)
    if rootfile is None:
        raise ValueError("EPUB container.xml does not contain a rootfile entry")
    opf_path = rootfile.attrib.get("full-path")
    if not opf_path:
        raise ValueError("EPUB rootfile entry is missing full-path")
    return opf_path


def resolve_href(base_path: str, href: str) -> str:
    href = urllib.parse.unquote(href.split("#", 1)[0])
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_path), href))


def spine_documents(epub: zipfile.ZipFile, opf_path: str) -> list[SpineDocument]:
    documents = manifest_documents(epub, opf_path)
    spine_paths = {document.path: document for document in documents}
    root = ET.fromstring(epub.read(opf_path))

    result: list[SpineDocument] = []
    for itemref in root.findall(".//opf:spine/opf:itemref", OPF_NS):
        idref = itemref.attrib.get("idref")
        if not idref:
            continue
        for item in root.findall(".//opf:manifest/opf:item", OPF_NS):
            if item.attrib.get("id") == idref:
                href = item.attrib.get("href")
                if href:
                    path = resolve_href(opf_path, href)
                    if path in spine_paths:
                        result.append(spine_paths[path])
                break
    return result


def manifest_documents(epub: zipfile.ZipFile, opf_path: str) -> list[SpineDocument]:
    root = ET.fromstring(epub.read(opf_path))
    result: list[SpineDocument] = []
    for item in root.findall(".//opf:manifest/opf:item", OPF_NS):
        href = item.attrib.get("href")
        media_type = item.attrib.get("media-type", "")
        if href and media_type in XHTML_MEDIA_TYPES:
            result.append(SpineDocument(path=resolve_href(opf_path, href), media_type=media_type))
    return result


def build_translation_plan(
    source: zipfile.ZipFile,
    *,
    min_chars: int = 2,
    limit: int | None = None,
) -> TranslationPlan:
    opf_path = find_opf_path(source)
    documents = spine_documents(source, opf_path)
    html_documents = manifest_documents(source, opf_path)
    segments_by_doc: dict[str, list[Segment]] = {}
    skipped_documents: list[str] = []
    selected = 0

    for document in documents:
        try:
            _, segments = bilingualize_xhtml(source.read(document.path), min_chars=min_chars)
        except Exception:
            skipped_documents.append(document.path)
            continue
        if limit is not None:
            remaining = max(limit - selected, 0)
            segments = segments[:remaining]
        segments_by_doc[document.path] = segments
        selected += len(segments)
        if limit is not None and selected >= limit:
            break

    return TranslationPlan(
        documents=documents,
        html_documents=html_documents,
        segments_by_doc=segments_by_doc,
        skipped_documents=skipped_documents,
    )


def analyze_epub(
    input_path: Path,
    *,
    batch_size: int = 8,
    min_chars: int = 2,
    limit: int | None = None,
    output_token_ratio: float = 1.15,
    is_cached: Callable[[str], bool] | None = None,
) -> DryRunStats:
    with zipfile.ZipFile(input_path, "r") as source:
        plan = build_translation_plan(source, min_chars=min_chars, limit=limit)

    cached_segments = 0
    if is_cached is not None:
        cached_segments = sum(1 for segments in plan.segments_by_doc.values() for segment in segments if is_cached(segment.text))
    estimated_input_tokens = estimate_tokens(plan.total_characters)
    estimated_output_tokens = math.ceil(estimated_input_tokens * output_token_ratio)
    batches = sum(math.ceil(len(segments) / batch_size) for segments in plan.segments_by_doc.values() if segments)
    return DryRunStats(
        documents=len(plan.documents),
        html_documents=len(plan.html_documents),
        segments=plan.total_segments,
        characters=plan.total_characters,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        batches=batches,
        cached_segments=cached_segments,
        skipped_documents=plan.skipped_documents,
    )


def estimate_tokens(characters: int) -> int:
    return math.ceil(characters / 4)


def convert_epub_to_bilingual(
    input_path: Path,
    output_path: Path,
    translator: Translator,
    *,
    batch_size: int = 8,
    min_chars: int = 2,
    limit: int | None = None,
    concurrency: int = 1,
    layout: str = "preserve",
    style_css: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ConversionStats:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_path, "r") as source:
        plan = build_translation_plan(source, min_chars=min_chars, limit=limit)
        stats = ConversionStats(documents=len(plan.documents), skipped_documents=list(plan.skipped_documents))

        translations_by_doc = translate_plan_segments(
            translator,
            plan.segments_by_doc,
            batch_size=batch_size,
            concurrency=concurrency,
            progress_callback=progress_callback,
        )

        modified: dict[str, bytes] = {}
        for document_path, translations in translations_by_doc.items():
            if not translations:
                continue
            try:
                result = bilingualize_xhtml(
                    source.read(document_path),
                    translations=translations,
                    min_chars=min_chars,
                )
            except Exception:
                stats.skipped_documents.append(document_path)
                continue
            if isinstance(result, BilingualizeResult):
                content = result.content
                if layout == "clean":
                    content = restyle_bilingual_xhtml(content, style_css=style_css)
                modified[document_path] = content
                stats.translated_segments += result.segments

        for document in plan.html_documents:
            if document.path not in modified:
                try:
                    content = ensure_xhtml_doctype(source.read(document.path))
                    if layout == "clean":
                        content = restyle_bilingual_xhtml(content, style_css=style_css)
                    modified[document.path] = content
                except Exception:
                    stats.skipped_documents.append(document.path)

        write_epub_copy(source, output_path, modified)
        return stats


def translate_segments(
    translator: Translator,
    segments: list[Segment],
    batch_size: int,
    *,
    concurrency: int = 1,
) -> dict[str, str]:
    return translate_plan_segments(
        translator,
        {"": segments},
        batch_size=batch_size,
        concurrency=concurrency,
    ).get("", {})


def translate_plan_segments(
    translator: Translator,
    segments_by_doc: dict[str, list[Segment]],
    *,
    batch_size: int,
    concurrency: int = 1,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, dict[str, str]]:
    batches: list[tuple[str, list[Segment]]] = []
    for document_path, segments in segments_by_doc.items():
        for start in range(0, len(segments), batch_size):
            batch = segments[start : start + batch_size]
            if batch:
                batches.append((document_path, batch))

    translations_by_doc: dict[str, dict[str, str]] = {document_path: {} for document_path in segments_by_doc}
    total_segments = sum(len(batch) for _, batch in batches)
    total_batches = len(batches)
    completed_segments = 0
    completed_batches = 0

    def mark_done(document_path: str, translated_count: int) -> None:
        nonlocal completed_segments, completed_batches
        completed_segments += translated_count
        completed_batches += 1
        if progress_callback is not None:
            progress_callback(
                TranslationProgress(
                    completed_segments=completed_segments,
                    total_segments=total_segments,
                    completed_batches=completed_batches,
                    total_batches=total_batches,
                    current_document=document_path,
                )
            )

    if concurrency <= 1 or total_batches <= 1:
        for document_path, batch in batches:
            translations_by_doc[document_path].update(translate_batch_to_dict(translator, batch))
            mark_done(document_path, len(batch))
        return translations_by_doc

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(translate_batch_to_dict, translator, batch): (document_path, len(batch))
            for document_path, batch in batches
        }
        for future in as_completed(futures):
            document_path, translated_count = futures[future]
            translations_by_doc[document_path].update(future.result())
            mark_done(document_path, translated_count)

    return translations_by_doc


def translate_batch_to_dict(translator: Translator, batch: list[Segment]) -> dict[str, str]:
    translations: dict[str, str] = {}
    translated = translator.translate_batch([segment.text for segment in batch])
    if len(translated) != len(batch):
        raise ValueError("Translator returned the wrong number of segments")
    for segment, value in zip(batch, translated, strict=True):
        translations[segment.id] = value
    return translations


def write_epub_copy(source: zipfile.ZipFile, output_path: Path, modified: dict[str, bytes]) -> None:
    infos = source.infolist()
    with zipfile.ZipFile(output_path, "w") as target:
        names_written: set[str] = set()
        if "mimetype" in source.namelist():
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            target.writestr(info, modified.get("mimetype", source.read("mimetype")))
            names_written.add("mimetype")

        for info in infos:
            if info.filename in names_written:
                continue
            data = modified.get(info.filename, source.read(info.filename))
            target.writestr(info, data)
            names_written.add(info.filename)
