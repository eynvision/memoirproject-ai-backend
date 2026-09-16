"""
@file src/core/config.py
@description Centralized application configuration and environment variable validation
using Pydantic BaseSettings.
"""

from typing import List, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded securely from environment variables.
    """
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., validation_alias="SUPABASE_ANON_KEY")
    supabase_secret_key: str = Field(..., validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    database_url: str = Field(..., validation_alias="DATABASE_URL")
    supabase_jwks_url: Optional[str] = Field(default=None, validation_alias="SUPABASE_JWKS_URL")
    supabase_media_bucket: str = Field("media", validation_alias="SUPABASE_BUCKET_NAME")
    
    media_max_bytes: int = Field(52_428_576, validation_alias="MEDIA_MAX_BYTES")
    media_signed_url_ttl: int = Field(300, validation_alias="MEDIA_SIGNED_URL_TTL")

    # AI Memoir Organisation (Google Gemini via LangChain)
    google_api_key: Optional[str] = Field(None, validation_alias="GOOGLE_API_KEY")
    google_model: str = Field("gemini-3.6-flash", validation_alias="GOOGLE_MODEL")
    share_link_base_url: str = Field("http://localhost:3000/share", validation_alias="SHARE_LINK_BASE_URL")

    @model_validator(mode="after")
    def populate_jwks_url(self) -> "Settings":
        if not self.supabase_jwks_url and self.supabase_url:
            self.supabase_jwks_url = f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return self
    
    # FIXED: Added cors_origins so main.py can dynamically read allowed origins from the environment
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        validation_alias="CORS_ORIGINS"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        """
        Parses comma-separated CORS origins string from environment variables into a list,
        or accepts an existing list.
        """
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

# Storage tiers for media asset lifecycle management
STORAGE_TIER_HOT = "hot"
STORAGE_TIER_COLD = "cold"

# Transcription status states for audio/video assets
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
