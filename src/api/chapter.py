"""
@file src/api/chapter.py
@description FastAPI router for AI memoir organisation: triggers background
chapter generation, polls generation status, lists/edits/reorders draft
chapters, and publishes the final memoir. The AI only suggests; publication
requires explicit human approval.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from src.core.auth import get_current_user
from src.domain.chapter_service import ChapterService
from src.schemas.chapter import (
    ChapterMemoryOrderRequest,
    ChapterUpdateRequest,
)

router = APIRouter(prefix="/api/memoirs", tags=["Memoir Organisation"])


def _extract_user_id(session: dict) -> str:
    """Unifies the user-ID key variants the JWT may expose."""
    return session.get("user_id") or session.get("id") or session.get("sub")


# ------------------------------------------------------------------
# 1. Trigger generation (background)
# ------------------------------------------------------------------
@router.post("/{memoir_id}/generate", status_code=status.HTTP_202_ACCEPTED)
def start_memoir_generation(
    memoir_id: str,
    background_tasks: BackgroundTasks,
    session: dict = Depends(get_current_user),
):
    """
    Starts an AI organisation run in the background. Immediately returns
    the new generation job id; the client polls GET .../generation-status.
    """
    user_id = _extract_user_id(session)
    generation, memories = ChapterService.start_generation(memoir_id, user_id)

    background_tasks.add_task(
        ChapterService.run_generation_job,
        memoir_id=memoir_id,
        generation_id=generation["id"],
        memories=memories,
        user_id=user_id,
    )

    return {
        "success": True,
        "message": "Memoir generation started.",
        "data": {
            "generation_id": generation["id"],
            "memoir_id": memoir_id,
            "status": "running",
            "memory_count": generation.get("memory_count"),
        },
    }


# ------------------------------------------------------------------
# 2. Poll generation status
# ------------------------------------------------------------------
@router.get("/{memoir_id}/generation-status")
def get_generation_status(
    memoir_id: str,
    session: dict = Depends(get_current_user),
):
    """
    Returns the latest generation job status for the memoir.
    status is one of: idle | running | completed | failed.
    """
    user_id = _extract_user_id(session)
    data = ChapterService.get_generation_status(memoir_id, user_id)
    return {
        "success": True,
        "message": "Operation successful.",
        "data": data.model_dump(exclude_none=True),
    }


# ------------------------------------------------------------------
# 3. List chapters with embedded memories
# ------------------------------------------------------------------
@router.get("/{memoir_id}/chapters")
def list_chapters(
    memoir_id: str,
    chapter_status: str | None = Query(None, alias="status"),
    session: dict = Depends(get_current_user),
):
    """
    Returns the memoir's chapters, each with its ordered member memories.
    Optionally filter by status=draft or status=published.
    """
    user_id = _extract_user_id(session)
    chapters = ChapterService.get_chapters(memoir_id, user_id, chapter_status)
    return {
        "success": True,
        "message": "Operation successful.",
        "data": chapters,
    }


# ------------------------------------------------------------------
# 4. Update a draft chapter (title / subtitle / summary)
# ------------------------------------------------------------------
@router.patch("/{memoir_id}/chapters/{chapter_id}")
def update_chapter(
    memoir_id: str,
    chapter_id: str,
    payload: ChapterUpdateRequest,
    session: dict = Depends(get_current_user),
):
    user_id = _extract_user_id(session)
    updated = ChapterService.update_chapter(memoir_id, chapter_id, user_id, payload)
    return {
        "success": True,
        "message": "Chapter updated.",
        "data": updated,
    }


# ------------------------------------------------------------------
# 5. Reorder memories inside a draft chapter
# ------------------------------------------------------------------
@router.patch("/{memoir_id}/chapters/{chapter_id}/memory-order")
def reorder_chapter_memories(
    memoir_id: str,
    chapter_id: str,
    payload: ChapterMemoryOrderRequest,
    session: dict = Depends(get_current_user),
):
    """
    Full-replacement reorder: provide the complete ordered list of memory
    IDs for this chapter.
    """
    user_id = _extract_user_id(session)
    result = ChapterService.reorder_chapter_memories(
        memoir_id, chapter_id, user_id, [str(mid) for mid in payload.memory_ids]
    )
    return {
        "success": True,
        "message": "Memory order updated.",
        "data": result,
    }


# ------------------------------------------------------------------
# 6. Publish the memoir
# ------------------------------------------------------------------
@router.post("/{memoir_id}/publish")
def publish_memoir(
    memoir_id: str,
    session: dict = Depends(get_current_user),
):
    """
    Promotes all draft chapters to published and marks the memoir as published.
    The owner reviews and approves — the AI never publishes on its own.
    """
    user_id = _extract_user_id(session)
    result = ChapterService.publish_memoir(memoir_id, user_id)
    return {
        "success": True,
        "message": "Memoir published successfully.",
        "data": result,
    }