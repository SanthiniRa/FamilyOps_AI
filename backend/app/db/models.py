from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, Float, JSON, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid
from datetime import datetime
import enum

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


class EventType(str, enum.Enum):
    EMAIL_RECEIVED = "email.received"
    EMAIL_PROCESSED = "email.processed"
    CALENDAR_EVENT_CREATED = "calendar.event.created"
    CALENDAR_EVENT_UPDATED = "calendar.event.updated"
    GROCERY_ITEM_ADDED = "grocery.item.added"
    GROCERY_LIST_UPDATED = "grocery.list.updated"
    MEAL_PLANNED = "meal.planned"
    MEAL_PLAN_GENERATED = "meal.plan.generated"
    REMINDER_CREATED = "reminder.created"
    REMINDER_TRIGGERED = "reminder.triggered"
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    MEMORY_STORED = "memory.stored"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"


class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True)
    role = Column(String(50), default="member")
    avatar_url = Column(String(500))
    preferences = Column(JSON, default=dict)
    dietary_restrictions = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks = relationship("Task", back_populates="assignee", foreign_keys="Task.assignee_id")
    reminders = relationship("Reminder", back_populates="member")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="pending")
    priority = Column(String(20), default="medium")
    due_date = Column(DateTime)
    assignee_id = Column(String, ForeignKey("family_members.id"))
    created_by = Column(String)
    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)
    agent_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = relationship("FamilyMember", back_populates="tasks", foreign_keys=[assignee_id])


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    location = Column(String(500))
    all_day = Column(Boolean, default=False)
    attendees = Column(JSON, default=list)
    google_event_id = Column(String(255))
    recurrence = Column(JSON)
    reminders = Column(JSON, default=list)
    color = Column(String(20))
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GroceryItem(Base):
    __tablename__ = "grocery_items"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    quantity = Column(Float, default=1)
    unit = Column(String(50))
    checked = Column(Boolean, default=False)
    list_id = Column(String, ForeignKey("grocery_lists.id"))
    added_by = Column(String)
    price_estimate = Column(Float)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    grocery_list = relationship("GroceryList", back_populates="items")


class GroceryList(Base):
    __tablename__ = "grocery_lists"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default="active")
    store = Column(String(255))
    scheduled_date = Column(DateTime)
    total_estimate = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship("GroceryItem", back_populates="grocery_list")


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id = Column(String, primary_key=True, default=gen_uuid)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    meals = Column(JSON, default=dict)
    nutritional_summary = Column(JSON, default=dict)
    generated_by_ai = Column(Boolean, default=False)
    preferences_used = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    ingredients = Column(JSON, nullable=False)
    instructions = Column(JSON, nullable=False)
    prep_time = Column(Integer)
    cook_time = Column(Integer)
    servings = Column(Integer)
    cuisine = Column(String(100))
    tags = Column(JSON, default=list)
    dietary_info = Column(JSON, default=dict)
    nutrition = Column(JSON, default=dict)
    image_url = Column(String(500))
    source_url = Column(String(500))
    embedding = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String(255), nullable=False)
    body = Column(Text)
    remind_at = Column(DateTime, nullable=False)
    recurrence = Column(String(50))
    member_id = Column(String, ForeignKey("family_members.id"))
    channel = Column(String(50), default="app")
    status = Column(String(50), default="pending")
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    member = relationship("FamilyMember", back_populates="reminders")


class HouseholdMemory(Base):
    __tablename__ = "household_memories"

    id = Column(String, primary_key=True, default=gen_uuid)
    content = Column(Text, nullable=False)
    category = Column(String(100))
    tags = Column(JSON, default=list)
    source = Column(String(100))
    importance = Column(Float, default=0.5)
    embedding = Column(JSON)
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


class Email(Base):
    __tablename__ = "emails"

    id = Column(String, primary_key=True, default=gen_uuid)
    message_id = Column(String(500), unique=True)
    subject = Column(String(500))
    sender = Column(String(255))
    recipients = Column(JSON, default=list)
    body_text = Column(Text)
    body_html = Column(Text)
    received_at = Column(DateTime)
    processed = Column(Boolean, default=False)
    category = Column(String(100))
    action_items = Column(JSON, default=list)
    summary = Column(Text)
    embedding = Column(JSON)
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=gen_uuid)
    agent_name = Column(String(100), nullable=False)
    workflow_id = Column(String(255))
    status = Column(String(50), default="running")
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    steps = Column(JSON, default=list)
    tokens_used = Column(Integer, default=0)
    duration_ms = Column(Integer)
    error = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=gen_uuid)
    event_type = Column(String(100), nullable=False)
    source = Column(String(100))
    payload = Column(JSON, default=dict)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
