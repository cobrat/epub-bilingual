from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Protocol
from urllib import error, request
from urllib.parse import urlparse, urlsplit, urlunsplit

from .profiling import ProfileMetrics


TRANSLATION_PROMPT_VERSION = "2026-04-27-v3"
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"
INLINE_PLACEHOLDER_RE = re.compile(r"__EBOOK_BILINGUAL_KEEP_\d+__")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*")
TRANSLATABLE_ENGLISH_HINTS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "best",
    "between",
    "build",
    "can",
    "causes",
    "continued",
    "costs",
    "data",
    "default",
    "detect",
    "do",
    "does",
    "faster",
    "feedback",
    "first",
    "for",
    "from",
    "how",
    "in",
    "increased",
    "is",
    "latency",
    "make",
    "mitigate",
    "model",
    "not",
    "of",
    "on",
    "or",
    "practices",
    "query",
    "rank",
    "respond",
    "response",
    "return",
    "see",
    "such",
    "the",
    "this",
    "time",
    "to",
    "token",
    "use",
    "what",
    "when",
    "why",
    "with",
    "work",
    "your",
}


def is_ollama_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()
    return parsed.port == 11434 or "ollama" in hostname


def ollama_server_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    for suffix in ("/v1/chat/completions", "/v1", "/api/chat", "/api/generate"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def fetch_ollama_models(base_url: str = OLLAMA_DEFAULT_BASE_URL, *, timeout: float = 2.0) -> list[str]:
    tags_url = f"{ollama_server_url(base_url)}/api/tags"
    req = request.Request(tags_url, headers={"Accept": "application/json"}, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = []
    for item in models:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
        elif isinstance(item, str):
            names.append(item)
    return sorted(dict.fromkeys(names))


class Translator(Protocol):
    def translate_batch(self, texts: list[str]) -> list[str]:
        ...


@dataclass(frozen=True)
class TerminologyEntry:
    source: str
    target: str
    note: str = ""


@dataclass
class TranslationCache:
    path: Path | None
    values: dict[str, str]
    dirty: bool = False
    _lock: threading.RLock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()

    @classmethod
    def load(cls, path: Path | None) -> "TranslationCache":
        if path is None or not path.exists():
            return cls(path=path, values={})
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Cache file must contain a JSON object: {path}")
        return cls(path=path, values={str(key): str(value) for key, value in data.items()})

    def get(self, key: str) -> str | None:
        with self._lock:
            return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            if self.values.get(key) == value:
                return
            self.values[key] = value
            self.dirty = True

    def save(self, *, force: bool = False) -> None:
        if self.path is None:
            return
        with self._lock:
            if not force and not self.dirty:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self.values, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write("\n")
            tmp.replace(self.path)
            self.dirty = False


def cache_key(
    model: str,
    source_language: str,
    target_language: str,
    text: str,
    cache_namespace: str = "",
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "source_language": source_language,
            "target_language": target_language,
            "translation_prompt_version": TRANSLATION_PROMPT_VERSION,
            "cache_namespace": cache_namespace,
            "text": text,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def target_prefers_cjk(target_language: str) -> bool:
    normalized = target_language.lower()
    return any(marker in normalized for marker in ("chinese", "simplified", "traditional", "mandarin", "中文", "汉语", "漢語"))


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def translation_quality_text(text: str) -> str:
    text = INLINE_PLACEHOLDER_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    return normalize_quality_text(text)


def normalize_quality_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def latin_words(text: str) -> list[str]:
    return LATIN_WORD_RE.findall(translation_quality_text(text))


def looks_like_identifier_or_reference(text: str) -> bool:
    words = latin_words(text)
    if not words:
        return True
    lowered = [word.lower() for word in words]
    if any(word in TRANSLATABLE_ENGLISH_HINTS for word in lowered):
        return False
    return len(words) <= 8


def is_probably_untranslated(source: str, translation: str, target_language: str) -> bool:
    if not target_prefers_cjk(target_language):
        return False
    source_text = translation_quality_text(source)
    translated_text = translation_quality_text(translation)
    if not translated_text:
        return not looks_like_identifier_or_reference(source)
    if has_cjk(translated_text):
        return False
    source_words = latin_words(source_text)
    translated_words = latin_words(translated_text)
    if not translated_words:
        return False
    if looks_like_identifier_or_reference(source_text) and len(translated_words) < 10:
        return False
    if normalize_quality_text(source_text) == normalize_quality_text(translated_text) and len(source_words) >= 2:
        return True
    if len(source_words) >= 4 and len(translated_words) >= 4:
        return True
    return len(translated_words) >= 8


class CachedTranslator:
    def __init__(
        self,
        translator: Translator,
        cache: TranslationCache,
        model: str,
        source_language: str,
        target_language: str,
        cache_namespace: str = "",
        autosave: bool = True,
        profile_metrics: ProfileMetrics | None = None,
    ) -> None:
        self.translator = translator
        self.cache = cache
        self.model = model
        self.source_language = source_language
        self.target_language = target_language
        self.cache_namespace = cache_namespace
        self.autosave = autosave
        self.profile_metrics = profile_metrics
        self._inflight_lock = threading.RLock()
        self._inflight: dict[str, threading.Event] = {}

    def translate_batch(self, texts: list[str]) -> list[str]:
        results: list[str | None] = []
        owned_keys: list[str] = []
        owned_texts: list[str] = []
        owned_indexes: dict[str, list[int]] = {}
        waiting_indexes: dict[str, tuple[threading.Event, list[int]]] = {}
        for index, text in enumerate(texts):
            key = self.cache_key_for_text(text)
            cached = self.cache.get(key)
            if cached is not None and is_probably_untranslated(text, cached, self.target_language):
                cached = None
            results.append(cached)
            if cached is not None:
                continue
            if key in owned_indexes:
                owned_indexes[key].append(index)
                continue

            with self._inflight_lock:
                cached = self.cache.get(key)
                if cached is not None and is_probably_untranslated(text, cached, self.target_language):
                    cached = None
                if cached is not None:
                    results[index] = cached
                    continue
                event = self._inflight.get(key)
                if event is None:
                    event = threading.Event()
                    self._inflight[key] = event
                    owned_keys.append(key)
                    owned_texts.append(text)
                    owned_indexes[key] = [index]
                else:
                    _, indexes = waiting_indexes.setdefault(key, (event, []))
                    indexes.append(index)

        try:
            if owned_texts:
                translated = self.translator.translate_batch(owned_texts)
                for key, text, value in zip(owned_keys, owned_texts, translated, strict=True):
                    if not is_probably_untranslated(text, value, self.target_language):
                        self.cache.set(key, value)
                    for index in owned_indexes[key]:
                        results[index] = value
                if self.autosave:
                    self.cache.save()
        finally:
            if owned_keys:
                with self._inflight_lock:
                    for key in owned_keys:
                        event = self._inflight.pop(key, None)
                        if event is not None:
                            event.set()

        for key, (event, indexes) in waiting_indexes.items():
            event.wait()
            cached = self.cache.get(key)
            if cached is None:
                raise RuntimeError("Concurrent translation failed before cache was populated")
            for index in indexes:
                results[index] = cached

        return [value if value is not None else "" for value in results]

    def cached_count(self, texts: list[str]) -> int:
        count = 0
        for text in texts:
            key = self.cache_key_for_text(text)
            cached = self.cache.get(key)
            if cached is not None and not is_probably_untranslated(text, cached, self.target_language):
                count += 1
        return count

    def cached_batch(self, texts: list[str]) -> list[str | None]:
        values: list[str | None] = []
        for text in texts:
            cached = self.cache.get(self.cache_key_for_text(text))
            if cached is not None and is_probably_untranslated(text, cached, self.target_language):
                cached = None
            values.append(cached)
        return values

    def cache_key_for_text(self, text: str) -> str:
        return cache_key(self.model, self.source_language, self.target_language, text, self.cache_namespace)


class MockTranslator:
    def translate_batch(self, texts: list[str]) -> list[str]:
        return [f"[译文占位] {text}" for text in texts]


class OpenAICompatibleTranslator:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        source_language: str = "auto",
        target_language: str = "Simplified Chinese",
        timeout: int = 120,
        retries: int = 3,
        terminology: list[TerminologyEntry] | None = None,
        profile_metrics: ProfileMetrics | None = None,
    ) -> None:
        self.api_key = api_key or ""
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.source_language = source_language
        self.target_language = target_language
        self.timeout = timeout
        self.retries = retries
        self.terminology = terminology or []
        self.profile_metrics = profile_metrics

    @property
    def chat_completions_url(self) -> str:
        parts = urlsplit(self.base_url)
        path = parts.path.rstrip("/")
        if path.endswith("/chat/completions"):
            return self.base_url
        path = f"{path}/chat/completions" if path else "/chat/completions"
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []

        payload = self._translation_payload(texts)
        content = self._post_json(payload)
        try:
            translations = parse_json_string_array(content)
        except (ValueError, json.JSONDecodeError):
            if len(texts) == 1:
                translation = parse_single_translation_response(content)
                if translation is not None and not is_probably_untranslated(texts[0], translation, self.target_language):
                    return [translation]
            self._record_fallback()
            return self._translate_one_by_one(texts)
        if len(translations) != len(texts):
            self._record_fallback()
            return self._translate_one_by_one(texts)
        if any(is_probably_untranslated(source, translation, self.target_language) for source, translation in zip(texts, translations, strict=True)):
            self._record_fallback()
            return self._translate_one_by_one(texts)
        return translations

    def _translation_payload(self, texts: list[str]) -> dict:
        system_prompt = (
            "You are a professional literary translator preparing bilingual EPUB text.\n\n"
            f"Translate each input segment from {self.source_language} to {self.target_language}.\n\n"
            "Requirements:\n"
            "- Return only a valid JSON array of strings. No Markdown, no code fences, no explanations.\n"
            "- The array length must be exactly the same as the input segments length.\n"
            "- Each output item must correspond to the input segment at the same index.\n"
            f"- For literary text, prefer fluent, natural {self.target_language} over word-for-word translation.\n"
            "- Preserve the original meaning, tone, tense, names, numbers, and punctuation intent.\n"
            "- Keep paragraph boundaries: do not merge, split, summarize, or omit segments.\n"
            "- Preserve proper nouns using common established translations when they exist.\n"
            "- Preserve placeholder tokens like __EBOOK_BILINGUAL_KEEP_0__ exactly; do not translate, remove, or reorder them.\n"
            "- Do not add translator notes, comments, headings, or extra context.\n"
            f"- If a segment is already in {self.target_language}, return it unchanged."
        )
        if self.terminology:
            system_prompt += "\n\nTerminology:\n" + format_terminology(self.terminology)
        user_payload = {
            "source_language": self.source_language,
            "target_language": self.target_language,
            "task": "Translate EPUB text segments for bilingual paragraph-by-paragraph reading.",
            "segments": texts,
        }
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }
        return self._adapt_payload_for_provider(payload)

    def _translate_one_by_one(self, texts: list[str]) -> list[str]:
        return [self._translate_single_with_format_retries(text) for text in texts]

    def _translate_single_with_format_retries(self, text: str) -> str:
        payload = self._translation_payload([text])
        for _ in range(max(self.retries, 1)):
            content = self._post_json(payload)
            translation = parse_single_translation_response(content)
            if translation is not None and not is_probably_untranslated(text, translation, self.target_language):
                return translation

        plain_payload = self._single_text_translation_payload(text)
        self._record_fallback()
        for _ in range(max(self.retries, 1)):
            content = self._post_json(plain_payload)
            translation = parse_single_translation_response(content) or clean_plain_translation(content)
            if translation and not is_probably_untranslated(text, translation, self.target_language):
                return translation
        return text

    def _single_text_translation_payload(self, text: str) -> dict:
        system_prompt = (
            "You are a professional literary translator preparing bilingual EPUB text.\n\n"
            f"Translate the input segment from {self.source_language} to {self.target_language}.\n\n"
            "Requirements:\n"
            "- Return only the translated text. No JSON, Markdown, code fences, or explanations.\n"
            f"- Prefer fluent, natural {self.target_language} over word-for-word translation.\n"
            "- Preserve the original meaning, tone, tense, names, numbers, and punctuation intent.\n"
            "- Preserve placeholder tokens like __EBOOK_BILINGUAL_KEEP_0__ exactly; do not translate, remove, or reorder them.\n"
            f"- If the segment is already in {self.target_language}, return it unchanged."
        )
        if self.terminology:
            system_prompt += "\n\nTerminology:\n" + format_terminology(self.terminology)
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        }
        return self._adapt_payload_for_provider(payload)

    def _adapt_payload_for_provider(self, payload: dict) -> dict:
        if self._is_kimi_k2():
            payload = dict(payload)
            payload.pop("temperature", None)
            payload.setdefault("thinking", {"type": "disabled"})
        return payload

    def _is_kimi_k2(self) -> bool:
        parsed = urlparse(self.base_url)
        return (parsed.hostname or "").lower() == "api.moonshot.cn" and self.model.startswith("kimi-k2")

    def _post_json(self, payload: dict) -> str:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            req = request.Request(self.chat_completions_url, data=body, headers=headers, method="POST")
            try:
                self._record_raw_llm_request()
                with request.urlopen(req, timeout=self.timeout) as resp:
                    response_data = json.loads(resp.read().decode("utf-8"))
                return response_data["choices"][0]["message"]["content"]
            except (error.HTTPError, error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                self._record_retry()
                time.sleep(min(2**attempt, 10))

        raise RuntimeError(f"LLM request failed after {self.retries} attempts: {last_error}") from last_error

    def _record_raw_llm_request(self) -> None:
        if self.profile_metrics is not None:
            self.profile_metrics.record_raw_llm_request()

    def _record_fallback(self) -> None:
        if self.profile_metrics is not None:
            self.profile_metrics.record_fallback()

    def _record_retry(self) -> None:
        if self.profile_metrics is not None:
            self.profile_metrics.record_retry()


def parse_json_string_array(content: str) -> list[str]:
    data = parse_json_payload(content, "[", "]")

    if isinstance(data, dict):
        for key in ("translations", "translated", "items", "results", "output"):
            value = data.get(key)
            if isinstance(value, list):
                data = value
                break

    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("Model response must be a JSON array of strings.")
    return data


def parse_single_translation_response(content: str) -> str | None:
    try:
        values = parse_json_string_array(content)
    except (ValueError, json.JSONDecodeError):
        values = []
    if len(values) == 1:
        return values[0]

    cleaned = clean_model_content(content)
    try:
        data = json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        try:
            data = parse_json_payload(content, "{", "}")
        except json.JSONDecodeError:
            return None

    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("translation", "translated", "target", "text", "output", "result", "content"):
            value = data.get(key)
            if isinstance(value, str):
                return value
    return None


def parse_json_payload(content: str, start_char: str, end_char: str) -> object:
    cleaned = clean_model_content(content)
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1], strict=False)


def clean_plain_translation(content: str) -> str:
    cleaned = clean_model_content(content)
    if not cleaned:
        return ""
    if cleaned[0] in "[{":
        return ""
    return cleaned


def clean_model_content(content: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def load_terminology(path: Path) -> list[TerminologyEntry]:
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    entries: list[TerminologyEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        for row in reader:
            if not row:
                continue
            if row[0].strip().startswith("#"):
                continue
            if len(row) < 2:
                continue
            source = row[0].strip()
            target = row[1].strip()
            note = row[2].strip() if len(row) > 2 else ""
            if not source or not target:
                continue
            if source.lower() in {"source", "term", "english"} and target.lower() in {"target", "translation", "chinese"}:
                continue
            entries.append(TerminologyEntry(source=source, target=target, note=note))
    return entries


def format_terminology(entries: list[TerminologyEntry]) -> str:
    lines = []
    for entry in entries:
        line = f"- {entry.source} => {entry.target}"
        if entry.note:
            line += f" ({entry.note})"
        lines.append(line)
    return "\n".join(lines)


def terminology_fingerprint(entries: list[TerminologyEntry]) -> str:
    if not entries:
        return ""
    payload = json.dumps([entry.__dict__ for entry in entries], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
