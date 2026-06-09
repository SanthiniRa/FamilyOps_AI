from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    app_name: str = "FamilyOps AI"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # API
    api_prefix: str = "/api/v1"
    allowed_origins: List[str] = ["http://localhost:3000", "http://localhost:5000", "*"]

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""
    database_url: str = ""

    # AI provider settings
    google_api_key: str = ""
    google_model: str = "gemini-2.5-flash"
    google_embedding_model: str = "models/embedding-001"

    # OpenAI (primary)
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # RAG
    rag_document_chunk_words: int = 140
    rag_document_chunk_overlap: int = 20
    rag_memory_chunk_words: int = 90
    rag_memory_chunk_overlap: int = 10
    rag_search_multiplier: int = 6
    rag_context_token_budget: int = 650

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "familyops_memory"

    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    api_bearer_token: str = ""
    access_token_expire_minutes: int = 60 * 24 * 7

    # Observability
    otlp_endpoint: str = ""
    prometheus_port: int = 9090

    # Email
    email_imap_host: str = ""
    email_imap_port: int = 993
    email_address: str = ""
    email_password: str = ""

    # Google Calendar
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/calendar/oauth/callback"

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # OpenTelemetry
    otel_service_name: str = "familyops-ai"
    otel_exporter_otlp_endpoint: str = ""

    # Feature flags
    enable_tracing: bool = True
    enable_metrics: bool = True

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value):
        """
        Accept common deployment labels like "release" or "production" as false.

        Some environments export DEBUG as a string label rather than a real
        boolean, and Pydantic would otherwise fail startup during settings load.
        """
        if isinstance(value, bool):
            return value

        if value is None:
            return False

        if isinstance(value, (int, float)):
            return bool(value)

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "t", "yes", "y", "on", "debug"}:
                return True
            if normalized in {
                "0",
                "false",
                "f",
                "no",
                "n",
                "off",
                "release",
                "prod",
                "production",
                "staging",
            }:
                return False

        return value

    class Config:
        # Resolve env files explicitly so imports behave the same from any cwd.
        env_file = (REPO_ROOT / ".env", BACKEND_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
