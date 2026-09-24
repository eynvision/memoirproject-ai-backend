"""
@file src/schemas/narrative.py
@description Response schema for the AI narrative layer (personality profile
and memory rewrite) status endpoint.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel


class NarrativeStatusData(BaseModel):
    """Progress of a memoir's personality-profile + rewrite job."""
    memoir_id: uuid.UUID
    status: Literal["idle", "running", "completed", "failed"] = "idle"
    error: Optional[str] = None
    updated_at: Optional[datetime] = None
    personality_profile: Optional[Dict[str, Any]] = None
