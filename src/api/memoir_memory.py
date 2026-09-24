"""
@file src/api/memoir_memory.py
@description FastAPI router for editing a memory's text from within the
memoir preview screen. Kept separate from api/memory.py (prefixed
/api/memories) and api/chapter.py (chapter-organisation logic) so this
route can live under the clean /api/memoirs/{memoir_id}/... path
alongside the chapter endpoints it's meant to be used next to.
"""

from fastapi import APIRouter, Depends
from src.core.auth import get_current_user
from src.domain.memory_service import MemoryService
from src.schemas.memory import MemoryUpdateRequest

router = APIRouter(prefix="/api/memoirs", tags=["Memories"])


def _extract_user_id(session: dict) -> str:
    """Unifies the user-ID key variants the JWT may expose."""
    return session.get("user_id") or session.get("id") or session.get("sub")


@router.patch("/{memoir_id}/memories/{memory_id}")
def update_memory(
    memoir_id: str,
    memory_id: str,
    payload: MemoryUpdateRequest,
    session: dict = Depends(get_current_user),
):
    """
    Edits a memory's title/body_text. Owner/admin only, and blocked once
    the memoir has been published.
    """
    user_id = _extract_user_id(session)
    updated = MemoryService.update_memory(memoir_id, memory_id, user_id, payload)
    return {
        "success": True,
        "message": "Memory updated.",
        "data": updated,
    }
