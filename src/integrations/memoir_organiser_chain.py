"""
@file memoir_organiser_chain.py
@description LangChain integration wrapper for AI memoir organisation.
It owns the prompt, the Gemini model call, and structured-output parsing,
so the domain service only sees clean, validated data structures.

The model is treated strictly as a suggester: it is given only the provided
memories and must reference them exclusively by their memory IDs.
"""

import json
import logging
from typing import List, Optional

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from src.core.config import CHAPTER_BATCH_SIZE, settings
from src.schemas.chapter import MemoryInputItem

logger = logging.getLogger(__name__)


class ChapterSuggestion(BaseModel):
    """One chapter group suggested by the model for a set of memories."""
    title: str = Field(description="Short evocative title for the chapter")
    subtitle: Optional[str] = Field(default=None, description="One-line subtitle")
    summary: Optional[str] = Field(default=None, description="2-3 sentence chapter summary")
    memory_ids: List[str] = Field(description="Memory IDs belonging to this chapter (only IDs given to you)")
    confidence: float = Field(ge=0.0, le=1.0, description="How confident you are in this grouping (0-1)")
    rationale: Optional[str] = Field(default=None, description="Why these memories belong together")


class MemoirOrganisationResult(BaseModel):
    """Structured result: the full chapter plan for the memoir."""
    chapters: List[ChapterSuggestion]


_SYSTEM_PROMPT = """You are a sensitive memoir editor (biographer). You are helping someone
turn a collection of personal memories into an organised, publishable memoir.

You will receive a JSON list of memories. Each memory has:
- id: a unique identifier you must use to reference it
- title: optional memory title
- content: the memory text
- date_label: approximate date/precision (may be absent)

TASK
Group the memories into meaningful chapters and detail:
1. A short evocative chapter title.
2. A subtitle and a 2-3 sentence summary.
3. The list of memory IDs that belong to this chapter.
4. A confidence score (0-1) for each chapter and a short rationale.

GUIDELINES
- Aim for 3 to 7 chapters in total (fewer only if the memoir has very few memories).
- Order chapters chronologically: earlier chapters cover earlier years/periods.
- Group memories by shared theme, period, or narrative arc. Related memories
  should stay together.
- Use ONLY the ids from the provided list. Never invent ids, facts, dates,
  people, or places. If information is missing or uncertain, do not guess.
- Every provided memory must be assigned to exactly one chapter.
- Keep the original memory content unchanged.</think>

Human prompt (fed the memories):

{memories}
"""


class MemoirOrganiserChain:
    """
    Wraps the Gemini model + prompt into an 'organise' entrypoint that returns
    a validated MemoirOrganisationResult. Constructing it fails fast when the
    Google API key is missing, mirroring the AssemblyAI transcription pattern.
    """

    def __init__(self):
        if not settings.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY is missing from environment variables. "
                "Memoir organisation cannot run without it."
            )
        self._llm = ChatGoogleGenerativeAI(
            model=settings.google_model,
            google_api_key=settings.google_api_key,
            temperature=0.2,
        ).with_structured_output(MemoirOrganisationResult)

    def organise(self, memories: List[MemoryInputItem]) -> MemoirOrganisationResult:
        """
        Groups memories into chapters. Memories are chunked when the list is
        larger than the configured batch size so the request stays inside the
        model's context window; results from each chunk are combined.
        """
        if not memories:
            raise ValueError("Cannot organise an empty set of memories.")

        chunks = [
            memories[i: i + CHAPTER_BATCH_SIZE]
            for i in range(0, len(memories), CHAPTER_BATCH_SIZE)
        ]

        combined = MemoirOrganisationResult(chapters=[])
        for chunk in chunks:
            payload = [
                json.loads(item.model_dump_json(exclude_none=True)) for item in chunk
            ]
            prompt = ChatPromptTemplate.from_messages(
                [("system", _SYSTEM_PROMPT), ("human", "{memories}")]
            )
            chain = prompt | self._llm
            result = chain.invoke({"memories": json.dumps(payload, indent=2)})
            combined.chapters.extend(result.chapters)

        logger.info("Memoir organisation produced %d chapters from %d memories.",
                    len(combined.chapters), len(memories))
        return combined