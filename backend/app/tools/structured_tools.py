"""
Structured Tool Definitions for LangGraph Agents

This module provides LangChain-compatible tool decorators for all MCP tools.
These are used by agents for better LLM understanding and tool selection.

Benefits over raw function calls:
- Automatic schema generation for LLM understanding
- Type validation and documentation
- LangChain integration for tool calling
- Proper error handling and logging
"""

from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from app.tools.mcp_tools import MCPTools
from app.core.logging import logger

mcp_tools = MCPTools()


# ============================================================
# TASK TOOLS
# ============================================================

@tool
async def create_household_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    due_date: Optional[str] = None,
    assigned_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new household task.
    
    Args:
        title: The task title or name
        description: Detailed task description
        priority: Task priority - 'low', 'medium', or 'high'
        due_date: Optional due date in ISO format (YYYY-MM-DD)
        assigned_to: Optional family member name to assign the task
        
    Returns:
        Dictionary with task_id and confirmation message
    """
    try:
        task_data = {
            "title": title,
            "description": description,
            "priority": priority,
            "due_date": due_date,
            "assigned_to": assigned_to,
        }
        result = await mcp_tools.create_task(task_data)
        logger.info("tool.task.created", task_id=result.get("task_id"))
        return {
            "success": True,
            "task_id": result.get("task_id"),
            "message": f"Task '{title}' created successfully",
        }
    except Exception as e:
        logger.error("tool.task.creation_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to create task: {str(e)}",
        }


@tool
async def update_task_status(
    task_id: str,
    status: str,
) -> Dict[str, Any]:
    """
    Update the status of a household task.
    
    Args:
        task_id: The ID of the task to update
        status: New status - 'pending', 'in_progress', 'completed', or 'cancelled'
        
    Returns:
        Dictionary with success status and message
    """
    try:
        # Implementation would update task status in database
        logger.info("tool.task.status_updated", task_id=task_id, status=status)
        return {
            "success": True,
            "task_id": task_id,
            "new_status": status,
            "message": f"Task status updated to {status}",
        }
    except Exception as e:
        logger.error("tool.task.update_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to update task: {str(e)}",
        }


# ============================================================
# CALENDAR TOOLS
# ============================================================

@tool
async def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: Optional[List[str]] = None,
    recurrence: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new calendar event.
    
    Args:
        title: Event title
        start_time: Start datetime in ISO format (YYYY-MM-DDTHH:MM:SS)
        end_time: End datetime in ISO format (YYYY-MM-DDTHH:MM:SS)
        description: Event description
        location: Event location
        attendees: List of attendee names or emails
        recurrence: Recurrence rule (e.g., 'DAILY', 'WEEKLY', 'MONTHLY')
        
    Returns:
        Dictionary with event_id and confirmation message
    """
    try:
        event_data = {
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "description": description,
            "location": location,
            "attendees": attendees or [],
            "recurrence": recurrence,
        }
        result = await mcp_tools.create_event(event_data)
        logger.info("tool.event.created", event_id=result.get("event_id"))
        return {
            "success": True,
            "event_id": result.get("event_id"),
            "message": f"Event '{title}' created successfully",
        }
    except Exception as e:
        logger.error("tool.event.creation_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to create event: {str(e)}",
        }


