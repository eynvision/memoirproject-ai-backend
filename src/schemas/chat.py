"""
@file src/schemas/chat.py
@description Request/response schemas for the memoir chat agent.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """A single user message to the chat agent."""
    message: str = Field(..., min_length=1, max_length=4000)


class ChatActionData(BaseModel):
    """A change the agent has proposed; nothing is applied until confirmed."""
    id: uuid.UUID
    action_type: str
    summary: str
    status: Literal["pending", "processing", "applied", "rejected", "failed"]
    payload: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class ChatReplyData(BaseModel):
    """The agent's reply plus any changes it proposed this turn."""
    reply: str
    pending_actions: List[ChatActionData] = Field(default_factory=list)


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    created_at: Optional[datetime] = None


class ChatHistoryData(BaseModel):
    messages: List[ChatHistoryItem] = Field(default_factory=list)
    pending_actions: List[ChatActionData] = Field(default_factory=list)
