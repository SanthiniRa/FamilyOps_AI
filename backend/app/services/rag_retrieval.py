from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache
import math
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.config import settings


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "can", "do", "for", "from",
    "get", "give", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "please", "should", "tell", "that", "the", "this", "to", "we",
    "what", "when", "where", "which", "who", "why", "with", "you", "did",
    "does", "had", "have", "has", "our", "need", "up", "out", "about",
}

_DOMAIN_HINTS = {
    "calendar": (
        "calendar", "schedule", "scheduled", "appointment", "meeting", "event",
        "add to my calendar", "add to calendar", "reminder", "invite", "reschedule",
    ),
    "meal": (
        "meal", "meals", "meal plan", "dinner", "lunch", "breakfast", "recipe",
        "recipes", "pantry", "grocery", "shopping list", "ingredients", "cook",
        "diet", "dietary", "vegetarian", "vegan", "gluten-free", "dairy-free",
        "lactose-free", "kid-friendly", "nutrition", "prep time", "budget",
    ),
    "memory": (
        "remember", "memory", "memories", "recall", "saved", "save", "note", "notes",
        "what did we", "which", "where did we", "what was our", "what memory",
    ),
    "email": (
        "email", "mail", "inbox", "sender", "subject", "message", "from the email",
    ),
    "document": (
        "document", "pdf", "docx", "file", "report", "attachment", "uploaded",
    ),
    "general": (
        "summary", "summarize", "status", "dashboard", "overview", "plan",
        "priorities", "focus", "today", "this week", "what should i do",
    ),
}

_MEMORY_TYPE_HINTS = {
    "calendar": {"email", "document", "calendar", "event", "reminder"},
    "meal": {"recipe", "meal_plan", "meal_preferences", "pantry_state", "meal_preference"},
    "memory": {"general", "memory", "preference", "routine", "household", "email", "document"},
    "general": {"general", "task", "reminder", "calendar", "email", "document", "memory"},
}


@dataclass
class Chunk:
    content: str
    metadata: Dict[str, Any]


@dataclass
class BM25Corpus:
    documents: List[List[str]]
    document_frequencies: Dict[str, int]
    average_document_length: float


