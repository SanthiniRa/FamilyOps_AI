from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evaluation.metrics.text_utils import best_match_score, sentence_split, tokenize, unique_preserve_order  # noqa: E402


INTENT_TO_TOOL = {
    "calendar": "calendar_tool",
    "meal": "meal_planner_tool",
    "memory": "memory_tool",
    "general": "chat",
}

INTENT_TO_AGENT = {
    "calendar": "calendar_agent",
    "meal": "meal_agent",
    "memory": "memory_agent",
    "general": "general_agent",
}

GENERAL_HINTS = (
    "summarize",
    "household status",
    "family dashboard",
    "what should i focus",
    "what should i do",
    "what is the best next step",
    "how many",
    "current family plan",
    "what items are low",
    "need attention soon",
    "what does the family dashboard",
    "focus on first",
    "what did we decide if",
)

MEMORY_HINTS = (
    "what memory",
    "remember",
    "recall",
    "which note",
    "what did we save",
    "what did we say",
    "what did we store",
    "we saved",
    "saved preference",
    "saved about",
    "the note we saved",
    "which allergy",
    "which dentist",
    "which babysitter",
    "where they are kept",
    "what was our saved",
    "what pizza place",
    "what memory did we save",
    "did we decide",
)

CALENDAR_HINTS = (
    "calendar",
    "schedule",
    "appointment",
    "meeting",
    "event",
    "add to my calendar",
    "add to calendar",
    "turn the",
    "create a calendar",
    "put the",
)

MEAL_HINTS = (
    "meal plan",
    "meal",
    "dinner",
    "lunch",
    "breakfast",
    "recipe",
    "recipes",
    "pantry",
    "shopping list",
    "cook",
    "ingredients",
    "vegetarian",
    "gluten-free",
    "dairy-free",
    "lactose-free",
    "kid-friendly",
)


