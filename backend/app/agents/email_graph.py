from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any
from app.tools.mcp_tools import MCPTools
import google.generativeai as genai
import json


tools = MCPTools()


# ============================================================
# STATE
# ============================================================
class EmailState(TypedDict):
    email: Dict[str, Any]
    actions: List[Dict[str, Any]]
    calendar_events: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]]


# ============================================================
# LLM NODE: EXTRACT STRUCTURE
# ============================================================
async def extract_node(state: EmailState):
    email = state["email"]

    prompt = f"""
Extract structured data from this email.

Return JSON:
{{
  "tasks": [],
  "calendar_events": [],
  "memory": []
}}

Email:
{email["body_text"]}
"""

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)

    data = json.loads(response.text)

    return {
        **state,
        "tasks": data.get("tasks", []),
        "calendar_events": data.get("calendar_events", []),
        "memory": data.get("memory", []),
    }


# ============================================================
# ROUTER NODE
# ============================================================
async def router_node(state: EmailState):
    outputs = []

    for task in state["tasks"]:
        outputs.append(("task", task))

    for event in state["calendar_events"]:
        outputs.append(("calendar", event))

    for mem in state["memory"]:
        outputs.append(("memory", mem))

    return {"routing": outputs}


# ============================================================
# EXECUTOR NODE (MCP CALLS)
# ============================================================
async def executor_node(state: EmailState):
    routing = state.get("routing", [])

    for action_type, payload in routing:

        if action_type == "task":
            await tools.create_task(payload)

        elif action_type == "calendar":
            await tools.create_event(payload)

        elif action_type == "memory":
            await tools.store_memory(payload)

    return state


# ============================================================
# GRAPH BUILD
# ============================================================
def build_graph():
    graph = StateGraph(EmailState)

    graph.add_node("extract", extract_node)
    graph.add_node("router", router_node)
    graph.add_node("execute", executor_node)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "router")
    graph.add_edge("router", "execute")
    graph.add_edge("execute", END)

    return graph.compile()