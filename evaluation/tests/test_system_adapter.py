from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.runners.system_adapter import SyntheticSystemAdapter  # noqa: E402


def test_retrieve_contexts_prefers_exact_calendar_context():
    cases = [
        {
            "category": "email_calendar",
            "expected_retrieved_context": [
                "Lisa emailed: dentist appointment on Friday June 12 at 3:00 PM.",
                "Location: 124 Oak Street, Suite 3.",
            ],
        },
        {
            "category": "email_calendar",
            "expected_retrieved_context": [
                "Jordan wrote that the PTA meeting is Tuesday June 16 at 6:00 PM.",
                "The meeting will be in the school library.",
            ],
        },
    ]

    adapter = SyntheticSystemAdapter(cases)
    results = adapter.retrieve_contexts(
        "From Lisa's email, add the dentist appointment on Friday June 12 at 3:00 PM to my calendar.",
        limit=2,
    )

    assert results[0] == "Lisa emailed: dentist appointment on Friday June 12 at 3:00 PM."
    assert "Location: 124 Oak Street, Suite 3." in results


def test_retrieve_contexts_prefers_specific_meal_context():
    cases = [
        {
            "category": "meal_planning",
            "expected_retrieved_context": [
                "Family preference: lactose-free dinners.",
                "Pantry items available: chicken breast, broccoli, rice.",
            ],
        },
        {
            "category": "meal_planning",
            "expected_retrieved_context": [
                "Family preference: peanut-free meals.",
                "Weeknight dinners should take under 30 minutes.",
            ],
        },
    ]

    adapter = SyntheticSystemAdapter(cases)
    results = adapter.retrieve_contexts(
        "Plan dinners this week for a lactose-free family using the chicken and broccoli we already have.",
        limit=2,
    )

    assert results[0] == "Family preference: lactose-free dinners."
    assert "Pantry items available: chicken breast, broccoli, rice." in results


def test_generate_answer_echoes_user_query_terms():
    cases = [
        {
            "category": "meal_planning",
            "expected_retrieved_context": [
                "Family preference: lactose-free dinners.",
                "Pantry items available: chicken breast, broccoli, rice.",
            ],
        }
    ]

    adapter = SyntheticSystemAdapter(cases)
    answer = adapter.generate_answer(
        {
            "category": "meal_planning",
            "input_query": "Plan dinners this week for a lactose-free family using the chicken and broccoli we already have.",
        },
        [
            "Family preference: lactose-free dinners.",
            "Pantry items available: chicken breast, broccoli, rice.",
        ],
    )

    assert "dinners this week" in answer.lower()
    assert "lactose-free family" in answer.lower()


def test_generate_general_answer_matches_query_frame():
    adapter = SyntheticSystemAdapter(
        [
            {
                "category": "general_chat",
                "expected_retrieved_context": [
                    "Dinner prep is already partially done.",
                    "There are 3 pending reminders.",
                ],
            }
        ]
    )

    answer = adapter.generate_answer(
        {
            "category": "general_chat",
            "input_query": "Do we have anything important coming up this weekend?",
        },
        [
            "Dinner prep is already partially done.",
            "There are 3 pending reminders.",
        ],
    )

    assert "this weekend" in answer.lower()
    assert "pending reminders" in answer.lower()


def test_generate_general_answer_echoes_question_form():
    adapter = SyntheticSystemAdapter(
        [
            {
                "category": "general_chat",
                "expected_retrieved_context": [
                    "Household snapshot: 4 unfinished tasks.",
                    "Upcoming events: 2 calendar entries this week.",
                ],
            }
        ]
    )

    answer = adapter.generate_answer(
        {
            "category": "general_chat",
            "input_query": "What does the family dashboard look like today?",
        },
        [
            "Household snapshot: 4 unfinished tasks.",
            "Upcoming events: 2 calendar entries this week.",
        ],
    )

    assert "family dashboard looks like today" in answer.lower()
    assert "household snapshot" in answer.lower()


def test_generate_memory_answer_names_the_topic():
    adapter = SyntheticSystemAdapter(
        [
            {
                "category": "memory_lookup",
                "expected_retrieved_context": [
                    "Maya is allergic to strawberries and peanuts.",
                ],
            }
        ]
    )

    answer = adapter.generate_answer(
        {
            "category": "memory_lookup",
            "input_query": "Which allergy note did we save for Maya?",
        },
        ["Maya is allergic to strawberries and peanuts."],
    )

    assert "allergy note" in answer.lower()
    assert "maya" in answer.lower()
