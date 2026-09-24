"""
@file src/api/narrative.py
@description FastAPI router for the AI narrative layer: re-run the personality
profile + memory rewrite in the background, and poll its status. The rewrite
also runs automatically after chapter generation.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, status
from src.core.auth import get_current_user
from src.domain.narrative_service import NarrativeService

router = APIRouter(prefix="/api/memoirs", tags=["Memoir Narrative"])


def _extract_user_id(session: dict) -> str:
    """Unifies the user-ID key variants the JWT may expose."""
    return session.get("user_id") or session.get("id") or session.get("sub")


@router.post("/{memoir_id}/narrative/regenerate", status_code=status.HTTP_202_ACCEPTED)
def regenerate_narrative(
    memoir_id: str,
    background_tasks: BackgroundTasks,
    session: dict = Depends(get_current_user),
):
    """
    Re-runs the personality profile and rewrites every draft chapter's memories
    in the background. Poll GET .../narrative-status for progress.
    """
    user_id = _extract_user_id(session)
    NarrativeService.start_regeneration(memoir_id, user_id)
    background_tasks.add_task(NarrativeService.run_narrative_job, memoir_id)
    return {
        "success": True,
        "message": "Narrative rewrite started.",
        "data": {"memoir_id": memoir_id, "status": "running"},
    }


@router.get("/{memoir_id}/narrative-status")
def get_narrative_status(
    memoir_id: str,
    session: dict = Depends(get_current_user),
):
    """Returns the narrative job status and the personality profile, if built."""
    user_id = _extract_user_id(session)
    data = NarrativeService.get_status(memoir_id, user_id)
    return {
        "success": True,
        "message": "Operation successful.",
        "data": data.model_dump(mode="json"),
    }
