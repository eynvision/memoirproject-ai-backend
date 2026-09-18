from typing import Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from src.core.config import settings
from src.core.auth import get_current_user
from src.domain.share_service import ShareService
from src.integrations.share_repository import ShareRepository
from src.schemas.share import (
    ShareLinkResponse, ShareLinkResponseEnvelope, ShareLinkUpdateRequest, SharedMemoirResponseEnvelope
)

owner_router = APIRouter(prefix="/api/memoirs", tags=["Share Links"])
reader_router = APIRouter(prefix="/api/share", tags=["Shared Memoirs"])

def _to_link_response(link: Dict[str, Any]) -> ShareLinkResponse:
    return ShareLinkResponse(
        id=str(link["id"]),
        memoir_id=str(link["memoir_id"]),
        scope=link["scope"],
        token=link["token"],
        url=f"{settings.share_link_base_url.rstrip('/')}/{link['token']}",
        created_by_participant_id=str(link["created_by_participant_id"]) if link.get("created_by_participant_id") else None,
        created_at=link["created_at"],
        expires_at=link.get("expires_at"),
        revoked_at=link.get("revoked_at"),
        open_count=link.get("open_count", 0)
    )
# --- OWNER ROUTES ---
@owner_router.post("/{memoir_id}/share-link", status_code=201, response_model=ShareLinkResponseEnvelope)
async def create_share_link(memoir_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))
    link = await ShareService.create_or_get_share_link(memoir_id, user_id)
    return {"success": True, "message": "Share link ready.", "data": _to_link_response(link)}

@owner_router.patch("/{memoir_id}/share-link", response_model=ShareLinkResponseEnvelope)
async def patch_share_link(memoir_id: str, payload: ShareLinkUpdateRequest, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))
    link = await ShareService.update_share_link(memoir_id, user_id, payload)
    return {"success": True, "message": "Share link updated.", "data": _to_link_response(link)}

@owner_router.delete("/{memoir_id}/share-link", status_code=200)
async def delete_share_link(memoir_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))
    await ShareService.revoke_share_link(memoir_id, user_id)
    return {"success": True, "message": "Share link revoked."}

# --- READER/CONTRIBUTOR ROUTE ---
@reader_router.get("/{token}", response_model=SharedMemoirResponseEnvelope)
async def read_shared_memoir(token: str):
    link = await ShareRepository.get_link_by_token(token)
    
    # Check if link exists, is revoked, or is expired
    if not link or link.get("revoked_at"):
        raise HTTPException(status_code=404, detail="Not found.")
    
    if link.get("expires_at"):
        expires_at = datetime.fromisoformat(link["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=404, detail="Link expired.")

    memoir = await ShareRepository.get_memoir_by_id(link["memoir_id"])
    if not memoir:
        raise HTTPException(status_code=404, detail="Memoir not found.")

    # Increment the open count in the background
    await ShareRepository.increment_open_count(link["id"], link.get("open_count", 0))

    memories = await ShareRepository.get_shared_memoir_view(link["memoir_id"])
    
    data = {
        **memoir,
        "can_comment": memoir.get("comment_policy") == "public",
        "memories": memories
    }
    return {"success": True, "message": "Operation successful", "data": data}