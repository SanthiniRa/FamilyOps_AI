"""
LangGraph Visualization Utilities

Provides functions to export the orchestrator graph as:
- PNG image (via Mermaid)
- Mermaid diagram (text)
- ASCII representation
- JSON graph structure
"""

from typing import Optional, Dict, Any
from pathlib import Path
from app.core.logging import logger

try:
    from PIL import Image
    import io
except ImportError:
    Image = None


class GraphVisualizer:
    """Handles graph visualization and export."""
    
    @staticmethod
    def get_mermaid_diagram() -> str:
        """
        Generate a Mermaid diagram of the FamilyOps orchestrator.
        
        Returns:
            Mermaid diagram as a string
        """
        return """graph TD
    Start([START])
    
    Start --> Router[Router Node<br/>Intent Classification]
    
    Router -->|task| TaskAgent[Task Agent<br/>Create/Update Tasks]
    Router -->|calendar| CalendarAgent[Calendar Agent<br/>Schedule Events]
    Router -->|grocery| GroceryAgent[Grocery Agent<br/>Manage Lists]
    Router -->|meal| MealAgent[Meal Agent<br/>Plan Meals]
    Router -->|reminder| ReminderAgent[Reminder Agent<br/>Set Reminders]
    Router -->|memory| MemoryAgent[Memory Agent<br/>Store/Retrieve Knowledge]
    Router -->|email| EmailAgent[Email Agent<br/>Process Emails]
    Router -->|shopping| ShoppingAgent[Shopping Agent<br/>Product Search]
    Router -->|payment| PaymentAgent[Payment Agent<br/>Handle Payments]
    Router -->|general| GeneralAgent[General Agent<br/>Conversational]
    
    TaskAgent --> LLM1{LLM<br/>Processing}
    CalendarAgent --> LLM2{LLM<br/>Processing}
    GroceryAgent --> LLM3{LLM<br/>Processing}
    MealAgent --> LLM4{LLM<br/>Processing}
    ReminderAgent --> LLM5{LLM<br/>Processing}
    MemoryAgent --> RAG[RAG Search<br/>Vector DB]
    RAG --> LLM6{LLM<br/>Processing}
    EmailAgent --> LLM7{LLM<br/>Processing}
    ShoppingAgent --> LLM8{LLM<br/>Processing}
    PaymentAgent --> LLM9{LLM<br/>Processing}
    GeneralAgent --> LLM10{LLM<br/>Processing}
    
    LLM1 --> Tools{Tool<br/>Execution}
    LLM2 --> Tools
    LLM3 --> Tools
    LLM4 --> Tools
    LLM5 --> Tools
    LLM6 --> Tools
    LLM7 --> Tools
    LLM8 --> Tools
    LLM9 --> Tools
    LLM10 --> Tools
    
    Tools --> DB[(Database<br/>SQLAlchemy)]
    Tools --> VectorDB[(Vector DB<br/>Qdrant)]
    
    LLM1 --> End([END])
    LLM2 --> End
    LLM3 --> End
    LLM4 --> End
    LLM5 --> End
    LLM6 --> End
    LLM7 --> End
    LLM8 --> End
    LLM9 --> End
    LLM10 --> End
    
    style Start fill:#90EE90
    style End fill:#FFB6C6
    style Router fill:#87CEEB
    style TaskAgent fill:#DDA0DD
    style CalendarAgent fill:#DDA0DD
    style GroceryAgent fill:#DDA0DD
    style MealAgent fill:#DDA0DD
    style ReminderAgent fill:#DDA0DD
    style MemoryAgent fill:#DDA0DD
    style EmailAgent fill:#DDA0DD
    style ShoppingAgent fill:#DDA0DD
    style PaymentAgent fill:#DDA0DD
    style GeneralAgent fill:#DDA0DD
    style LLM1 fill:#FFE4B5
    style LLM2 fill:#FFE4B5
    style LLM3 fill:#FFE4B5
    style LLM4 fill:#FFE4B5
    style LLM5 fill:#FFE4B5
    style LLM6 fill:#FFE4B5
    style LLM7 fill:#FFE4B5
    style LLM8 fill:#FFE4B5
    style LLM9 fill:#FFE4B5
    style LLM10 fill:#FFE4B5
    style Tools fill:#F0E68C
    style DB fill:#B0C4DE
    style VectorDB fill:#B0C4DE
"""
    
    @staticmethod
    def get_ascii_diagram() -> str:
        """
        Generate an ASCII art representation of the graph.
        
        Returns:
            ASCII diagram as a string
        """
        return """
╔════════════════════════════════════════════════════════════════════════════╗
║         FamilyOps AI - LangGraph Multi-Agent Orchestration                │
╠════════════════════════════════════════════════════════════════════════════╣
║                                                                            │
║                              START                                        │
║                                ▼                                          │
║                          ┌──────────────┐                                │
║                          │ Router Node  │                                │
║                          │   (Intent)   │                                │
║                          └──────┬───────┘                                │
║                 ┌────────────────┼─────────────────┐                     │
║         ┌───────┴──────┬────────┴────────┬────────┴──────────┬────────┐ │
║         ▼              ▼                 ▼                   ▼        ▼  │
║    ┌─────────┐  ┌─────────┐  ┌──────────────┐  ┌──────────────┐ ┌─────┐ │
║    │ Task    │  │Calendar │  │   Grocery    │  │ Meal Planner │ │...  │ │
║    │ Agent   │  │ Agent   │  │   Agent      │  │   Agent      │ │     │ │
║    └────┬────┘  └────┬────┘  └──────┬───────┘  └──────┬───────┘ └─────┘ │
║         │            │              │                 │                  │
║         └────────────┴──────────────┴─────────────────┘                  │
║                      ▼                                                   │
║              ┌─────────────────────┐                                     │
║              │   LLM Processing    │                                     │
║              │  (Claude/Gemini)    │                                     │
║              └──────────┬──────────┘                                     │
║                         ▼                                                │
║              ┌─────────────────────┐                                     │
║              │  Tool Execution     │                                     │
║              │  (MCP Tools)        │                                     │
║              └────┬────────────┬───┘                                     │
║                   ▼            ▼                                         │
║            ┌──────────┐   ┌──────────┐                                   │
║            │Database  │   │ Vector   │                                   │
║            │ (Tasks,  │   │ DB (RAG) │                                   │
║            │ Events)  │   │(Qdrant)  │                                   │
║            └──────────┘   └──────────┘                                   │
║                         ▼                                                │
║                       END                                               │
║                                                                            │
╚════════════════════════════════════════════════════════════════════════════╝

AGENTS:
  • Router: Intent classification (LLM + keyword fallback)
  • Task Agent: Create and manage household tasks
  • Calendar Agent: Schedule events and check availability
  • Grocery Agent: Manage shopping lists
  • Meal Agent: Plan meals with dietary restrictions
  • Reminder Agent: Set recurring reminders
  • Memory Agent: RAG-based knowledge retrieval
  • Email Agent: Process and extract from emails
  • Shopping Agent: Search products and compare prices
  • Payment Agent: Handle bill payments
  • General Agent: Conversational fallback

STATE PERSISTENCE:
  • Messages: Conversation history
  • Intent: Detected intent category
  • Context: Household data (tasks, events, etc.)
  • Tools Called: Execution log
  • Workflow ID: Unique execution trace
"""
    
    @staticmethod
    def get_graph_json() -> Dict[str, Any]:
        """
        Get the graph structure as JSON.
        
        Returns:
            Dictionary representing graph structure
        """
        return {
            "name": "FamilyOpsOrchestrator",
            "version": "1.0",
            "description": "LangGraph-based multi-agent orchestration for household management",
            "entry_point": "router",
            "exit_point": "END",
            "nodes": [
                {
                    "name": "router",
                    "type": "node",
                    "description": "Intent classification with LLM + keyword fallback"
                },
                {
                    "name": "task_agent",
                    "type": "node",
                    "description": "Create and manage household tasks"
                },
                {
                    "name": "calendar_agent",
                    "type": "node",
                    "description": "Schedule events and check availability"
                },
                {
                    "name": "grocery_agent",
                    "type": "node",
                    "description": "Manage grocery shopping lists"
                },
                {
                    "name": "meal_agent",
                    "type": "node",
                    "description": "Plan meals with dietary restrictions"
                },
                {
                    "name": "reminder_agent",
                    "type": "node",
                    "description": "Set recurring reminders"
                },
                {
                    "name": "memory_agent",
                    "type": "node",
                    "description": "RAG-based knowledge retrieval"
                },
                {
                    "name": "email_agent",
                    "type": "node",
                    "description": "Process and extract from emails"
                },
                {
                    "name": "shopping_agent",
                    "type": "node",
                    "description": "Search products and compare prices"
                },
                {
                    "name": "payment_agent",
                    "type": "node",
                    "description": "Handle bill payments"
                },
                {
                    "name": "general_agent",
                    "type": "node",
                    "description": "Conversational fallback agent"
                },
            ],
            "edges": [
                {"from": "router", "to": "task_agent", "condition": "intent == 'task'"},
                {"from": "router", "to": "calendar_agent", "condition": "intent == 'calendar'"},
                {"from": "router", "to": "grocery_agent", "condition": "intent == 'grocery'"},
                {"from": "router", "to": "meal_agent", "condition": "intent == 'meal'"},
                {"from": "router", "to": "reminder_agent", "condition": "intent == 'reminder'"},
                {"from": "router", "to": "memory_agent", "condition": "intent == 'memory'"},
                {"from": "router", "to": "email_agent", "condition": "intent == 'email'"},
                {"from": "router", "to": "shopping_agent", "condition": "intent == 'shopping'"},
                {"from": "router", "to": "payment_agent", "condition": "intent == 'payment'"},
                {"from": "router", "to": "general_agent", "condition": "intent == 'general'"},
            ],
            "state_model": {
                "messages": "List[BaseMessage]",
                "agent_name": "str",
                "workflow_id": "str",
                "context": "Dict[str, Any]",
                "tools_called": "List[str]",
                "reply": "str",
                "status": "str",
                "error": "Optional[str]"
            }
        }
    
    @staticmethod
    async def export_mermaid_png(
        output_path: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Export graph as Mermaid PNG (requires external service or mermaid-cli).
        
        Args:
            output_path: Optional file path to save PNG
            
        Returns:
            PNG bytes if available, None otherwise
        """
        try:
            # Note: This requires mermaid-cli or external rendering service
            # For now, return Mermaid markdown that can be rendered elsewhere
            logger.warning("graph_visualization.png_export_not_available")
            return None
        except Exception as e:
            logger.error("graph_visualization.png_export_failed", error=str(e))
            return None


def export_graph_visualizations(output_dir: str = "backend/docs") -> Dict[str, str]:
    """
    Export all graph visualizations to files.
    
    Args:
        output_dir: Directory to save visualizations
        
    Returns:
        Dictionary with paths to exported files
    """
    try:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        files = {}
        
        # Export Mermaid diagram
        mermaid_path = output_path / "orchestrator_graph.md"
        with open(mermaid_path, "w") as f:
            f.write("# FamilyOps Orchestrator - LangGraph Diagram\n\n```mermaid\n")
            f.write(GraphVisualizer.get_mermaid_diagram())
            f.write("\n```\n")
        files["mermaid"] = str(mermaid_path)
        
        # Export ASCII diagram
        ascii_path = output_path / "orchestrator_graph_ascii.txt"
        with open(ascii_path, "w") as f:
            f.write(GraphVisualizer.get_ascii_diagram())
        files["ascii"] = str(ascii_path)
        
        # Export JSON structure
        import json
        json_path = output_path / "orchestrator_graph.json"
        with open(json_path, "w") as f:
            json.dump(GraphVisualizer.get_graph_json(), f, indent=2)
        files["json"] = str(json_path)
        
        logger.info(
            "graph_visualization.exported",
            files_count=len(files),
            output_dir=output_dir
        )
        
        return files
        
    except Exception as e:
        logger.error("graph_visualization.export_failed", error=str(e))
        return {}


__all__ = [
    "GraphVisualizer",
    "export_graph_visualizations",
]
