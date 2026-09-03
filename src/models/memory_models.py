# Pydantic models for the memory feature — direct twin of the frontend schemas.
# Strictly mapped to the official SQL schema.

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class MemoryStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"


class MediaKind(str, Enum):
    audio = "audio"
    photo = "photo"


class MediaLinkType(str, Enum):
    primary = "primary"
    reference = "reference"


class TranscodeStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    skipped = "skipped"


# ---------- Media ----------

class PresignRequest(BaseModel):
    kind: MediaKind
    mime_type: str = Field(..., max_length=100)
    byte_size: int = Field(..., gt=0, le=50 * 1024 * 1024)  # 50 MB hard limit
    original_filename: Optional[str] = Field(None, max_length=255)
    checksum_sha256: Optional[str] = Field(None, min_length=64, max_length=64)


class PresignResponse(BaseModel):
    upload_url: str
    storage_key: str
    expires_at: datetime


class MediaConfirmRequest(BaseModel):
    storage_key: str
    kind: MediaKind
    mime_type: str
    byte_size: int = Field(..., gt=0)
    duration_ms: Optional[int] = Field(None, ge=0)  # Required for audio by DB constraint
    width_px: Optional[int] = Field(None, ge=0)
    height_px: Optional[int] = Field(None, ge=0)
    caption: Optional[str] = Field(None, max_length=1000)
    original_filename: Optional[str] = Field(None, max_length=255)
    checksum_sha256: Optional[str] = Field(None, min_length=64, max_length=64)


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    memoir_id: UUID
    kind: MediaKind
    storage_key: str
    mime_type: str
    byte_size: int
    duration_ms: Optional[int] = None
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    caption: Optional[str] = None
    playback_url: str
    position: int
    link_type: MediaLinkType = MediaLinkType.primary
    transcription_status: TranscodeStatus
    created_at: datetime


# ---------- Memory ----------

class MemoryCreateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    body_text: Optional[str] = Field(None, max_length=20_000)
    prompt_id: Optional[UUID] = None


class MemoryPatchRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    body_text: Optional[str] = Field(None, max_length=20_000)


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    memoir_id: UUID
    author_participant_id: UUID
    prompt_id: Optional[UUID] = None
    title: Optional[str] = None
    body_text: Optional[str] = None
    status: MemoryStatus
    media: List[MediaAssetOut] = []
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None


class MemoryListResponse(BaseModel):
    memories: List[MemoryOut]
    total: int