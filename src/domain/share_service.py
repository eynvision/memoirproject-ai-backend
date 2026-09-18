from datetime import datetime, timezone
from fastapi import HTTPException, status
from src.core.config import settings
from src.integrations.share_repository import ShareRepository

class ShareService:
    
    @staticmethod
    async def create_or_get_share_link(memoir_id: str, user_id: str, scope: str = "contribute"):
        participant = await ShareRepository.get_participant(memoir_id, user_id)
        if not participant or participant.get("role") != "owner":
            raise HTTPException(status_code=403, detail="Only owners can create share links.")

        existing = await ShareRepository.get_active_link(memoir_id, scope)
        if existing:
            return existing

        insert_data = {
            "memoir_id": memoir_id,
            "scope": scope,
            "created_by_participant_id": participant["id"]
        }
        return await ShareRepository.insert_link(insert_data)

    @staticmethod
    async def update_share_link(memoir_id: str, user_id: str, payload, scope: str = "contribute"):
        participant = await ShareRepository.get_participant(memoir_id, user_id)
        if not participant or participant.get("role") != "owner":
            raise HTTPException(status_code=403, detail="Only owners can update links.")
        
        link = await ShareRepository.get_active_link(memoir_id, scope)
        if not link:
            raise HTTPException(status_code=404, detail="No active share link.")

        update_data = {}
        if payload.expires_at is not None:
            update_data["expires_at"] = payload.expires_at.isoformat()

        if not update_data:
            return link
            
        return await ShareRepository.update_link(link["id"], update_data)

    @staticmethod
    async def revoke_share_link(memoir_id: str, user_id: str, scope: str = "contribute"):
        participant = await ShareRepository.get_participant(memoir_id, user_id)
        if not participant or participant.get("role") != "owner":
            raise HTTPException(status_code=403, detail="Only owners can revoke links.")
            
        link = await ShareRepository.get_active_link(memoir_id, scope)
        if not link:
            raise HTTPException(status_code=404, detail="No active share link.")

        await ShareRepository.update_link(link["id"], {"revoked_at": datetime.now(timezone.utc).isoformat()})