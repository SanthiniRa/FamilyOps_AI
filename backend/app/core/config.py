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
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    cross_encoder_top_n: int = 10
    enable_cross_encoder_rerank: bool = False
    enable_pii_redaction: bool = True
    enable_strict_pii_redaction: bool = False
    redaction_audit_log_path: str = ""

    # Web search
    web_search_max_results: int = 5
    web_search_fetch_limit: int = 3
    web_search_timeout_seconds: int = 12
    web_search_provider: str = "duckduckgo"
    web_search_tavily_api_key: str = ""
    web_search_tavily_search_depth: str = "basic"
    web_search_cache_ttl_seconds: int = 300
    web_search_rate_limit_requests_per_minute: int = 20

    # Weather
    weather_timeout_seconds: int = 12
    weather_forecast_days: int = 5
    weather_default_country_code: str = "GB"
    weather_cache_ttl_seconds: int = 900
    weather_rate_limit_requests_per_minute: int = 30

    # Event search
    event_search_timeout_seconds: int = 12
    event_search_provider: str = "ticketmaster"
    event_search_country_code: str = "GB"
    ticketmaster_api_key: str = ""
    event_search_cache_ttl_seconds: int = 600
    event_search_rate_limit_requests_per_minute: int = 20

    # Recipe search
    recipe_search_timeout_seconds: int = 12
    recipe_search_provider: str = "themealdb"
    recipe_search_cache_ttl_seconds: int = 1800
    recipe_search_rate_limit_requests_per_minute: int = 30

    # Resilience
    external_api_retry_attempts: int = 3
    external_api_retry_base_delay_seconds: float = 0.25
    external_api_retry_max_delay_seconds: float = 2.0
    external_rate_limit_window_seconds: int = 60
    enable_shared_resilience_redis: bool = False

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
    important_email_keywords: str = "urgent,action required,reply required,invoice,payment,deadline,permission slip,form,rsvp,conference,pickup,drop off"
    important_email_senders: str = ""
    important_email_sender_domains: str = ""

    # Twilio (SMS)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

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
