from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("\u3000", " ")
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def compact_text(value: str) -> str:
    return normalize_text(value).replace(" ", "")


def text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, compact_text(left), compact_text(right)).ratio()


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insertions = previous[j] + 1
            deletions = current[j - 1] + 1
            substitutions = previous[j - 1] + (left_char != right_char)
            current.append(min(insertions, deletions, substitutions))
        previous = current
    return previous[-1]


def character_error_rate(left: str, right: str) -> float:
    left_norm = compact_text(left)
    right_norm = compact_text(right)
    if not right_norm:
        return 0.0 if not left_norm else 1.0
    return levenshtein_distance(left_norm, right_norm) / len(right_norm)


def word_error_rate(left: str, right: str) -> float:
    left_words = normalize_text(left).split()
    right_words = normalize_text(right).split()
    if not right_words:
        return 0.0 if not left_words else 1.0
    return _sequence_distance(left_words, right_words) / len(right_words)


def _sequence_distance(left: list[str], right: list[str]) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            insertions = previous[j] + 1
            deletions = current[j - 1] + 1
            substitutions = previous[j - 1] + (left_item != right_item)
            current.append(min(insertions, deletions, substitutions))
        previous = current
    return previous[-1]
