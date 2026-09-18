from typing import List, Optional , Literal
from pydantic import BaseModel, Field 
class MemoryMapping(BaseModel):
    memory_id: str = Field(description="The exact UUID of the memory.")
    inferred_date: Optional[Literal["day", "month", "year", "decade"]] = Field(
        default=None,
        description="The precision of the date. Must be strictly one of: 'day', 'month', 'year', or 'decade'."
    )
class ChapterOutput(BaseModel):
    title: str = Field(description="A distinct, chronological title for this chapter.")
    summary: Optional[str] = Field(default=None, description="A 1-2 sentence overview.")
    narrative_prose: str = Field(description="A cohesive, continuous biographical narrative weaving together all memories assigned to this chapter using strictly the provided facts.")
    sort_order: int = Field(description="The chronological sequence order.")
    memories: List[MemoryMapping] = Field(description="List of memories assigned to this chapter.")
class MemoirOrganizationOutput(BaseModel):
    chapters: List[ChapterOutput] = Field(description="List of chronological chapters covering all provided memories.")

class OrganizeResponseEnvelope(BaseModel):
    success: bool = True
    message: str = "Organization started in the background."
    
class ChapterUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, description="The new title chosen by the user.")
    summary: Optional[str] = Field(None, description="The new summary chosen by the user.")

class MemoryMoveRequest(BaseModel):
    new_chapter_id: str = Field(description="The ID of the chapter this memory should be moved to.")
    
class ChatMessage(BaseModel):
    role: str = Field(description="The role of the speaker, e.g. 'user' or 'assistant'.")
    content: str = Field(description="The text content of the message.")

class ChatRequest(BaseModel):
    message: str = Field(description="The user's latest prompt or question for the AI co-author.")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Past conversation turns for context.")

class ChatResponse(BaseModel):
    success: bool = True
    reply: str = Field(description="Gemini's contextual response regarding the archive.")