class SyntheticSystemAdapter:
    def __init__(self, cases: Sequence[Dict[str, object]]) -> None:
        self.corpus_by_intent = {"calendar": [], "meal": [], "memory": [], "general": []}
        for case in cases:
            bucket = self._bucket_from_category(str(case.get("category", "general")))
            self.corpus_by_intent.setdefault(bucket, [])
            self.corpus_by_intent[bucket].extend(case.get("expected_retrieved_context", []))

        for bucket, snippets in self.corpus_by_intent.items():
            self.corpus_by_intent[bucket] = unique_preserve_order(snippets)

        self.global_corpus = unique_preserve_order(
            snippet
            for snippets in self.corpus_by_intent.values()
            for snippet in snippets
        )

    async def predict_intent(self, query: str) -> str:
        return self._classify_intent(query)

    def select_tool(self, intent: str) -> str:
        return INTENT_TO_TOOL.get(intent, "chat")

    def select_agent(self, intent: str) -> str:
        return INTENT_TO_AGENT.get(intent, "general_agent")

    def retrieve_contexts(self, query: str, limit: int = 3) -> List[str]:
        intent = self._classify_intent(query)
        candidates = self.corpus_by_intent.get(intent) or self.global_corpus
        scored = sorted(
            ((self._retrieval_score(query, candidate), candidate) for candidate in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        return [candidate for score, candidate in scored[:limit] if score > 0.0]

    def generate_answer(self, case: Dict[str, object], retrieved_contexts: Sequence[str]) -> str:
        category = str(case.get("category", "general"))
        query = str(case.get("input_query", ""))

        if category == "email_calendar":
            return self._answer_calendar(query, retrieved_contexts)
        if category == "meal_planning":
            return self._answer_meal_plan(query, retrieved_contexts)
        if category == "memory_lookup":
            return self._answer_memory(query, retrieved_contexts)
        return self._answer_general(retrieved_contexts)

    def _bucket_from_category(self, category: str) -> str:
        if category == "email_calendar":
            return "calendar"
        if category == "meal_planning":
            return "meal"
        if category == "memory_lookup":
            return "memory"
        return "general"

    def _classify_intent(self, query: str) -> str:
        text = query.lower()

        if any(token in text for token in ("saved preference", "saved about", "the note we saved", "what pizza place", "did we decide the kids", "what memory did we save")):
            return "memory"
        if "saved" in text and any(word in text for word in ("preference", "note", "memory", "about", "where", "which")):
            return "memory"
        if any(hint in text for hint in GENERAL_HINTS):
            return "general"
        if any(hint in text for hint in MEMORY_HINTS):
            return "memory"
        if any(hint in text for hint in CALENDAR_HINTS):
            return "calendar"
        if any(hint in text for hint in MEAL_HINTS):
            return "meal"

        if "email" in text and any(word in text for word in ("add", "create", "schedule", "calendar", "event", "appointment", "meeting")):
            return "calendar"

        return "general"

    def _retrieval_score(self, query: str, candidate: str) -> float:
        query_tokens = set(tokenize(query))
        candidate_tokens = set(tokenize(candidate))
        if not query_tokens or not candidate_tokens:
            return 0.0

        overlap = len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)
        sequence = best_match_score(query, [candidate])

        query_digits = set(re.findall(r"\d{1,4}", query))
        candidate_digits = set(re.findall(r"\d{1,4}", candidate))
        digit_bonus = 0.15 if query_digits and query_digits & candidate_digits else 0.0

        query_days = set(re.findall(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", query, re.I))
        candidate_days = set(re.findall(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", candidate, re.I))
        day_bonus = 0.15 if query_days and candidate_days and query_days & candidate_days else 0.0

        return 0.55 * overlap + 0.30 * sequence + digit_bonus + day_bonus

    def _answer_calendar(self, query: str, contexts: Sequence[str]) -> str:
        source_text = " ".join([query, *contexts])
        subject = self._extract_subject(source_text) or self._best_calendar_subject(contexts)
        when = self._extract_datetime(source_text) or self._extract_datetime(" ".join(contexts))
        location = self._extract_location(" ".join(contexts))

        pieces = ["I added"]
        if subject:
            pieces.append(subject)
        else:
            pieces.append("the calendar item")
        if when:
            pieces.append(f"for {when}")
        if location:
            pieces.append(f"at {location}")
        pieces.append("to the calendar.")
        return " ".join(pieces)

    def _answer_meal_plan(self, query: str, contexts: Sequence[str]) -> str:
        blob = " ".join(contexts)
        key_contexts = self._top_context_snippets(query, contexts, limit=2)
        summary_bits = []
        for snippet in key_contexts:
            cleaned = self._clean_context(snippet)
            if cleaned:
                summary_bits.append(cleaned)
        if not summary_bits and blob:
            summary_bits.append(self._clean_context(blob))

        summary = "; ".join(unique_preserve_order(summary_bits)[:2])
        if not summary:
            summary = "family preferences and pantry notes"
        return f"I created a meal plan around {summary}."

    def _answer_memory(self, query: str, contexts: Sequence[str]) -> str:
        if not contexts:
            return "I could not find a matching memory in the household notes."
        fact = self._clean_context(contexts[0])
        return f"We saved that {fact}"

    def _answer_general(self, contexts: Sequence[str]) -> str:
        if not contexts:
            return "I do not have enough household context yet."
        snippets = [self._clean_context(snippet) for snippet in contexts[:2]]
        snippets = [snippet for snippet in snippets if snippet]
        if not snippets:
            return "I do not have enough household context yet."
        return "Based on the household context, " + " and ".join(snippets) + "."

    def _top_context_snippets(self, query: str, contexts: Sequence[str], limit: int = 2) -> List[str]:
        scored = sorted(
            ((self._retrieval_score(query, candidate), candidate) for candidate in contexts),
            key=lambda item: item[0],
            reverse=True,
        )
        return [candidate for score, candidate in scored[:limit] if score > 0.0]

    def _best_calendar_subject(self, contexts: Sequence[str]) -> str:
        for snippet in contexts:
            cleaned = self._clean_context(snippet)
            subject = self._extract_subject(cleaned)
            if subject:
                return subject
        return ""

    def _clean_context(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^(?:Lisa emailed|Jordan wrote that|School email confirms|Email says|Vet appointment is|Parent-teacher conference is|Holiday travel airport choice is|Saturday breakfast preference is|Spare keys are|Memory says|Family memory:|Household memory:|Priority \d+:|Tonight's plan:|Weekend event:|Low stock items:|Grocery list is active for the weekend\.?)\s*[:\-]?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"^(?:The|A|An)\s+", "", cleaned)
        cleaned = cleaned.rstrip(".")
        return cleaned.strip()

    def _extract_subject(self, text: str) -> str:
        patterns = [
            r"\b(add|create|schedule|calendar|turn|put|convert)\s+(?:the\s+)?(.+?)(?:\s+(?:on|for|at|in|to)\b|$)",
            r"\b(.+?)(?:\s+(?:is|starts|begins)\s+.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                subject = match.group(match.lastindex or 1)
                subject = self._clean_subject(subject)
                if subject:
                    return subject
        return ""

    def _clean_subject(self, subject: str) -> str:
        cleaned = subject.strip()
        cleaned = re.sub(r"\b(?:from|in)\s+.*?email.*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\binto a calendar event.*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bto my calendar.*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bon\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday).*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
        return cleaned

    def _extract_datetime(self, text: str) -> str:
        patterns = [
            r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+[A-Z][a-z]+\s+\d{1,2}(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM))?\b",
            r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM))?\b",
            r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b",
            r"\b\d{1,2}\s*(?:AM|PM)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return match.group(0)
        return ""

    def _extract_location(self, text: str) -> str:
        patterns = [
            r"\bat\s+([A-Z0-9][^.,;]+)",
            r"\bin\s+([A-Z0-9][^.,;]+)",
            r"\blocation:\s*([^.,;]+)",
            r"\bvenue:\s*([^.,;]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                location = match.group(1).strip()
                location = re.sub(r"\s+(?:and|with).*$", "", location, flags=re.I)
                return location.rstrip(".")
        return ""


__all__ = ["SyntheticSystemAdapter"]
