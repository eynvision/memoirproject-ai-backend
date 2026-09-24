"""
@file api/memoir.py
@description FastAPI router handling HTTP endpoints for memoir creation, 
management, and live memoir retrieval.
"""

from fastapi import APIRouter, Depends, status
from src.schemas.memoir import MemoirCreateRequest, MemoirResponseEnvelope
from src.domain.memoir_service import MemoirService
from src.core.auth import get_current_user

router = APIRouter(prefix="/api/memoirs", tags=["Memoirs"])

@router.get("/mine", status_code=status.HTTP_200_OK)
def list_my_memoirs(current_user: dict = Depends(get_current_user)):
    """
    Lists every memoir the current user is an active participant of, so the
    frontend can recover an active memoir after login without relying on
    client-side cache from a prior signup/onboarding flow.
    """
    user_id = current_user.get("user_id") or current_user.get("id") or current_user.get("sub")
    memoirs = MemoirService.list_my_memoirs(user_id)
    return {
        "success": True,
        "message": "Operation successful.",
        "data": memoirs,
    }

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=MemoirResponseEnvelope)
def create_memoir(
    payload: MemoirCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Creates a new root memoir container for a subject. 
    This must be executed first to obtain a memoir_id before adding media or memories.
    """
    user_id = current_user.get("user_id") or current_user.get("id") or current_user.get("sub")
    
    user_session = {"user_id": user_id}
    new_memoir = MemoirService.create_memoir(payload, user_session)
    return {
        "success": True,
        "message": "Memoir successfully created.",
        "data": new_memoir
    }

@router.get("/{memoir_id}/live", status_code=status.HTTP_200_OK)
def get_live_memoir(
    memoir_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves live memoir metadata, chapters, and memory entries for active participants.
    """
    user_id = current_user.get("user_id") or current_user.get("id") or current_user.get("sub")
    data = MemoirService.get_live_memoir(memoir_id, user_id)
    return {
        "success": True,
        "data": data
    }