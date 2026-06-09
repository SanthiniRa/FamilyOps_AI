from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, List


_TOKEN_RE = re.compile(r"[a-z0-9']+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(normalize_text(text))


def sentence_split(text: str) -> List[str]:
    parts = [part.strip() for part in _SENTENCE_RE.split(text.strip()) if part.strip()]
    return parts if parts else ([text.strip()] if text.strip() else [])


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def sequence_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def token_overlap_score(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def best_match_score(text: str, candidates: Iterable[str]) -> float:
    return max((max(jaccard_similarity(text, candidate), sequence_similarity(text, candidate)) for candidate in candidates), default=0.0)


def extract_numeric_tokens(text: str) -> List[str]:
    return re.findall(r"\b\d{1,4}(?:[:/-]\d{1,4})*\b", text)


def extract_capitalized_phrases(text: str) -> List[str]:
    return re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+|[A-Z][a-z]+)\b", text)


def unique_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered

