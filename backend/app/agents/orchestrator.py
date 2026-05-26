from typing import Any, Dict, List, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from app.core.config import settings
from app.core.logging import logger
from app.events.bus import event_bus
import operator
from datetime import datetime


def _build_llm():
    if settings.google_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.google_model,
            google_api_key=settings.google_api_key,
            temperature=0.1,
        )
    elif settings.openai_api_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.1,
        )
    return None


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    agent_name: str
    workflow_id: str
    context: Dict[str, Any]
    tools_called: List[str]
    status: str
    error: Optional[str]


class FamilyOpsOrchestrator:
    def __init__(self):
        self.llm = _build_llm()
        self.agents: Dict[str, Any] = {}
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("router", self._router_node)
        graph.add_node("email_agent", self._email_agent_node)
        graph.add_node("calendar_agent", self._calendar_agent_node)
        graph.add_node("grocery_agent", self._grocery_agent_node)
        graph.add_node("meal_agent", self._meal_agent_node)
        graph.add_node("reminder_agent", self._reminder_agent_node)
        graph.add_node("memory_agent", self._memory_agent_node)
        graph.add_node("task_agent", self._task_agent_node)
        graph.add_node("responder", self._responder_node)

        graph.set_entry_point("router")

        graph.add_conditional_edges(
            "router",
            self._route_to_agent,
            {
                "email": "email_agent",
                "calendar": "calendar_agent",
                "grocery": "grocery_agent",
                "meal": "meal_agent",
                "reminder": "reminder_agent",
                "memory": "memory_agent",
                "task": "task_agent",
                "respond": "responder",
            }
        )

        for node in ["email_agent", "calendar_agent", "grocery_agent",
                     "meal_agent", "reminder_agent", "memory_agent", "task_agent"]:
            graph.add_edge(node, "responder")

        graph.add_edge("responder", END)

        return graph.compile()

    async def _router_node(self, state: AgentState) -> AgentState:
        last_message = state["messages"][-1].content if state["messages"] else ""
        logger.info("orchestrator.routing", message_preview=last_message[:100])

        intent = await self._detect_intent(last_message)
        state["context"]["intent"] = intent
        state["status"] = "routing"

        await event_bus.publish("agent.started", {
            "agent": "orchestrator",
            "workflow_id": state["workflow_id"],
            "intent": intent,
        })

        return state

    def _route_to_agent(self, state: AgentState) -> str:
        intent = state["context"].get("intent", "respond")
        routing_map = {
            "email": "email",
            "calendar": "calendar",
            "schedule": "calendar",
            "grocery": "grocery",
            "shopping": "grocery",
            "meal": "meal",
            "recipe": "meal",
            "reminder": "reminder",
            "alert": "reminder",
            "memory": "memory",
            "remember": "memory",
            "task": "task",
            "todo": "task",
        }
        for keyword, agent in routing_map.items():
            if keyword in intent.lower():
                return agent
        return "respond"

    async def _detect_intent(self, message: str) -> str:
        keywords = ["email", "calendar", "schedule", "grocery", "shopping",
                    "meal", "recipe", "reminder", "memory", "task", "todo"]
        message_lower = message.lower()
        for kw in keywords:
            if kw in message_lower:
                return kw
        return "general"

    async def _email_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("email_agent")
        state["context"]["email_result"] = {"status": "processed", "agent": "email"}
        return state

    async def _calendar_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("calendar_agent")
        state["context"]["calendar_result"] = {"status": "processed", "agent": "calendar"}
        return state

    async def _grocery_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("grocery_agent")
        state["context"]["grocery_result"] = {"status": "processed", "agent": "grocery"}
        return state

    async def _meal_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("meal_agent")
        state["context"]["meal_result"] = {"status": "processed", "agent": "meal"}
        return state

    async def _reminder_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("reminder_agent")
        state["context"]["reminder_result"] = {"status": "processed", "agent": "reminder"}
        return state

    async def _memory_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("memory_agent")
        state["context"]["memory_result"] = {"status": "processed", "agent": "memory"}
        return state

    async def _task_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("task_agent")
        state["context"]["task_result"] = {"status": "processed", "agent": "task"}
        return state

    async def _responder_node(self, state: AgentState) -> AgentState:
        state["status"] = "completed"
        await event_bus.publish("agent.completed", {
            "workflow_id": state["workflow_id"],
            "tools_called": state["tools_called"],
        })
        return state

    async def run(self, message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        import uuid
        workflow_id = str(uuid.uuid4())

        initial_state = AgentState(
            messages=[HumanMessage(content=message)],
            agent_name="orchestrator",
            workflow_id=workflow_id,
            context=context or {},
            tools_called=[],
            status="started",
            error=None,
        )

        try:
            result = await self.graph.ainvoke(initial_state)
            return {
                "workflow_id": workflow_id,
                "status": result["status"],
                "context": result["context"],
                "tools_called": result["tools_called"],
            }
        except Exception as e:
            logger.error("orchestrator.run_error", error=str(e))
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e),
                "context": {},
                "tools_called": [],
            }


orchestrator = FamilyOpsOrchestrator()
