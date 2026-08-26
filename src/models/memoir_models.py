from datetime import datetime, date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


class RelationshipGroup(str, Enum):
    spouse_partner = "spouse_partner"
    child = "child"
    grandchild = "grandchild"
    sibling = "sibling"
    parent = "parent"
    extended_family = "extended_family"
    friend = "friend"
    colleague = "colleague"
    neighbour = "neighbour"
    self = "self"
    other = "other"


class MemoirCreateRequest(BaseModel):
    subject_name: str = Field(..., min_length=1, max_length=200)
    birth_year: Optional[int] = Field(None, ge=1800, le=2100)
    end_year: Optional[int] = Field(None, ge=1800, le=2100)
    is_living: bool
    relationship: RelationshipGroup


class MemoirOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_name: str
    subject_born_on: Optional[date] = None
    subject_died_on: Optional[date] = None
    subject_is_living: bool
    status: str
    created_at: datetime


class ContributorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: Optional[str] = None
    display_name: str
    role: Literal["Admin", "Contributor"]
    status: Literal["Accepted", "Pending"]