class CrossEncoderScorer:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self.model = CrossEncoder(model_name)

    def predict(self, pairs: Sequence[Tuple[str, str]]) -> Sequence[float]:
        return self.model.predict(list(pairs))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def tokenize(text: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9']+", normalize_text(text)) if token not in _STOPWORDS]


def sentence_split(text: str) -> List[str]:
    stripped = (text or "").strip()
    if not stripped:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", stripped) if part.strip()]
    return parts if parts else [stripped]


def infer_query_domain(query: str) -> str:
    lowered = normalize_text(query)
    for domain, hints in _DOMAIN_HINTS.items():
        if any(hint in lowered for hint in hints):
            return domain
    return "general"


def candidate_memory_types(query: str, memory_type: Optional[str] = None) -> List[str]:
    domain = infer_query_domain(query)
    if memory_type:
        return [memory_type]
    return list(_MEMORY_TYPE_HINTS.get(domain, _MEMORY_TYPE_HINTS["general"]))


def rewrite_retrieval_query(
    query: str,
    memory_type: Optional[str] = None,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> str:
    tokens = tokenize(query)
    if metadata_filter:
        for value in metadata_filter.values():
            if isinstance(value, str):
                tokens.extend(tokenize(value))
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    tokens.extend(tokenize(str(item)))

    domain = infer_query_domain(query)
    domain_tokens = {
        "calendar": ["calendar", "appointment", "event", "schedule"],
        "meal": ["meal", "recipe", "pantry", "nutrition", "ingredients"],
        "memory": ["memory", "saved", "note", "recall"],
        "email": ["email", "inbox", "message", "subject"],
        "document": ["document", "file", "attachment", "page"],
        "general": ["household", "summary", "status"],
    }.get(domain, [])

    if memory_type:
        domain_tokens.append(memory_type.replace("_", " "))

    tokens.extend(domain_tokens)
    return " ".join(_unique_preserve_order(tokens))


def split_semantic_chunks(
    text: str,
    *,
    max_words: int = 140,
    overlap: int = 20,
) -> List[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", cleaned) if part.strip()]
    if not paragraphs:
        paragraphs = [cleaned]

    chunks: List[str] = []
    current_words: List[str] = []

    def flush() -> None:
        nonlocal current_words
        if current_words:
            chunks.append(" ".join(current_words).strip())
            if overlap > 0:
                current_words = current_words[-overlap:]
            else:
                current_words = []

    for paragraph in paragraphs:
        for sentence in sentence_split(paragraph):
            words = sentence.split()
            if not words:
                continue
            if len(words) > max_words:
                flush()
                for idx in range(0, len(words), max_words - min(overlap, max_words - 1)):
                    pieces = words[idx: idx + max_words]
                    if pieces:
                        chunks.append(" ".join(pieces).strip())
                current_words = []
                continue

            if len(current_words) + len(words) > max_words:
                flush()
            current_words.extend(words)

        if current_words:
            chunks.append(" ".join(current_words).strip())
            current_words = []

    return [chunk for chunk in _unique_preserve_order(chunks) if chunk]


def chunk_memory_content(
    content: Any,
    memory_type: str = "general",
    metadata: Optional[Dict[str, Any]] = None,
) -> List[Chunk]:
    metadata = dict(metadata or {})
    text = coerce_text_content(content)
    if not text:
        return []

    max_words = {
        "email": 110,
        "document": 140,
        "recipe": 100,
        "meal_plan": 100,
        "meal_preferences": 80,
    }.get(memory_type, settings.rag_memory_chunk_words)
    overlap = 20 if max_words >= 100 else settings.rag_memory_chunk_overlap

    chunks = split_semantic_chunks(text, max_words=max_words, overlap=overlap)
    if not chunks:
        return [Chunk(content=text, metadata=metadata)]

    chunk_count = len(chunks)
    return [
        Chunk(
            content=chunk,
            metadata={
                **metadata,
                "chunk_index": idx,
                "chunk_count": chunk_count,
                "chunk_type": memory_type,
            },
        )
        for idx, chunk in enumerate(chunks)
    ]


def coerce_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, (int, float, bool)):
        return str(content)
    if isinstance(content, dict):
        ordered_keys = [
            "title",
            "subject",
            "summary",
            "content",
            "body",
            "text",
            "notes",
            "ingredients",
            "instructions",
            "meals",
            "shopping_list",
        ]
        parts: List[str] = []
        for key in ordered_keys:
            if key not in content:
                continue
            value = content.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (list, tuple)):
                parts.append(f"{key}: " + ", ".join(coerce_text_content(item) for item in value))
            else:
                parts.append(f"{key}: {coerce_text_content(value)}")

        if not parts:
            try:
                return json.dumps(content, ensure_ascii=True)
            except Exception:
                return str(content)

        for key, value in content.items():
            if key in ordered_keys:
                continue
            if value in (None, "", [], {}):
                continue
            parts.append(f"{key}: {coerce_text_content(value)}")
        return "\n".join(parts)

    if isinstance(content, (list, tuple, set)):
        return "\n".join(coerce_text_content(item) for item in content if item not in (None, "", [], {}))

    return str(content).strip()


def metadata_matches(candidate_metadata: Dict[str, Any], metadata_filter: Optional[Dict[str, Any]]) -> bool:
    if not metadata_filter:
        return True

    for key, expected in metadata_filter.items():
        actual = candidate_metadata.get(key)
        if actual is None:
            actual = candidate_metadata.get("metadata", {}).get(key)

        if isinstance(expected, (list, tuple, set)):
            normalized_expected = {normalize_text(str(value)) for value in expected}
            if isinstance(actual, (list, tuple, set)):
                normalized_actual = {normalize_text(str(value)) for value in actual}
                if not normalized_expected.intersection(normalized_actual):
                    return False
            else:
                if normalize_text(str(actual)) not in normalized_expected:
                    return False
        else:
            if normalize_text(str(actual)) != normalize_text(str(expected)):
                return False

    return True


def build_bm25_corpus(texts: Sequence[str]) -> BM25Corpus:
    tokenized_documents = [tokenize(text) for text in texts if (text or "").strip()]
    if not tokenized_documents:
        return BM25Corpus(documents=[], document_frequencies={}, average_document_length=0.0)

    document_frequencies: Counter[str] = Counter()
    total_length = 0
    for tokens in tokenized_documents:
        document_frequencies.update(set(tokens))
        total_length += len(tokens)

    return BM25Corpus(
        documents=tokenized_documents,
        document_frequencies=dict(document_frequencies),
        average_document_length=total_length / len(tokenized_documents),
    )


def bm25_score(
    query: str,
    document: str,
    corpus: Optional[BM25Corpus] = None,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    query_tokens = list(dict.fromkeys(tokenize(query)))
    document_tokens = tokenize(document)
    if not query_tokens or not document_tokens:
        return 0.0

    corpus = corpus or build_bm25_corpus([document])
    if not corpus.documents or corpus.average_document_length <= 0.0:
        return 0.0

    document_frequencies = corpus.document_frequencies
    document_length = len(document_tokens)
    total_documents = len(corpus.documents)
    term_counts = Counter(document_tokens)

    score = 0.0
    length_normalizer = k1 * (1.0 - b + b * (document_length / corpus.average_document_length))
    for term in query_tokens:
        term_frequency = term_counts.get(term, 0)
        if term_frequency <= 0:
            continue

        document_frequency = document_frequencies.get(term, 0)
        idf = math.log(1.0 + ((total_documents - document_frequency + 0.5) / (document_frequency + 0.5)))
        score += idf * (term_frequency * (k1 + 1.0)) / (term_frequency + length_normalizer)

    return score


def reciprocal_rank_fusion(rankings: Sequence[Sequence[Any]], *, k: int = 60) -> Dict[str, float]:
    fused_scores: Dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            if isinstance(item, dict):
                identifier = item.get("id")
            else:
                identifier = item
            if identifier in (None, ""):
                continue
            fused_scores[str(identifier)] += 1.0 / (k + rank)
    return dict(fused_scores)


def rank_candidates_by_bm25(
    query: str,
    candidates: Sequence[Dict[str, Any]],
    *,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    filtered_candidates: List[Dict[str, Any]] = []
    candidate_texts: List[str] = []

    for candidate in candidates:
        content = (candidate.get("content") or "").strip()
        if not content:
            continue
        if not metadata_matches(candidate, metadata_filter):
            continue

        filtered_candidates.append(dict(candidate))
        candidate_texts.append(_candidate_text(candidate))

    if not filtered_candidates:
        return []

    corpus = build_bm25_corpus(candidate_texts)
    ranked_candidates: List[Dict[str, Any]] = []
    for candidate, candidate_text in zip(filtered_candidates, candidate_texts):
        candidate["bm25_score"] = bm25_score(query, candidate_text, corpus=corpus)
        ranked_candidates.append(candidate)

    ranked_candidates.sort(key=lambda item: item.get("bm25_score", 0.0), reverse=True)
    for rank, candidate in enumerate(ranked_candidates, start=1):
        candidate["bm25_rank"] = rank
    return ranked_candidates


@lru_cache(maxsize=1)
def get_cross_encoder_scorer() -> Optional[CrossEncoderScorer]:
    if not getattr(settings, "enable_cross_encoder_rerank", False):
        return None

    model_name = (getattr(settings, "cross_encoder_model", "") or "").strip()
    if not model_name:
        return None

    try:
        return CrossEncoderScorer(model_name)
    except Exception:
        return None


def cross_encoder_rerank_candidates(
    query: str,
    candidates: Sequence[Dict[str, Any]],
    *,
    top_n: Optional[int] = None,
    scorer: Optional[CrossEncoderScorer] = None,
) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    ranked_candidates = [dict(candidate) for candidate in candidates]
    for candidate in ranked_candidates:
        candidate.setdefault("cross_encoder_score", 0.0)

    scorer = scorer or get_cross_encoder_scorer()
    if scorer is None:
        return ranked_candidates

    limit = len(ranked_candidates) if top_n is None else max(0, min(top_n, len(ranked_candidates)))
    if limit <= 0:
        return ranked_candidates

    scored_slice = ranked_candidates[:limit]
    pairs = [(query, _candidate_text(candidate)) for candidate in scored_slice]

    try:
        predictions = scorer.predict(pairs)
    except Exception:
        return ranked_candidates

    for candidate, score in zip(scored_slice, predictions):
        candidate["cross_encoder_score"] = float(score)

    scored_slice.sort(
        key=lambda item: float(item.get("cross_encoder_score", 0.0) or 0.0),
        reverse=True,
    )
    for rank, candidate in enumerate(scored_slice, start=1):
        candidate["cross_encoder_rank"] = rank

    return scored_slice + ranked_candidates[limit:]


def _candidate_text(candidate: Dict[str, Any]) -> str:
    content = candidate.get("content") or ""
    metadata = candidate.get("metadata") or {}
    citation_bits = [
        str(candidate.get("memory_type") or ""),
        str(metadata.get("source") or candidate.get("source") or ""),
        str(metadata.get("filename") or candidate.get("filename") or ""),
        str(metadata.get("title") or candidate.get("title") or ""),
    ]
    return " ".join([content, *citation_bits]).strip()


def lexical_similarity(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def query_overlap_score(query: str, candidate: Dict[str, Any]) -> float:
    candidate_text = _candidate_text(candidate)
    return max(
        lexical_similarity(query, candidate_text),
        SequenceMatcher(None, normalize_text(query), normalize_text(candidate_text)).ratio(),
    )


def rerank_candidates(
    query: str,
    candidates: Sequence[Dict[str, Any]],
    *,
    limit: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None,
    token_budget: int = 700,
) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    query_tokens = set(tokenize(query))
    query_digits = set(re.findall(r"\d{1,4}", query))
    query_days = set(re.findall(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", query, re.I))

    deduped: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        content = (candidate.get("content") or "").strip()
        if not content:
            continue
        normalized = normalize_text(content)
        if normalized in deduped:
            existing = deduped[normalized]
            existing["score"] = max(existing.get("score", 0.0), candidate.get("score", 0.0))
            continue
        if not metadata_matches(candidate, metadata_filter):
            continue
        candidate = dict(candidate)
        candidate["rerank_score"] = _score_candidate(
            query=query,
            candidate=candidate,
            query_tokens=query_tokens,
            query_digits=query_digits,
            query_days=query_days,
        )
        deduped[normalized] = candidate

    ranked = sorted(deduped.values(), key=lambda item: item.get("rerank_score", item.get("score", 0.0)), reverse=True)
    if token_budget > 0:
        ranked = _apply_token_budget(ranked, token_budget=token_budget, limit=limit)
    for candidate in ranked:
        candidate["score"] = candidate.get("rerank_score", candidate.get("score", 0.0))
    return ranked[:limit]


def _score_candidate(
    *,
    query: str,
    candidate: Dict[str, Any],
    query_tokens: set[str],
    query_digits: set[str],
    query_days: set[str],
) -> float:
    content = candidate.get("content") or ""
    metadata = candidate.get("metadata") or {}

    content_tokens = set(tokenize(content))
    if not content_tokens:
        return 0.0

    lexical = len(query_tokens & content_tokens) / max(1, len(query_tokens | content_tokens))
    sequence = SequenceMatcher(None, normalize_text(query), normalize_text(content)).ratio()
    vector_score = float(candidate.get("vector_score", candidate.get("score", 0.0)) or 0.0)
    lexical_score = float(candidate.get("lexical_score", 0.0) or 0.0)
    bm25 = float(candidate.get("bm25_score", 0.0) or 0.0)
    rrf_score = float(candidate.get("rrf_score", 0.0) or 0.0)
    cross_encoder = float(candidate.get("cross_encoder_score", 0.0) or 0.0)
    recency = float(candidate.get("recency_boost", 0.0) or 0.0)

    metadata_boost = 0.0
    source = normalize_text(str(metadata.get("source") or candidate.get("source") or ""))
    if source and source in normalize_text(query):
        metadata_boost += 0.08
    if query_digits and any(digit in content for digit in query_digits):
        metadata_boost += 0.10
    if query_days and any(day in normalize_text(content) for day in query_days):
        metadata_boost += 0.10
    if metadata.get("filename") and normalize_text(str(metadata["filename"])) in normalize_text(query):
        metadata_boost += 0.06
    if metadata.get("title") and normalize_text(str(metadata["title"])) in normalize_text(query):
        metadata_boost += 0.06

    source_bonus = 0.0
    memory_type = normalize_text(str(candidate.get("memory_type") or metadata.get("memory_type") or ""))
    if memory_type and memory_type in normalize_text(query):
        source_bonus += 0.08

    bm25_bonus = min(1.0, bm25 / (bm25 + 2.5)) if bm25 > 0.0 else 0.0
    rrf_bonus = min(1.0, rrf_score * 30.0) if rrf_score > 0.0 else 0.0
    cross_encoder_bonus = 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, cross_encoder)))) if cross_encoder else 0.0

    combined = (
        0.22 * vector_score
        + 0.14 * max(lexical, lexical_score)
        + 0.14 * bm25_bonus
        + 0.10 * rrf_bonus
        + 0.18 * cross_encoder_bonus
        + 0.10 * sequence
        + 0.06 * recency
        + metadata_boost
        + source_bonus
    )

    return max(0.0, min(1.0, combined))


def _apply_token_budget(candidates: Sequence[Dict[str, Any]], *, token_budget: int, limit: int) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    remaining = token_budget
    for candidate in candidates:
        content = (candidate.get("content") or "").strip()
        if not content:
            continue
        token_count = max(1, len(content.split()))
        if selected and token_count > remaining:
            continue
        selected.append(candidate)
        remaining -= token_count
        if len(selected) >= limit or remaining <= 0:
            break
    return selected


def build_context_from_candidates(
    candidates: Sequence[Dict[str, Any]],
    *,
    token_budget: int = 700,
    max_items: int = 4,
) -> str:
    if not candidates:
        return ""

    lines: List[str] = []
    remaining = token_budget
    for candidate in candidates[:max_items]:
        content = (candidate.get("content") or "").strip()
        if not content:
            continue

        metadata = candidate.get("metadata") or {}
        citation = metadata.get("citation") or metadata.get("filename") or candidate.get("citation") or ""
        prefix_bits = []
        if citation:
            prefix_bits.append(str(citation))
        if candidate.get("memory_type"):
            prefix_bits.append(str(candidate["memory_type"]))
        prefix = f"[{ ' | '.join(prefix_bits) }]" if prefix_bits else ""
        line = f"{prefix} {content}".strip()

        token_count = max(1, len(line.split()))
        if lines and token_count > remaining:
            break

        lines.append(f"- {line}" if not line.startswith("-") else line)
        remaining -= token_count
        if remaining <= 0:
            break

    return "\n".join(lines)


def _unique_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if not value:
            continue
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered
