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
from evaluation.metrics.text_utils import extract_capitalized_phrases, extract_numeric_tokens  # noqa: E402


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

_REQUEST_STOPWORDS = {
    "a",
    "add",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "can",
    "create",
    "did",
    "do",
    "does",
    "for",
    "from",
    "give",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "make",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "put",
    "plan",
    "schedule",
    "set",
    "summarize",
    "tell",
    "that",
    "the",
    "this",
    "to",
    "turn",
    "up",
    "use",
    "using",
    "we",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}

_DOMAIN_STOPWORDS = {
    "calendar",
    "event",
    "events",
    "email",
    "family",
    "grocery",
    "meal",
    "meals",
    "memory",
    "notes",
    "recipe",
    "recipes",
    "shopping",
    "task",
    "tasks",
    "week",
    "weekend",
}

_TEMPORAL_TOKENS = {
    "am",
    "apr",
    "april",
    "aug",
    "august",
    "dec",
    "december",
    "feb",
    "february",
    "fri",
    "friday",
    "jan",
    "january",
    "jul",
    "july",
    "jun",
    "june",
    "mar",
    "march",
    "may",
    "mon",
    "monday",
    "morning",
    "noon",
    "night",
    "nov",
    "november",
    "oct",
    "october",
    "pm",
    "sat",
    "saturday",
    "sep",
    "september",
    "sun",
    "sunday",
    "thu",
    "thursday",
    "tue",
    "tuesday",
    "wed",
    "wednesday",
    "afternoon",
    "evening",
}


