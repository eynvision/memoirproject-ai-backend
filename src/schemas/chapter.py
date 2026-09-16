"""
@file src/schemas/chapter.py
@description Pydantic request and response schemas for the AI memoir
organisation feature: generation status, chapter suggestions, chapter
edits, memory reordering, and publication envelopes.
"""

import uuid
from datetime import date, datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class MemoryInputItem(BaseModel):
    """
    One memory in the normalised shape sent to the LLM. Only real, provided
    fields are included so the model cannot invent people/places from nothing.
    """
    id: uuid.UUID
    title: Optional[str] = None
    content: Optional[str] = None
    date_label: Optional[str] = None


class GenerationStatusData(BaseModel):
    """Progress of a memoir's AI organisation run for the status endpoint."""
    memoir_id: uuid.UUID
    generation_id: Optional[uuid.UUID] = None
    status: Literal["idle", "running", "completed", "failed"] = "idle"
    memory_count: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ChapterUpdateRequest(BaseModel):
    """Editable chapter fields; at least one must be provided."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    subtitle: Optional[str] = None
    summary: Optional[str] = None

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if self.title is None and self.subtitle is None and self.summary is None:
            raise ValueError("At least one of title, subtitle, or summary must be provided.")
        return self


class ChapterMemoryOrderRequest(BaseModel):
    """New ordered list of memory IDs for a chapter (full replacement order)."""
    memory_ids: List[uuid.UUID] = Field(..., min_length=1)


class ChapterMemoryData(BaseModel):
    """A memory embedded inside a chapter response."""
    id: uuid.UUID
    memoir_id: uuid.UUID
    title: Optional[str] = None
    body_text: Optional[str] = None
    occurred_start: Optional[date] = None
    occurred_precision: Optional[str] = None


class ChapterData(BaseModel):
    """A generated chapter with its ordered member memories."""
    id: uuid.UUID
    memoir_id: uuid.UUID
    title: str
    subtitle: Optional[str] = None
    summary: Optional[str] = None
    status: str
    sort_order: int
    confidence: Optional[float] = None
    memories: List[ChapterMemoryData] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API response envelopes (consistent with the rest of the backend)
# ---------------------------------------------------------------------------

class GenerationStatusEnvelope(BaseModel):
    success: bool = True
    message: str = "Operation successful"
    data: GenerationStatusData


class ChapterEnvelope(BaseModel):
    success: bool = True
    message: str = "Operation successful"
    data: ChapterData


class ChaptersEnvelope(BaseModel):
    success: bool = True
    message: str = "Operation successful"
    data: List[ChapterData]


class PublishData(BaseModel):
    memoir_id: uuid.UUID
    chapters_published: int
    memoir_status: str


class PublishEnvelope(BaseModel):
    success: bool = True
    message: str = "Operation successful"
    data: PublishData