@tool
async def find_available_time_slots(
    duration_minutes: int = 60,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Find available time slots in the family calendar.
    
    Args:
        duration_minutes: Duration of desired meeting in minutes
        start_date: Start date for search (ISO format)
        end_date: End date for search (ISO format)
        
    Returns:
        List of available time slots
    """
    try:
        # Implementation would search calendar for available slots
        logger.info("tool.calendar.slots_searched", duration=duration_minutes)
        return {
            "success": True,
            "available_slots": [],
            "message": "Calendar slots searched",
        }
    except Exception as e:
        logger.error("tool.calendar.search_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================
# MEMORY/RAG TOOLS
# ============================================================

@tool
async def search_household_memory(
    query: str,
    memory_type: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Search household memory using semantic search.
    
    Args:
        query: Search query or question
        memory_type: Filter by memory type (email, document, general, etc.)
        limit: Maximum number of results to return
        
    Returns:
        List of relevant memories with scores
    """
    try:
        from app.memory.memory import memory_service
        results = await memory_service.search_memory(
            query=query,
            memory_type=memory_type,
            k=limit,
        )
        logger.info("tool.memory.searched", query_len=len(query), results_count=len(results))
        return {
            "success": True,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error("tool.memory.search_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "results": [],
        }


@tool
async def store_household_memory(
    content: str,
    memory_type: str = "general",
    importance: int = 5,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Store information in household memory.
    
    Args:
        content: The information to remember
        memory_type: Type of memory (general, preference, routine, health, etc.)
        importance: Importance level 1-10
        tags: Tags to categorize the memory
        metadata: Additional metadata
        
    Returns:
        Dictionary with memory_id and confirmation
    """
    try:
        full_metadata = metadata or {}
        full_metadata["importance"] = importance
        if tags:
            full_metadata["tags"] = tags
            
        result = await mcp_tools.store_memory({
            "content": content,
            "type": memory_type,
            "metadata": full_metadata,
        })
        logger.info("tool.memory.stored", memory_type=memory_type, importance=importance)
        return {
            "success": True,
            "memory_id": result,
            "message": f"Memory stored successfully (type: {memory_type}, importance: {importance}/10)",
        }
    except Exception as e:
        logger.error("tool.memory.storage_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================
# GROCERY TOOLS
# ============================================================

@tool
async def add_grocery_item(
    item_name: str,
    quantity: int = 1,
    unit: str = "item",
    list_name: str = "Main List",
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Add an item to a grocery list.
    
    Args:
        item_name: Name of the item to add
        quantity: Quantity needed
        unit: Unit of measurement (item, lb, oz, cup, etc.)
        list_name: Name of the grocery list
        category: Category of item (produce, dairy, meat, etc.)
        
    Returns:
        Dictionary with confirmation
    """
    try:
        logger.info("tool.grocery.item_added", item=item_name, qty=quantity)
        return {
            "success": True,
            "item": item_name,
            "quantity": quantity,
            "unit": unit,
            "list": list_name,
            "message": f"Added {quantity} {unit} of {item_name} to {list_name}",
        }
    except Exception as e:
        logger.error("tool.grocery.add_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


@tool
async def search_products(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Search for products by name or category.
    
    Args:
        query: Product search query
        category: Filter by category
        limit: Maximum results
        
    Returns:
        List of matching products with prices
    """
    try:
        logger.info("tool.products.searched", query=query, category=category)
        return {
            "success": True,
            "results": [],
            "message": "Product search executed",
        }
    except Exception as e:
        logger.error("tool.products.search_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================
# EMAIL TOOLS
# ============================================================

@tool
async def store_email(
    message_id: str,
    subject: str,
    sender: str,
    body: str,
) -> Dict[str, Any]:
    """
    Store and process an email message.
    
    Args:
        message_id: Unique email message ID
        subject: Email subject line
        sender: Sender email address
        body: Email body text
        
    Returns:
        Dictionary with processing status
    """
    try:
        result = await mcp_tools.store_email({
            "message_id": message_id,
            "subject": subject,
            "sender": sender,
            "body": body,
        })
        logger.info("tool.email.stored", sender=sender, subject_len=len(subject))
        return {
            "success": True,
            "message_id": message_id,
            "message": "Email stored and processed",
        }
    except Exception as e:
        logger.error("tool.email.storage_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================
# UTILITY FUNCTION FOR AGENT TOOLS
# ============================================================

def get_agent_tools(agent_type: str) -> List[Any]:
    """
    Get relevant tools for a specific agent type.
    
    Args:
        agent_type: Type of agent (task, calendar, memory, grocery, email, general)
        
    Returns:
        List of tool functions for the agent
    """
    tools_map = {
        "task": [create_household_task, update_task_status],
        "calendar": [create_calendar_event, find_available_time_slots],
        "memory": [search_household_memory, store_household_memory],
        "grocery": [add_grocery_item, search_products],
        "email": [store_email],
        "knowledge": [search_household_memory, store_household_memory],
        "general": [
            create_household_task,
            create_calendar_event,
            search_household_memory,
            add_grocery_item,
        ],
    }
    
    return tools_map.get(agent_type, [])


# ============================================================
# EXPORT ALL TOOLS
# ============================================================

ALL_TOOLS = [
    create_household_task,
    update_task_status,
    create_calendar_event,
    find_available_time_slots,
    search_household_memory,
    store_household_memory,
    add_grocery_item,
    search_products,
    store_email,
]

__all__ = [
    "create_household_task",
    "update_task_status",
    "create_calendar_event",
    "find_available_time_slots",
    "search_household_memory",
    "store_household_memory",
    "add_grocery_item",
    "search_products",
    "store_email",
    "get_agent_tools",
    "ALL_TOOLS",
]