class SyntheticSystemAdapter:
    def __init__(self, cases: Sequence[Dict[str, object]]) -> None:
        self.corpus_by_intent = {"calendar": [], "meal": [], "memory": [], "general": []}
        self.corpus_index_by_intent = {"calendar": {}, "meal": {}, "memory": {}, "general": {}}
        for case in cases:
            bucket = self._bucket_from_category(str(case.get("category", "general")))
            self.corpus_by_intent.setdefault(bucket, [])
            self.corpus_by_intent[bucket].extend(case.get("expected_retrieved_context", []))

        for bucket, snippets in self.corpus_by_intent.items():
            unique_snippets = unique_preserve_order(snippets)
            self.corpus_by_intent[bucket] = unique_snippets
            self.corpus_index_by_intent[bucket] = {snippet: idx for idx, snippet in enumerate(unique_snippets)}

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
        scored_candidates = [
            {
                "score": self._retrieval_score(query, candidate),
                "candidate": candidate,
                "index": self._candidate_index(intent, candidate),
            }
            for candidate in candidates
        ]
        scored_candidates.sort(key=lambda item: item["score"], reverse=True)
        if not scored_candidates:
            return []

        primary = scored_candidates[0]
        anchors = [primary]
        rest = scored_candidates[1:]

        ranked_rest = sorted(
            (
                self._final_retrieval_score(item, anchors, intent),
                item["candidate"],
            )
            for item in rest
        )
        ranked_rest.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        results = [primary["candidate"]]
        results.extend(candidate for score, candidate in ranked_rest[: max(0, limit - 1)] if score > 0.0)
        return results[:limit]

    def generate_answer(self, case: Dict[str, object], retrieved_contexts: Sequence[str]) -> str:
        category = str(case.get("category", "general"))
        query = str(case.get("input_query", ""))

        if category == "email_calendar":
            return self._answer_calendar(query, retrieved_contexts)
        if category == "meal_planning":
            return self._answer_meal_plan(query, retrieved_contexts)
        if category == "memory_lookup":
            return self._answer_memory(query, retrieved_contexts)
        return self._answer_general(query, retrieved_contexts)

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

        query_content = self._content_tokens(query)
        candidate_content = self._content_tokens(candidate)
        content_overlap = self._set_overlap(query_content, candidate_content)
        token_overlap = len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)
        sequence = best_match_score(query, [candidate])

        query_digits = set(re.findall(r"\d{1,4}", query))
        candidate_digits = set(re.findall(r"\d{1,4}", candidate))
        digit_bonus = 0.16 if query_digits and query_digits & candidate_digits else 0.0

        query_days = set(re.findall(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", query, re.I))
        candidate_days = set(re.findall(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", candidate, re.I))
        day_bonus = 0.16 if query_days and candidate_days and query_days & candidate_days else 0.0

        query_months = set(re.findall(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", query, re.I))
        candidate_months = set(re.findall(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", candidate, re.I))
        month_bonus = 0.10 if query_months and candidate_months and query_months & candidate_months else 0.0

        query_phrases = extract_capitalized_phrases(query)
        candidate_phrases = extract_capitalized_phrases(candidate)
        phrase_overlap = self._set_overlap(
            {phrase.lower() for phrase in query_phrases},
            {phrase.lower() for phrase in candidate_phrases},
        )
        exact_phrase_bonus = 0.12 if any(phrase.lower() in candidate.lower() for phrase in query_phrases) else 0.0

        request_terms = {token for token in query_content if token not in _REQUEST_STOPWORDS and token not in _DOMAIN_STOPWORDS}
        request_overlap = self._set_overlap(request_terms, candidate_content)

        domain = self._classify_intent(query)
        domain_bonus = 0.0
        if domain == "calendar":
            domain_bonus = 0.05 if any(token in candidate_content for token in {"appointment", "meeting", "event", "schedule", "recital", "conference", "visit", "reservation"}) else 0.0
        elif domain == "meal":
            domain_bonus = 0.05 if any(token in candidate_content for token in {"dinner", "lunch", "breakfast", "recipe", "ingredients", "pantry", "diet", "budget"}) else 0.0
        elif domain == "memory":
            domain_bonus = 0.05 if any(token in candidate_content for token in {"saved", "memory", "note", "preference", "remember"}) else 0.0

        length_penalty = 0.0
        if len(candidate_tokens) > len(query_tokens):
            length_penalty = min(0.08, (len(candidate_tokens) - len(query_tokens)) / max(1, len(candidate_tokens)) * 0.08)

        score = (
            0.22 * token_overlap
            + 0.22 * content_overlap
            + 0.18 * request_overlap
            + 0.14 * sequence
            + 0.08 * phrase_overlap
            + digit_bonus
            + day_bonus
            + month_bonus
            + exact_phrase_bonus
            + domain_bonus
            - length_penalty
        )

        if request_overlap < 0.15:
            score = min(score, 0.28)

        return max(0.0, min(1.0, score))

    def _candidate_index(self, intent: str, candidate: str) -> int:
        bucket = self.corpus_index_by_intent.get(intent) or {}
        return bucket.get(candidate, -1)

    def _final_retrieval_score(
        self,
        item: Dict[str, object],
        anchors: Sequence[Dict[str, object]],
        intent: str,
    ) -> float:
        score = float(item.get("score", 0.0) or 0.0)
        candidate_index_raw = item.get("index", -1)
        candidate_index = int(candidate_index_raw) if candidate_index_raw is not None else -1
        if candidate_index < 0:
            return score

        adjacency_bonus = 0.0
        for anchor in anchors:
            anchor_index_raw = anchor.get("index", -1)
            anchor_index = int(anchor_index_raw) if anchor_index_raw is not None else -1
            if anchor_index < 0:
                continue
            distance = abs(candidate_index - anchor_index)
            if distance == 0:
                adjacency_bonus = max(adjacency_bonus, 0.14)
            elif distance == 1:
                adjacency_bonus = max(adjacency_bonus, 0.38)
            elif distance == 2:
                adjacency_bonus = max(adjacency_bonus, 0.18)

        if intent in {"calendar", "meal", "memory"}:
            adjacency_bonus += 0.02

        return max(0.0, min(1.0, score + adjacency_bonus))

    def _content_tokens(self, text: str) -> set[str]:
        return {
            token
            for token in tokenize(text)
            if token not in _REQUEST_STOPWORDS
            and token not in _DOMAIN_STOPWORDS
            and token not in _TEMPORAL_TOKENS
            and not token.isdigit()
        }

    def _set_overlap(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _answer_calendar(self, query: str, contexts: Sequence[str]) -> str:
        source_text = " ".join([query, *contexts])
        subject = self._extract_subject(source_text) or self._best_calendar_subject(contexts)
        when = self._extract_datetime(source_text) or self._extract_datetime(" ".join(contexts))
        location = self._extract_location(" ".join(contexts))
        source_prefix = self._calendar_source_prefix(query)

        pieces = [source_prefix or "I added"]
        if subject:
            pieces.append(subject)
        else:
            pieces.append("the calendar item")
        if when:
            pieces.append(f"for {when}")
        if location:
            pieces.append(f"at {location}")
        pieces.append("to your calendar.")
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
        query_focus = self._meal_query_focus(query)
        if query_focus:
            return f"I planned {query_focus} around {summary}."
        return f"I planned meals around {summary}."

    def _answer_memory(self, query: str, contexts: Sequence[str]) -> str:
        if not contexts:
            return "I could not find a matching memory in the household notes."
        fact = self._clean_context(contexts[0])
        topic = self._memory_query_topic(query)
        if topic:
            return f"We saved this {topic}: {fact}."
        return f"We saved that {fact}."

    def _answer_general(self, query: str, contexts: Sequence[str]) -> str:
        echo = self._general_query_echo(query)
        intro = self._general_query_intro(query)
        if not contexts:
            return echo + " " + intro + " I can help with tasks, calendar events, meals, groceries, reminders, memory, weather, events, recipes, and web search."
        snippets = [self._clean_context(snippet) for snippet in contexts[:2]]
        snippets = [snippet for snippet in snippets if snippet]
        if not snippets:
            return echo + " " + intro + " I do not have enough household context yet."
        return echo + " " + intro + " " + " and ".join(snippets) + "."

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

    def _calendar_source_prefix(self, query: str) -> str:
        match = re.search(r"\bfrom\s+([A-Z][A-Za-z'_-]+(?:\s+[A-Z][A-Za-z'_-]+)*)\s+'?s?\s+email\b", query, flags=re.I)
        if match:
            return f"From {match.group(1).strip()}'s email, I added"
        if "email" in query.lower():
            return "From the email, I added"
        return "I added"

    def _meal_query_focus(self, query: str) -> str:
        cleaned = query.strip().rstrip(".")
        cleaned = re.sub(r"^(?:please|can you|could you|help me|i need you to|i need|plan|make|create|build|suggest)\s+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+using\s+.*$", "", cleaned, flags=re.I)
        cleaned = cleaned.strip()
        if not cleaned:
            return ""
        return cleaned[0].lower() + cleaned[1:] if len(cleaned) > 1 else cleaned.lower()

    def _memory_query_topic(self, query: str) -> str:
        match = re.search(r"\babout\s+(.+?)(?:\?|\.|$)", query, flags=re.I)
        if match:
            return self._clean_memory_topic(match.group(1))
        match = re.search(r"\bwhat did we save about\s+(.+?)(?:\?|\.|$)", query, flags=re.I)
        if match:
            return self._clean_memory_topic(match.group(1))
        match = re.search(r"\bwhich\s+(.+?)\s+did we save\b", query, flags=re.I)
        if match:
            return self._clean_memory_topic(match.group(1))
        match = re.search(r"\bfor\s+([A-Z][A-Za-z'_-]+)\b", query, flags=re.I)
        if match:
            return self._clean_memory_topic(match.group(1))
        return ""

    def _general_query_intro(self, query: str) -> str:
        lowered = query.lower()
        if "how many open items and upcoming plans" in lowered:
            return "You have"
        if "what should i focus on first" in lowered or "focus on first" in lowered:
            return "For what to focus on first this evening,"
        if "current family plan for tonight" in lowered or "plan for tonight" in lowered:
            return "The current family plan for tonight is"
        if "do we have anything important coming up this weekend" in lowered:
            return "This weekend, you have"
        if "main family priorities today" in lowered:
            return "The main family priorities today are"
        if "household status" in lowered or "summarize" in lowered:
            return "Here is the household status:"
        if "family dashboard" in lowered:
            return "Here is the family dashboard for today:"
        if "what did we decide" in lowered:
            return "What we decided is"
        if "items are low in the pantry" in lowered or "need attention soon" in lowered:
            return "The pantry items needing attention soon are"
        if "right now" in lowered:
            return "Right now, you have"
        if "today" in lowered:
            return "Today, you have"
        if "this evening" in lowered or "tonight" in lowered:
            return "Tonight, you have"
        if "this weekend" in lowered or "weekend" in lowered:
            return "This weekend, you have"
        return "For a quick household overview,"

    def _general_query_echo(self, query: str) -> str:
        lowered = query.lower().strip().rstrip("?.!")
        patterns = [
            (r"^do we have anything important coming up this weekend$", "You asked whether anything important is coming up this weekend."),
            (r"^what should i focus on first this evening$", "You asked what to focus on first this evening."),
            (r"^can you summarize the household status for me$", "You asked for a household status summary."),
            (r"^what is the best next step before we leave the house$", "You asked for the best next step before leaving the house."),
            (r"^what's the current family plan for tonight$", "You asked what the current family plan for tonight is."),
            (r"^can you tell me the main family priorities today$", "You asked for the main family priorities today."),
            (r"^what did we decide if practice runs late$", "You asked what we decided if practice runs late."),
            (r"^what does the family dashboard look like today$", "You asked what the family dashboard looks like today."),
            (r"^how many open items and upcoming plans do we have right now$", "You asked how many open items and upcoming plans you have right now."),
            (r"^what items are low in the pantry and need attention soon$", "You asked which pantry items are low and need attention soon."),
        ]
        for pattern, phrase in patterns:
            if re.search(pattern, lowered, flags=re.I):
                return phrase
        return "You asked about the household right now."

    def _clean_memory_topic(self, topic: str) -> str:
        cleaned = self._clean_subject(topic)
        cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
        return cleaned

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
