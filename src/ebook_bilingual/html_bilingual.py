from __future__ import annotations

from dataclasses import dataclass
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

SKIP_ANCESTORS = {"script", "style", "nav", "code", "pre", "svg", "math"}
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
class Segment:
    id: str
    text: str
    tag: str = "p"


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
        text = element_text(element)
        if len(text) < min_chars:
            continue
        if should_skip_text(text):
            continue
        result.append((element, Segment(id=f"s{index}", text=text, tag=local_name(element.tag))))
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


def add_translation_after(element: ET.Element, translation: str, parents: dict[ET.Element, ET.Element]) -> bool:
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
    translation_element.text = translation

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


def restyle_bilingual_xhtml(content: bytes, *, style_css: str | None = None) -> bytes:
    root = ET.fromstring(content)
    ns = namespace_for(root.tag)
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
                if class_name in {"bilingual-original", "bilingual-translation"}
            ]
            if kept_classes:
                element.set("class", " ".join(kept_classes))
            else:
                element.attrib.pop("class", None)

    body = next((el for el in root.iter() if local_name(el.tag) == "body"), None)
    if body is not None:
        body.set("class", "bilingual-clean")

    ET.indent(root, space="  ")
    serialized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return ensure_xhtml_doctype(serialized)


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
        if add_translation_after(element, translated, parents):
            inserted += 1

    serialized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return BilingualizeResult(content=ensure_xhtml_doctype(serialized), segments=inserted)
