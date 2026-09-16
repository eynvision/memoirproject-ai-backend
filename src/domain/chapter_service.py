"""
@file chapter_service.py
@description Business logic for AI memoir organisation: fetching and
normalising memories, running the LangChain suggestion job, validating the
AI's structured output before anything is saved, then exposing review,
reorder, and publish operations. The AI only suggests; humans approve.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, status

from src.core.config import CHAPTER_MAX_LIMIT, CHAPTER_MIN_LIMIT
from src.schemas.chapter import (
    ChapterUpdateRequest,
    GenerationStatusData,
    MemoryInputItem,
)
from src.domain.authorization import verify_active_participant
from src.integrations import chapter_repository
from src.integrations.memoir_organiser_chain import (
    MemoirOrganiserChain,
    MemoirOrganisationResult,
)

logger = logging.getLogger(__name__)

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _date_label(row: dict) -> Optional[str]:
    """Builds a human-friendly date label from occurred_* and precision."""
    start = row.get("occurred_start")
    if not start:
        return None

    date_str = str(start)
    year = date_str[:4]
    precision = row.get("occurred_precision") or "day"

    if precision == "year":
        return year
    if precision == "decade":
        return f"{year[:3]}0s"
    if precision == "month" and len(date_str) >= 7:
        month_index = int(date_str[5:7]) - 1
        return f"{_MONTH_NAMES[month_index]} {year}"
    return date_str


def _normalize_memories(rows: List[dict]) -> List[MemoryInputItem]:
    """Transforms raw memory rows into the normalised prompt shape."""
    items = []
    for row in rows:
        items.append(
            MemoryInputItem(
                id=row["id"],
                title=row.get("title"),
                content=row.get("body_text"),
                date_label=_date_label(row),
            )
        )
    return items


class ChapterService:
    """
    Coordinates the AI memoir organisation lifecycle while keeping the
    AI layer (LangChain) isolated behind a small interface.
    """

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    @classmethod
    def start_generation(cls, memoir_id: str, user_id: str) -> tuple:
        """
        Validates the requester, loads + normalises the memoir's memories,
        and records a 'running' generation job. Returns (generation_row,
        normalized_memories) so the caller can schedule the LLM work.
        """
        verify_active_participant(
            memoir_id, user_id, required_roles=["owner", "admin"]
        )

        latest = chapter_repository.fetch_latest_generation(memoir_id)
        if latest and latest.get("status") == "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A memoir generation is already running for this memoir.",
            )

        res = chapter_repository.fetch_memories_for_organisation(memoir_id)
        rows = res.data if res and res.data else []
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No memories found for this memoir. Add memories before generating chapters.",
            )

        memories = _normalize_memories(rows)

        record = {
            "memoir_id": memoir_id,
            "status": "running",
            "memory_count": len(memories),
            "started_by_user_id": user_id,
        }
        insert_res = chapter_repository.insert_generation_record(record)
        generation = insert_res.data[0]
        return generation, memories

    @classmethod
    def run_generation_job(
        cls,
        memoir_id: str,
        generation_id: str,
        memories: List[MemoryInputItem],
        user_id: str,
    ):
        """
        Background worker: asks the LangChain chain to organise the memories,
        validates the structured output, then replaces any previous draft
        chapters and marks the generation completed. Failures are recorded on
        the generation row so the status endpoint can surface them.
        """
        try:
            result = MemoirOrganiserChain().organise(memories)
            cls._validate_ai_output(result, memories, memoir_id)
            cls._save_chapters(memoir_id, result)

            chapter_repository.update_generation_record(generation_id, {
                "status": "completed",
                "error_message": None,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.exception("Memoir generation %s failed for memoir %s",
                             generation_id, memoir_id)
            chapter_repository.update_generation_record(generation_id, {
                "status": "failed",
                "error_message": str(e),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
            raise

    @classmethod
    def get_generation_status(cls, memoir_id: str, user_id: str) -> GenerationStatusData:
        """Returns the latest generation job state, or 'idle' if none ran yet."""
        verify_active_participant(memoir_id, user_id)
        gen = chapter_repository.fetch_latest_generation(memoir_id)
        if not gen:
            return GenerationStatusData(memoir_id=memoir_id, status="idle")

        return GenerationStatusData(
            memoir_id=memoir_id,
            generation_id=gen["id"],
            status=gen["status"],
            memory_count=gen.get("memory_count"),
            error_message=gen.get("error_message"),
            started_at=gen.get("started_at"),
            finished_at=gen.get("finished_at"),
        )

    # ------------------------------------------------------------------
    # Validation (step 5 of the design: never trust the AI blindly)
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_ai_output(
        result: MemoirOrganisationResult,
        memories: List[MemoryInputItem],
        memoir_id: str,
    ):
        """
        Rejects AI output that is structurally unsafe: chapters referring to
        memories we never provided, duplicated or missing memories, empty
        chapters, or out-of-range confidence. The original memory IDs keep
        every chapter traceable to its source content.
        """
        provided_ids = {str(item.id) for item in memories}
        chapters = result.chapters

        if not chapters:
            raise ValueError("The model returned no chapters.")

        if len(chapters) > CHAPTER_MAX_LIMIT:
            raise ValueError(
                f"The model returned {len(chapters)} chapters; maximum allowed is {CHAPTER_MAX_LIMIT}."
            )
        if len(memories) >= CHAPTER_MIN_LIMIT and len(chapters) < CHAPTER_MIN_LIMIT:
            # Below the "ideal" chapter count, but not structurally unsafe: a
            # small or tightly-related set of memories can legitimately group
            # into fewer chapters. Log it for visibility instead of rejecting
            # a valid, well-formed result.
            logger.info(
                "Memoir %s: model returned %d chapter(s), fewer than the suggested minimum of %d.",
                memoir_id, len(chapters), CHAPTER_MIN_LIMIT,
            )

        assigned_ids = set()
        for chapter in chapters:
            if not chapter.title or not chapter.title.strip():
                raise ValueError("The model returned a chapter without a title.")
            if not chapter.memory_ids:
                raise ValueError(f"Chapter '{chapter.title}' has no memories assigned.")
            if not (0.0 <= chapter.confidence <= 1.0):
                raise ValueError(f"Chapter '{chapter.title}' has invalid confidence '{chapter.confidence}'.")

            for memory_id in chapter.memory_ids:
                if memory_id not in provided_ids:
                    raise ValueError(
                        f"Chapter '{chapter.title}' references memory '{memory_id}' that was never provided. "
                        "The AI may have invented data; generation refused and can be retried."
                    )
                if memory_id in assigned_ids:
                    raise ValueError(
                        f"Memory '{memory_id}' was assigned to more than one chapter."
                    )
                assigned_ids.add(memory_id)

        unassigned = provided_ids - assigned_ids
        if unassigned:
            raise ValueError(
                f"{len(unassigned)} provided memories were not assigned to any chapter."
            )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _save_chapters(memoir_id: str, result: MemoirOrganisationResult):
        """Replaces prior draft chapters with the new AI suggestions."""
        chapter_repository.clear_draft_chapters(memoir_id)

        chapter_records = [
            {
                "memoir_id": memoir_id,
                "title": chapter.title,
                "subtitle": chapter.subtitle,
                "summary": chapter.summary,
                "status": "draft",
                "sort_order": index,
                "confidence": chapter.confidence,
            }
            for index, chapter in enumerate(result.chapters)
        ]

        insert_res = chapter_repository.insert_chapters(chapter_records)
        inserted = insert_res.data if insert_res else []

        inserted_by_order = {row.get("sort_order"): row.get("id") for row in inserted}

        link_records = []
        for index, chapter in enumerate(result.chapters):
            chapter_id = inserted_by_order.get(index)
            if not chapter_id:
                raise ValueError("Could not map an inserted chapter to the AI result.")
            for memory_index, memory_id in enumerate(chapter.memory_ids):
                link_records.append(
                    {
                        "chapter_id": chapter_id,
                        "memoir_id": memoir_id,
                        "memory_id": memory_id,
                        "sort_order": memory_index,
                    }
                )

        chapter_repository.insert_chapter_memories(link_records)

    # ------------------------------------------------------------------
    # Review operations (owner/admin only)
    # ------------------------------------------------------------------
    @classmethod
    def get_chapters(cls, memoir_id: str, user_id: str, chapter_status: Optional[str] = None) -> list:
        """Returns chapters with their ordered member memories."""
        verify_active_participant(memoir_id, user_id)

        if chapter_status not in (None, "draft", "published"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status filter must be one of: draft, published.",
            )

        res = chapter_repository.fetch_chapters_with_memories(memoir_id, chapter_status)
        rows = res.data if res and res.data else []

        chapters = []
        for row in rows:
            raw_links = [link for link in row.pop("chapter_memory", []) if link and link.get("memory")]
            raw_links.sort(key=lambda link: link.get("sort_order", 0))
            row["memories"] = [link["memory"] for link in raw_links]
            chapters.append(row)
        return chapters

    @classmethod
    def update_chapter(
        cls,
        memoir_id: str,
        chapter_id: str,
        user_id: str,
        payload: ChapterUpdateRequest,
    ) -> dict:
        """Edits title/subtitle/summary of a draft chapter."""
        verify_active_participant(memoir_id, user_id, required_roles=["owner", "admin"])

        chapter = chapter_repository.fetch_chapter_by_id(chapter_id, memoir_id)
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found in this memoir.",
            )
        if chapter.get("status") == "published":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Published chapters cannot be edited.",
            )

        updates = payload.model_dump(exclude_none=True)
        update_res = chapter_repository.update_chapter(chapter_id, memoir_id, updates)
        updated = update_res.data[0] if update_res and update_res.data else chapter
        return updated

    @classmethod
    def reorder_chapter_memories(
        cls,
        memoir_id: str,
        chapter_id: str,
        user_id: str,
        memory_ids: List[str],
    ) -> dict:
        """Rebuilds the ordered membership of a draft chapter."""
        verify_active_participant(memoir_id, user_id, required_roles=["owner", "admin"])

        chapter = chapter_repository.fetch_chapter_by_id(chapter_id, memoir_id)
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found in this memoir.",
            )
        if chapter.get("status") == "published":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Published chapters cannot be reordered.",
            )

        owned = chapter_repository.fetch_memories_by_ids(memoir_id, memory_ids)
        owned_ids = {str(row["id"]) for row in owned}
        missing = [m for m in memory_ids if m not in owned_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"One or more memory IDs do not belong to this memoir: {missing}",
            )

        chapter_repository.replace_chapter_memory_order(chapter_id, memoir_id, memory_ids)
        return {"chapter_id": chapter_id, "memory_order": memory_ids}

    # ------------------------------------------------------------------
    # Publication (humans approve; the AI never publishes)
    # ------------------------------------------------------------------
    @classmethod
    def publish_memoir(cls, memoir_id: str, user_id: str) -> dict:
        """Promotes draft chapters to published and marks the memoir published."""
        verify_active_participant(memoir_id, user_id, required_roles=["owner", "admin"])

        res = chapter_repository.fetch_chapters_with_memories(memoir_id, status="draft")
        drafts = res.data if res and res.data else []
        if not drafts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No draft chapters to publish. Generate chapters first.",
            )

        chapter_repository.mark_chapters_published(memoir_id)
        chapter_repository.update_memoir_status(memoir_id, "published")

        return {
            "memoir_id": memoir_id,
            "chapters_published": len(drafts),
            "memoir_status": "published",
        }