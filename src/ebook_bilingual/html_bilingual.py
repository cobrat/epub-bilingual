from __future__ import annotations

import copy
from dataclasses import dataclass
import posixpath
import re
import xml.etree.ElementTree as ET

from .styles import BILINGUAL_CSS, CLEAN_BILINGUAL_CSS


XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"

ET.register_namespace("", XHTML_NS)
ET.register_namespace("epub", EPUB_NS)

BLOCK_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "figcaption",
    "dt",
    "dd",
}

NUMBERED_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3}
LEADING_NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:[.)])?\s+")
CHAPTER_NUMBER_RE = re.compile(r"^\s*Chapter\s+(\d+)\b", re.IGNORECASE)
SKIP_HEADING_NUMBER_DOCUMENT_PARTS = {
    "afterword",
    "colophon",
    "copyright",
    "cover",
    "dedication",
    "index",
    "ix",
    "nav",
    "preface",
    "titlepage",
    "toc",
}
SKIP_ANCESTORS = {"script", "style", "nav", "code", "pre", "svg", "math"}
PROTECTED_INLINE_TAGS = {"code", "kbd", "samp", "var", "math"}
INLINE_PLACEHOLDER_RE = re.compile(r"__EBOOK_BILINGUAL_KEEP_\d+__")
GENERIC_INLINE_PLACEHOLDER = "__EBOOK_BILINGUAL_KEEP_N__"
SKIP_CLASS_NAMES = {"pg-boilerplate", "pgheader", "pgfooter"}
SKIP_IDS = {"pg-header", "pg-machine-header", "pg-footer"}
SKIP_TEXT_PATTERNS = (
    re.compile(r"\bProject Gutenberg\b", re.IGNORECASE),
    re.compile(r"\bwww\.gutenberg\.org\b", re.IGNORECASE),
    re.compile(r"\bProject Gutenberg License\b", re.IGNORECASE),
    re.compile(r"\bSTART OF (THE )?PROJECT GUTENBERG\b", re.IGNORECASE),
    re.compile(r"\bEND OF (THE )?PROJECT GUTENBERG\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class ProtectedInline:
    placeholder: str
    element: ET.Element


@dataclass(frozen=True)
class Segment:
    id: str
    text: str
    tag: str = "p"
    protected_inlines: tuple[ProtectedInline, ...] = ()


@dataclass
class BilingualizeResult:
    content: bytes
    segments: int


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def namespace_for(tag: str) -> str | None:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return None


def qname(ns: str | None, name: str) -> str:
    return f"{{{ns}}}{name}" if ns else name


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def element_text(element: ET.Element) -> str:
    return normalize_text("".join(element.itertext()))


def protected_segment_text(element: ET.Element) -> tuple[str, tuple[ProtectedInline, ...]]:
    protected: list[ProtectedInline] = []
    parts: list[str] = []

    def walk(current: ET.Element) -> None:
        if current.text:
            parts.append(current.text)
        for child in list(current):
            if local_name(child.tag) in PROTECTED_INLINE_TAGS:
                placeholder = f"__EBOOK_BILINGUAL_KEEP_{len(protected)}__"
                clone = copy.deepcopy(child)
                clone.tail = None
                protected.append(ProtectedInline(placeholder=placeholder, element=clone))
                parts.append(placeholder)
            else:
                walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(element)
    return normalize_text("".join(parts)), tuple(protected)


def translatable_text_without_placeholders(text: str, protected_inlines: tuple[ProtectedInline, ...]) -> str:
    for protected in protected_inlines:
        text = text.replace(protected.placeholder, "")
    return normalize_text(text)


def has_class(element: ET.Element, class_name: str) -> bool:
    classes = element.attrib.get("class", "").split()
    return class_name in classes


def has_any_class(element: ET.Element, class_names: set[str]) -> bool:
    return any(class_name in class_names for class_name in element.attrib.get("class", "").split())


def add_class(element: ET.Element, class_name: str) -> None:
    classes = element.attrib.get("class", "").split()
    if class_name not in classes:
        classes.append(class_name)
        element.set("class", " ".join(classes))


def descendants_with_class(element: ET.Element, class_name: str) -> bool:
    return any(has_class(descendant, class_name) for descendant in element.iter())


def parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def remove_child_preserving_tail(parent: ET.Element, child: ET.Element) -> None:
    tail = child.tail or ""
    children = list(parent)
    try:
        index = children.index(child)
    except ValueError:
        return
    if tail:
        if index == 0:
            parent.text = (parent.text or "") + tail
        else:
            previous = children[index - 1]
            previous.tail = (previous.tail or "") + tail
    parent.remove(child)


def replace_child_preserving_tail(parent: ET.Element, child: ET.Element, replacement: ET.Element) -> None:
    replacement.tail = child.tail
    child.tail = None
    children = list(parent)
    try:
        index = children.index(child)
    except ValueError:
        return
    parent.remove(child)
    parent.insert(index, replacement)


def remove_invisible_index_terms(root: ET.Element) -> None:
    parents = parent_map(root)
    for element in list(root.iter()):
        if local_name(element.tag) != "a":
            continue
        if element.attrib.get("data-type") != "indexterm":
            continue
        if element.attrib.get("href"):
            continue
        if normalize_text("".join(element.itertext())):
            continue
        parent = parents.get(element)
        if parent is None:
            continue
        element_id = element.attrib.get("id")
        if element_id:
            ns = namespace_for(element.tag)
            marker = ET.Element(qname(ns, "span"), {"id": element_id})
            marker.text = "\u200b"
            replace_child_preserving_tail(parent, element, marker)
        else:
            remove_child_preserving_tail(parent, element)


def has_skipped_ancestor(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    current = parents.get(element)
    while current is not None:
        if should_skip_element(current):
            return True
        current = parents.get(current)
    return False


def should_skip_element(element: ET.Element) -> bool:
    return (
        local_name(element.tag) in SKIP_ANCESTORS
        or has_any_class(element, SKIP_CLASS_NAMES)
        or element.attrib.get("id") in SKIP_IDS
    )


def should_skip_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in SKIP_TEXT_PATTERNS)


def next_sibling(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> ET.Element | None:
    parent = parents.get(element)
    if parent is None:
        return None
    siblings = list(parent)
    try:
        index = siblings.index(element)
    except ValueError:
        return None
    if index + 1 >= len(siblings):
        return None
    return siblings[index + 1]


def is_already_translated(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    if has_class(element, "bilingual-translation"):
        return True
    if descendants_with_class(element, "bilingual-translation"):
        return True
    sibling = next_sibling(element, parents)
    return sibling is not None and has_class(sibling, "bilingual-translation")


def collect_segments(root: ET.Element, min_chars: int = 2) -> list[tuple[ET.Element, Segment]]:
    parents = parent_map(root)
    result: list[tuple[ET.Element, Segment]] = []
    for index, element in enumerate(root.iter()):
        if local_name(element.tag) not in BLOCK_TAGS:
            continue
        if should_skip_element(element) or has_skipped_ancestor(element, parents) or is_already_translated(element, parents):
            continue
        text, protected_inlines = protected_segment_text(element)
        translatable_text = translatable_text_without_placeholders(text, protected_inlines)
        if len(translatable_text) < min_chars:
            continue
        if should_skip_text(text):
            continue
        result.append(
            (
                element,
                Segment(
                    id=f"s{index}",
                    text=text,
                    tag=local_name(element.tag),
                    protected_inlines=protected_inlines,
                ),
            )
        )
    return result


def ensure_style(root: ET.Element) -> None:
    ns = namespace_for(root.tag)
    head = next((el for el in root.iter() if local_name(el.tag) == "head"), None)
    if head is None:
        return
    for child in list(head):
        if local_name(child.tag) == "style" and child.attrib.get("id") == "bilingual-style":
            return
    style = ET.Element(qname(ns, "style"), {"id": "bilingual-style", "type": "text/css"})
    style.text = "\n" + BILINGUAL_CSS + "\n"
    head.append(style)


def append_translation_text(parent: ET.Element, text: str) -> None:
    if not text:
        return
    children = list(parent)
    if children:
        last_child = children[-1]
        last_child.tail = (last_child.tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def set_translation_content(
    element: ET.Element,
    translation: str,
    protected_inlines: tuple[ProtectedInline, ...],
) -> None:
    translation = translation.replace(GENERIC_INLINE_PLACEHOLDER, "")
    protected_by_placeholder = {protected.placeholder: protected for protected in protected_inlines}
    cursor = 0
    for match in INLINE_PLACEHOLDER_RE.finditer(translation):
        append_translation_text(element, translation[cursor : match.start()])
        protected = protected_by_placeholder.get(match.group(0))
        if protected is None:
            # Unknown placeholders come from model drift; do not leak them into the EPUB.
            pass
        else:
            element.append(copy.deepcopy(protected.element))
        cursor = match.end()
    append_translation_text(element, translation[cursor:])


def add_translation_after(
    element: ET.Element,
    translation: str,
    parents: dict[ET.Element, ET.Element],
    protected_inlines: tuple[ProtectedInline, ...] = (),
) -> bool:
    parent = parents.get(element)
    if parent is None:
        return False

    ns = namespace_for(element.tag)
    translation_element = ET.Element(
        qname(ns, "p"),
        {
            "class": "bilingual-translation",
            "data-bilingual": "translation",
        },
    )
    set_translation_content(translation_element, translation, protected_inlines)

    add_class(element, "bilingual-original")
    element.set("data-bilingual", "original")

    siblings = list(parent)
    index = siblings.index(element)
    translation_element.tail = element.tail
    element.tail = "\n"
    parent.insert(index + 1, translation_element)
    return True


def ensure_xhtml_doctype(content: bytes) -> bytes:
    if re.search(rb"<!DOCTYPE\s+html", content, flags=re.IGNORECASE):
        return content

    xml_decl = re.match(rb"\s*<\?xml[^?]*\?>", content)
    if xml_decl:
        split_at = xml_decl.end()
        return content[:split_at] + b"\n<!DOCTYPE html>" + content[split_at:]
    return b"<!DOCTYPE html>\n" + content


def restyle_bilingual_xhtml(
    content: bytes,
    *,
    style_css: str | None = None,
    number_headings: bool = False,
    heading_counters: list[int] | None = None,
    heading_numbers: dict[str, str] | None = None,
    document_path: str | None = None,
) -> bytes:
    root = ET.fromstring(content)
    ns = namespace_for(root.tag)
    remove_invisible_index_terms(root)
    head = next((el for el in root.iter() if local_name(el.tag) == "head"), None)
    if head is not None:
        for child in list(head):
            child_name = local_name(child.tag)
            if child_name == "style" or child_name == "link":
                head.remove(child)
        style = ET.Element(qname(ns, "style"), {"id": "bilingual-clean-style", "type": "text/css"})
        style.text = "\n" + (style_css or CLEAN_BILINGUAL_CSS) + "\n"
        head.append(style)

    for element in root.iter():
        element.attrib.pop("style", None)
        classes = element.attrib.get("class")
        if classes is not None:
            kept_classes = [
                class_name
                for class_name in classes.split()
                if class_name in {"bilingual-original", "bilingual-translation", "bilingual-heading-number"}
            ]
            if kept_classes:
                element.set("class", " ".join(kept_classes))
            else:
                element.attrib.pop("class", None)

    body = next((el for el in root.iter() if local_name(el.tag) == "body"), None)
    if body is not None:
        body.set("class", "bilingual-clean")

    if number_headings and should_number_document_headings(document_path):
        number_document_headings(
            root,
            heading_counters if heading_counters is not None else [0, 0, 0],
            document_path=document_path,
            heading_numbers=heading_numbers,
        )

    ET.indent(root, space="  ")
    serialized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return ensure_xhtml_doctype(serialized)


def should_number_document_headings(document_path: str | None) -> bool:
    if document_path is None:
        return True
    filename = posixpath.basename(document_path).lower()
    stem = filename.rsplit(".", 1)[0]
    return not any(part in stem for part in SKIP_HEADING_NUMBER_DOCUMENT_PARTS)


def number_document_headings(
    root: ET.Element,
    counters: list[int],
    *,
    document_path: str | None = None,
    heading_numbers: dict[str, str] | None = None,
) -> None:
    parents = parent_map(root)
    level_offset = 0
    for element in root.iter():
        level = NUMBERED_HEADING_TAGS.get(local_name(element.tag))
        if level is None:
            continue
        if should_skip_element(element) or has_skipped_ancestor(element, parents):
            continue

        text = element_text(element)
        if heading_numbers is not None:
            number = heading_number_for_element(element, parents, document_path, heading_numbers)
            if number is not None and parse_heading_number(text, level) is None:
                insert_heading_number(element, number)
            continue

        if level == 1 and CHAPTER_NUMBER_RE.match(text):
            existing_number = parse_heading_number(text, level)
            if existing_number is not None:
                sync_heading_counters(counters, existing_number)
                level_offset = 1
                continue

        effective_level = min(level + level_offset, len(counters))
        existing_number = parse_heading_number(text, level)
        if existing_number is not None:
            sync_heading_counters(counters, existing_number)
            continue

        generated = next_heading_number(counters, effective_level)
        insert_heading_number(element, generated)


def heading_number_for_element(
    element: ET.Element,
    parents: dict[ET.Element, ET.Element],
    document_path: str | None,
    heading_numbers: dict[str, str],
) -> str | None:
    if not document_path:
        return None
    current: ET.Element | None = element
    while current is not None:
        element_id = current.attrib.get("id")
        if element_id:
            return heading_numbers.get(f"{document_path}#{element_id}")
        current = parents.get(current)
    return None


def parse_heading_number(text: str, level: int) -> str | None:
    match = LEADING_NUMBER_RE.match(text)
    if match is not None:
        return match.group(1)
    if level == 1:
        chapter_match = CHAPTER_NUMBER_RE.match(text)
        if chapter_match is not None:
            return chapter_match.group(1)
    return None


def sync_heading_counters(counters: list[int], number: str) -> None:
    parts = [int(part) for part in number.split(".")[: len(counters)] if part.isdigit()]
    if not parts:
        return
    for index, part in enumerate(parts):
        counters[index] = part
    for index in range(len(parts), len(counters)):
        counters[index] = 0


def next_heading_number(counters: list[int], level: int) -> str:
    index = level - 1
    for parent_index in range(index):
        if counters[parent_index] == 0:
            counters[parent_index] = 1
    counters[index] += 1
    for child_index in range(index + 1, len(counters)):
        counters[child_index] = 0
    return ".".join(str(value) for value in counters[:level])


def insert_heading_number(element: ET.Element, number: str) -> None:
    ns = namespace_for(element.tag)
    marker = ET.Element(qname(ns, "span"), {"class": "bilingual-heading-number"})
    marker.text = f"{number} "
    marker.tail = element.text
    element.text = None
    element.insert(0, marker)


def bilingualize_xhtml(
    content: bytes,
    translations: dict[str, str] | None = None,
    min_chars: int = 2,
) -> tuple[bytes, list[Segment]] | BilingualizeResult:
    """Collect translatable segments or insert translations into an XHTML document.

    When translations is None, returns (unchanged_content, segments). When translations
    is supplied, returns BilingualizeResult with translated paragraph nodes inserted.
    """
    root = ET.fromstring(content)
    element_segments = collect_segments(root, min_chars=min_chars)
    segments = [segment for _, segment in element_segments]
    if translations is None:
        return content, segments

    ensure_style(root)
    parents = parent_map(root)
    inserted = 0
    for element, segment in element_segments:
        translated = translations.get(segment.id)
        if not translated:
            continue
        if add_translation_after(element, translated, parents, segment.protected_inlines):
            inserted += 1

    serialized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return BilingualizeResult(content=ensure_xhtml_doctype(serialized), segments=inserted)
