from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, Integer,
    Float, JSON, ForeignKey, Enum
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from datetime import datetime, timezone
import uuid
import enum

Base = declarative_base()


# ============================================================
# Helpers
# ============================================================
def gen_uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


# ============================================================
# Event Types
# ============================================================
class EventType(str, enum.Enum):
    EMAIL_RECEIVED = "email.received"
    EMAIL_PROCESSED = "email.processed"
    CALENDAR_EVENT_CREATED = "calendar.event.created"
    CALENDAR_EVENT_UPDATED = "calendar.event.updated"
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    REMINDER_CREATED = "reminder.created"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"


# ============================================================
# Family Members
# ============================================================
class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True)
    role = Column(String(50), default="member")
    avatar_url = Column(String(500))
    preferences = Column(JSON, default=dict)
    dietary_restrictions = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tasks = relationship("Task", back_populates="assignee")
    reminders = relationship("Reminder", back_populates="member")
    user_account = relationship("User", back_populates="family_member", uselist=False)


# ============================================================
# Users
# ============================================================
class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(Enum(UserRole), nullable=False, default=UserRole.MEMBER)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    family_member_id = Column(String, ForeignKey("family_members.id"), unique=True)

    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    family_member = relationship("FamilyMember", back_populates="user_account")


# ============================================================
# Tasks
# ============================================================
class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String(255), nullable=False)
    description = Column(Text)

    status = Column(String(50), default="pending")
    priority = Column(String(20), default="medium")
    due_date = Column(DateTime(timezone=True))

    assignee_id = Column(String, ForeignKey("family_members.id"))
    created_by = Column(String)

    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)
    agent_generated = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assignee = relationship("FamilyMember", back_populates="tasks")


# ============================================================
# Calendar Events
# ============================================================
class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String(255), nullable=False)
    description = Column(Text)

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    location = Column(String(500))
    all_day = Column(Boolean, default=False)

    attendees = Column(JSON, default=list)
    google_event_id = Column(String(255))
    recurrence = Column(JSON)
    reminders = Column(JSON, default=list)

    color = Column(String(20))
    extra_data = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ============================================================
# Grocery
# ============================================================
class GroceryList(Base):
    __tablename__ = "grocery_lists"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default="active")
    store = Column(String(255))
    scheduled_date = Column(DateTime(timezone=True))
    total_estimate = Column(Float)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


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

    created_at = Column(DateTime(timezone=True), default=utcnow)


# ============================================================
# Pantry Inventory
# ============================================================
class PantryItem(Base):
    __tablename__ = "pantry_items"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)

    category = Column(String(100))
    quantity = Column(Float, default=1)
    unit = Column(String(50))
    
    # Tracking
    min_quantity = Column(Float, default=0)  # Reorder threshold
    last_updated = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    expiry_date = Column(DateTime(timezone=True))
    
    # Metadata
    location = Column(String(100))  # Kitchen shelf, fridge, etc.
    notes = Column(Text)
    price_per_unit = Column(Float)
    
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ============================================================
# Meal Plans
# ============================================================
class MealPlan(Base):
    __tablename__ = "meal_plans"

    id = Column(String, primary_key=True, default=gen_uuid)
    week_start = Column(DateTime(timezone=True), nullable=False)
    week_end = Column(DateTime(timezone=True), nullable=False)

    meals = Column(JSON, default=dict)
    nutritional_summary = Column(JSON, default=dict)
    generated_by_ai = Column(Boolean, default=False)
    preferences_used = Column(JSON, default=dict)
    result = Column(JSON)  
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ============================================================
# Recipes
# ============================================================
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

    created_at = Column(DateTime(timezone=True), default=utcnow)


# ============================================================
# Reminders
# ============================================================
class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String(255), nullable=False)
    body = Column(Text)

    remind_at = Column(DateTime(timezone=True), nullable=False)
    recurrence = Column(String(50))

    member_id = Column(String, ForeignKey("family_members.id"))
    channel = Column(String(50), default="app")
    status = Column(String(50), default="pending")

    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    member = relationship("FamilyMember", back_populates="reminders")


# ============================================================
# Memory
class Memory(Base):
    __tablename__ = "memories"

    id = Column(String, primary_key=True, default=gen_uuid)
    content = Column(Text, nullable=False)
    memory_type = Column(String(50), nullable=False, default="household")
    embedding_id = Column(String(255), nullable=True)
    memory_metadata = Column("metadata", JSON, default=dict)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow
    )


# ============================================================
# Email
# ============================================================
class Email(Base):
    __tablename__ = "emails"

    id = Column(String, primary_key=True, default=gen_uuid)

    message_id = Column(String(500), unique=True)
    subject = Column(String(500))
    sender = Column(String(255))

    recipients = Column(JSON, default=list)
    body_text = Column(Text)
    body_html = Column(Text)

    received_at = Column(DateTime(timezone=True))

    processed = Column(Boolean, default=False)
    category = Column(String(100))

    action_items = Column(JSON, default=list)
    summary = Column(Text)

    embedding = Column(JSON)
    extra_data = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), default=utcnow)


# ============================================================
# Uploaded Images
# ============================================================
class UploadedImage(Base):
    __tablename__ = "uploaded_images"

    id = Column(String, primary_key=True, default=gen_uuid)
    family_id = Column(String)

    image_url = Column(String(500))
    storage_path = Column(String(500))
    analysis_result = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=utcnow)


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id = Column(String, primary_key=True, default=gen_uuid)
    filename = Column(String(500), nullable=False)
    content_type = Column(String(255), nullable=True)
    storage_path = Column(String(1000), nullable=False)
    extra_metadata = Column("metadata", JSON, default=dict)
    source = Column(String(100), nullable=True)
    ingested = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=utcnow)


# ============================================================
# Payments
# ============================================================
class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=gen_uuid)
    description = Column(String(255))
    amount = Column(Float)

    due_date = Column(DateTime(timezone=True))
    status = Column(String(50), default="pending")

    from_email = Column(String(255))
    extracted_from_email_id = Column(String, ForeignKey("emails.id"))

    created_at = Column(DateTime(timezone=True), default=utcnow)


# ============================================================
# Agent Runs
# ============================================================
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

    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True))


# ============================================================
# SMS Messages
# ============================================================
class SmsMessage(Base):
    __tablename__ = "sms_messages"

    id = Column(String, primary_key=True, default=gen_uuid)

    from_number = Column(String(30), nullable=False)
    to_number = Column(String(30))
    body = Column(Text, nullable=False)

    twilio_sid = Column(String(60), unique=True)

    is_appointment = Column(Boolean, default=False)
    processed = Column(Boolean, default=False)

    extracted_data = Column(JSON, default=dict)
    tasks_created = Column(JSON, default=list)
    events_created = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    processed_at = Column(DateTime(timezone=True))


# ============================================================
# Events
# ============================================================
class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=gen_uuid)

    event_type = Column(String(100), nullable=False)
    source = Column(String(100))
    payload = Column(JSON, default=dict)

    processed = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=utcnow)
