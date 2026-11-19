"""Request language and server-side English for exam content.

Exam and question-bank text is not in the public catalog: that file is served without a session, and
it would hand out questions and explanations. These routes translate on the server instead, only in
responses, so grading and stored records keep the Vietnamese source.
"""
from __future__ import annotations

import json
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "i18n" / "sensitive_en.json"
SUPPORTED = ("vi", "en")
# Reviews and test reports hold no learner data that this could match by accident, and nothing edits them.
TRANSLATED_PATHS = ("/api/v1/career-process/exam", "/api/v1/tests", "/micro-tests", "/api/v1/micro-tests")
_language: ContextVar[str] = ContextVar("language", default="vi")
_base: dict[str, str] | None = None
_catalog: dict[str, str] | None = None
_descriptions: list[tuple[str, str]] = []
# Answers, code output and the learner's own words are never translated.
LEARNER_KEYS = frozenset({"answer", "answer_text", "text", "stdout", "output_text", "traceback", "rows", "figures"})
# Translations that live in the database (questions written by experts, 5.35). Each source is
# (version, pairs): version is cheap and changes whenever pairs would; pairs returns
# (exact, phrases), where phrases may also be replaced inside a longer sentence.
_sources: list[tuple[Callable[[], Any], Callable[[], tuple[dict[str, str], dict[str, str]]]]] = []
_source_version: Any = None


def register_source(version: Callable[[], Any], pairs: Callable[[], tuple[dict[str, str], dict[str, str]]]) -> None:
    global _catalog
    _sources.append((version, pairs))
    _catalog = None


def set_language(value: str | None) -> None:
    _language.set(value if value in SUPPORTED else "vi")


def current() -> str:
    return _language.get()


def is_english() -> bool:
    return current() == "en"


def reply_language() -> str:
    return "English" if is_english() else "Vietnamese"


def _phrases(entries: dict[str, str]) -> list[tuple[str, str]]:
    pairs = [(source, target) for source, target in entries.items() if len(source) >= 8 and target]
    # A topic can appear in lower case inside the verdict sentence.
    return pairs + [(source.lower(), target[0].lower() + target[1:]) for source, target in pairs]


def catalog() -> dict[str, str]:
    global _base, _catalog, _descriptions, _source_version
    if _base is None:
        _base = json.loads(CATALOG_PATH.read_text(encoding="utf-8")) if CATALOG_PATH.exists() else {}
    version = tuple(read() for read, _ in _sources)
    if _catalog is None or version != _source_version:
        exact: dict[str, str] = {}
        phrases: dict[str, str] = {}
        for _, pairs in _sources:
            more_exact, more_phrases = pairs()
            exact.update(more_exact)
            phrases.update(more_phrases)
        # The reviewed catalog wins when both hold the same Vietnamese text.
        _catalog = {**exact, **_base}
        # Longest first, so a short label never replaces part of a longer one.
        _descriptions = sorted(_phrases(_base) + _phrases({key: value for key, value in phrases.items() if key not in _base}), key=lambda item: -len(item[0]))
        _source_version = version
    return _catalog


def _key(text: str) -> str:
    return text.strip()


def localize(value: Any) -> Any:
    """Exact text first, then known exam text inside a composed sentence such as an explanation."""
    return _localize(value, catalog(), _descriptions)


def _localize(value: Any, entries: dict[str, str], phrases: list[tuple[str, str]]) -> Any:
    if isinstance(value, str):
        hit = entries.get(_key(value))
        if hit is not None:
            return hit
        if re.search(r"[^\x00-\x7f]", value):
            for source, target in phrases:
                if source in value:
                    value = value.replace(source, target)
        return value
    if isinstance(value, list):
        return [_localize(item, entries, phrases) for item in value]
    if isinstance(value, dict):
        # A choice {"id", "text"} is question content; any other "text" may be what the learner wrote.
        keep = LEARNER_KEYS - {"text"} if set(value) == {"id", "text"} else LEARNER_KEYS
        return {key: (item if key in keep else _localize(item, entries, phrases)) for key, item in value.items()}
    return value


def should_translate(path: str) -> bool:
    return is_english() and path.startswith(TRANSLATED_PATHS)
