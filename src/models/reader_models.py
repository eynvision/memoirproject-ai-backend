# Pydantic contracts for the public reading experience: the assembled book,
# the comment thread (one level of replies), reactions and search hits.

from datetime import date, datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BookMedia(BaseModel):
    id: UUID
    kind: str
    playback_url: str
    caption: Optional[str] = None
    duration_ms: Optional[int] = None


class ReactionSummary(BaseModel):
    counts: Dict[str, int] = {}
    mine: List[str] = []


class CommentNode(BaseModel):
    id: UUID
    author_name: str
    body: str
    created_at: datetime
    replies: List["CommentNode"] = []
    reactions: ReactionSummary = Field(default_factory=ReactionSummary)


CommentNode.model_rebuild()


class BookMemory(BaseModel):
    id: UUID
    title: Optional[str] = None
    body_text: Optional[str] = None
    transcript: Optional[str] = None
    media: List[BookMedia] = []
    comments: List[CommentNode] = []
    reactions: ReactionSummary = Field(default_factory=ReactionSummary)
    comment_reactions: Dict[str, ReactionSummary] = {}


class BookChapter(BaseModel):
    id: Optional[UUID] = None
    title: str
    summary: Optional[str] = None
    sort_order: int = 0
    memories: List[BookMemory] = []


class BookMemoir(BaseModel):
    id: UUID
    subject_name: str
    subject_born_on: Optional[date] = None
    subject_died_on: Optional[date] = None
    subject_is_living: bool
    description: Optional[str] = None
    published_at: Optional[datetime] = None


class BookOut(BaseModel):
    memoir: BookMemoir
    chapters: List[BookChapter] = []
    media_library: List[BookMedia] = []
    comments_open: bool = False
    share_token: Optional[str] = None


class CommentCreateRequest(BaseModel):
    memory_id: UUID
    body: str = Field(..., min_length=1, max_length=2000)
    author_name: str = Field(..., min_length=1, max_length=200)
    parent_comment_id: Optional[UUID] = None


class ReactionRequest(BaseModel):
    target_type: Literal["memory", "comment"]
    target_id: UUID
    kind: str = Field(..., min_length=1, max_length=60)
    author_name: str = Field(..., min_length=1, max_length=200)


class ReactionToggleOut(BaseModel):
    target_type: Literal["memory", "comment"]
    target_id: UUID
    summary: ReactionSummary


class SearchHit(BaseModel):
    memory_id: UUID
    chapter_id: Optional[UUID] = None
    title: Optional[str] = None
    snippet: str


class SearchOut(BaseModel):
    hits: List[SearchHit] = []


class ShareLinkOut(BaseModel):
    token: str