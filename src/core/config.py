"""
@file src/core/config.py
@description Centralized application configuration and environment variable validation
using Pydantic BaseSettings.
"""

from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded securely from environment variables.
    """
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., validation_alias="SUPABASE_ANON_KEY")
    supabase_secret_key: str = Field(..., validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    database_url: str = Field(..., validation_alias="DATABASE_URL")
    supabase_jwks_url: str = Field(..., validation_alias="SUPABASE_JWKS_URL")
    supabase_media_bucket: str = Field("memoir-media", validation_alias="SUPABASE_BUCKET_NAME")
    
    # Flexible LLM Configuration for Groq / ExperientialLabs / OpenAI
    llm_api_key: Optional[str] = Field(None, validation_alias="LLM_API_KEY")
    llm_base_url: str = Field("https://api.groq.com/openai/v1", validation_alias="LLM_BASE_URL")
    llm_model: str = Field("llama-3.1-8b-instant", validation_alias="LLM_MODEL")
    
    # AI Memoir Organisation (Google Gemini via LangChain)
    google_api_key: Optional[str] = Field(None, validation_alias="GOOGLE_API_KEY")
    google_model: str = Field("gemini-3.6-flash", validation_alias="GOOGLE_MODEL")
    share_link_base_url: str = Field("http://localhost:3000/share", validation_alias="SHARE_LINK_BASE_URL")

    media_max_bytes: int = Field(52_428_576, validation_alias="MEDIA_MAX_BYTES")
    media_signed_url_ttl: int = Field(300, validation_alias="MEDIA_SIGNED_URL_TTL")
    
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        validation_alias="CORS_ORIGINS"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()

STORAGE_TIER_HOT = "hot"
STORAGE_TIER_COLD = "cold"

TRANSCRIPTION_STATUS_PENDING = "pending"
TRANSCRIPTION_STATUS_COMPLETED = "completed"
TRANSCRIPTION_STATUS_FAILED = "failed"

SUPABASE_JWKS_URL = settings.supabase_jwks_url

# ------------------------------------------------------------------
# AI Memoir Organisation constants
# ------------------------------------------------------------------
# The AI should suggest a meaningful number of chapters. These bounds
# are validated in chapter_service before anything is persisted.
CHAPTER_MIN_LIMIT = 3
CHAPTER_MAX_LIMIT = 7
# Hard celling on memories sent to the model in one request; larger
# memoirs are chunked so we stay inside the model's context window.
CHAPTER_BATCH_SIZE = 60

# ------------------------------------------------------------------
# AI narrative layer (personality profile + emotional rewrite) and chat
# ------------------------------------------------------------------
# Each memory is truncated to this many characters before it is sent to the
# personality/rewrite prompts, and the personality prompt as a whole is capped
# so a very large memoir cannot exceed the model's context window.
NARRATIVE_MAX_MEMORY_CHARS = 4000
PROFILE_MAX_TOTAL_CHARS = 300_000
# memory.rewritten_text mirrors the 10,000-char limit on memory.body_text.
REWRITE_MAX_CHARS = 10_000
# A narrative job stuck in 'running' longer than this is treated as dead.
NARRATIVE_STALE_MINUTES = 15
PROFILE_TEMPERATURE = 0.3
REWRITE_TEMPERATURE = 0.7
CHAT_TEMPERATURE = 0.4
# Most recent chat messages replayed to the model on each turn.
CHAT_HISTORY_LIMIT = 30
# Hard stop on model<->tool round trips within one chat turn.
CHAT_MAX_STEPS = 12

# Photos returned with chapters stay valid long enough for a reading session.
CHAPTER_PHOTO_URL_TTL = 3600