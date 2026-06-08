from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict):
    messages: list
    user_query: str
    selected_agent: str
    agent_outputs: dict
    memory_context: dict
    metadata: dict

    family_preferences: dict
    allergies: List[str]
    dietary_restrictions: List[str]
    pantry_inventory: dict
    budget: float

    meal_plan: dict
    shopping_list: list
    nutrition_summary: dict