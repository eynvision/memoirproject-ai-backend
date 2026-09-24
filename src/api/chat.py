"""
@file src/api/chat.py
@description FastAPI router for the memoir chat agent. The agent only proposes
changes; the user applies or discards each one via the confirm/reject
endpoints. Owner/admin only.
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from src.core.auth import get_current_user
from src.domain.chat_service import ChatService
from src.schemas.chat import ChatMessageRequest

router = APIRouter(prefix="/api/memoirs", tags=["Memoir Chat"])


def _extract_user_id(session: dict) -> str:
    """Unifies the user-ID key variants the JWT may expose."""
    return session.get("user_id") or session.get("id") or session.get("sub")


@router.post("/{memoir_id}/chat")
def send_chat_message(
    memoir_id: str,
    payload: ChatMessageRequest,
    session: dict = Depends(get_current_user),
):
    """
    Sends a message to the memoir assistant and returns its reply, plus any
    changes it proposed this turn (status 'pending' until confirmed).
    """
    user_id = _extract_user_id(session)
    data = ChatService.send_message(memoir_id, user_id, payload.message)
    return {"success": True, "message": "Operation successful.", "data": data}


@router.get("/{memoir_id}/chat")
def get_chat_history(
    memoir_id: str,
    limit: int = 50,
    session: dict = Depends(get_current_user),
):
    """Returns the user's recent conversation (text only) and their pending proposed changes."""
    user_id = _extract_user_id(session)
    data = ChatService.get_history(memoir_id, user_id, limit=max(1, min(limit, 200)))
    return {"success": True, "message": "Operation successful.", "data": data}


@router.post("/{memoir_id}/chat/actions/{action_id}/confirm")
def confirm_chat_action(
    memoir_id: str,
    action_id: str,
    background_tasks: BackgroundTasks,
    session: dict = Depends(get_current_user),
):
    """Applies a change the assistant proposed. Long-running ones continue in the background."""
    user_id = _extract_user_id(session)
    action, job = ChatService.confirm_action(memoir_id, action_id, user_id)
    if job:
        function, args = job
        background_tasks.add_task(function, *args)
    return {"success": True, "message": "Change applied.", "data": action}


@router.post("/{memoir_id}/chat/actions/{action_id}/reject")
def reject_chat_action(
    memoir_id: str,
    action_id: str,
    session: dict = Depends(get_current_user),
):
    """Discards a change the assistant proposed."""
    user_id = _extract_user_id(session)
    action = ChatService.reject_action(memoir_id, action_id, user_id)
    return {"success": True, "message": "Change discarded.", "data": action}
