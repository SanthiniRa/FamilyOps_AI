from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.supervisor import SupervisorAgent
from app.agents.meal_planning_agent import MealPlanningAgent


supervisor = SupervisorAgent()
meal_agent = MealPlanningAgent()


def build_graph():

    graph = StateGraph(AgentState)

    def route(state):
        return supervisor.route(state)

    graph.add_conditional_edges(
        "supervisor",
        route,
        {
            "meal_planning": "meal_agent",
            "shopping": "shopping_agent",
            "knowledge": "knowledge_agent",
            "email": "email_agent",
            "calendar": "calendar_agent",
        }
    )

    graph.add_node("meal_agent", meal_agent.run)

    graph.set_entry_point("supervisor")
    graph.add_edge("meal_agent", END)

    return graph.compile()