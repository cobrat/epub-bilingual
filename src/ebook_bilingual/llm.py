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


TRANSLATION_PROMPT_VERSION = "2026-04-27-v3"


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
            self.values[key] = value

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self.values, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write("\n")
            tmp.replace(self.path)


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


class CachedTranslator:
    def __init__(
        self,
        translator: Translator,
        cache: TranslationCache,
        model: str,
        source_language: str,
        target_language: str,
        cache_namespace: str = "",
    ) -> None:
        self.translator = translator
        self.cache = cache
        self.model = model
        self.source_language = source_language
        self.target_language = target_language
        self.cache_namespace = cache_namespace

    def translate_batch(self, texts: list[str]) -> list[str]:
        results: list[str | None] = []
        missing_indexes: list[int] = []
        missing_texts: list[str] = []
        for index, text in enumerate(texts):
            key = cache_key(self.model, self.source_language, self.target_language, text, self.cache_namespace)
            cached = self.cache.get(key)
            results.append(cached)
            if cached is None:
                missing_indexes.append(index)
                missing_texts.append(text)

        if missing_texts:
            translated = self.translator.translate_batch(missing_texts)
            for index, value in zip(missing_indexes, translated, strict=True):
                key = cache_key(self.model, self.source_language, self.target_language, texts[index], self.cache_namespace)
                self.cache.set(key, value)
                results[index] = value
            self.cache.save()

        return [value if value is not None else "" for value in results]

    def cached_count(self, texts: list[str]) -> int:
        count = 0
        for text in texts:
            key = cache_key(self.model, self.source_language, self.target_language, text, self.cache_namespace)
            if self.cache.get(key) is not None:
                count += 1
        return count


class MockTranslator:
    def translate_batch(self, texts: list[str]) -> list[str]:
        return [f"[译文占位] {text}" for text in texts]


class OpenAICompatibleTranslator:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        source_language: str = "auto",
        target_language: str = "Simplified Chinese",
        timeout: int = 120,
        retries: int = 3,
        terminology: list[TerminologyEntry] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.source_language = source_language
        self.target_language = target_language
        self.timeout = timeout
        self.retries = retries
        self.terminology = terminology or []

    @property
    def chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

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
                if translation is not None:
                    return [translation]
            return self._translate_one_by_one(texts)
        if len(translations) != len(texts):
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
        return {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }

    def _translate_one_by_one(self, texts: list[str]) -> list[str]:
        return [self._translate_single_with_format_retries(text) for text in texts]

    def _translate_single_with_format_retries(self, text: str) -> str:
        payload = self._translation_payload([text])
        for _ in range(max(self.retries, 1)):
            content = self._post_json(payload)
            translation = parse_single_translation_response(content)
            if translation is not None:
                return translation

        plain_payload = self._single_text_translation_payload(text)
        for _ in range(max(self.retries, 1)):
            content = self._post_json(plain_payload)
            translation = parse_single_translation_response(content) or clean_plain_translation(content)
            if translation:
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
        return {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        }

    def _post_json(self, payload: dict) -> str:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            req = request.Request(self.chat_completions_url, data=body, headers=headers, method="POST")
            try:
                with request.urlopen(req, timeout=self.timeout) as resp:
                    response_data = json.loads(resp.read().decode("utf-8"))
                return response_data["choices"][0]["message"]["content"]
            except (error.HTTPError, error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(min(2**attempt, 10))

        raise RuntimeError(f"LLM request failed after {self.retries} attempts: {last_error}") from last_error


def parse_json_string_array(content: str) -> list[str]:
    cleaned = clean_model_content(content)

    try:
        data = json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1], strict=False)

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
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start : end + 1], strict=False)
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
