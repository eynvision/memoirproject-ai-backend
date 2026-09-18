from typing import Dict, Any, Optional, List
from fastapi import HTTPException, status
from src.integrations.supabase_client import supabase_admin

class ShareRepository:

    @staticmethod
    async def get_participant(memoir_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Resolves the participant ID and role for the user."""
        try:
            res = supabase_admin.table("memoir_participant")\
                .select("id, role")\
                .eq("memoir_id", memoir_id)\
                .eq("user_id", user_id)\
                .is_("removed_at", None)\
                .execute()
            return res.data[0] if res.data else None
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    @staticmethod
    async def get_memoir_by_id(memoir_id: str) -> Optional[Dict[str, Any]]:
        res = supabase_admin.table("memoir").select("*").eq("id", memoir_id).execute()
        return res.data[0] if res.data else None

    @staticmethod
    async def get_active_link(memoir_id: str, scope: str) -> Optional[Dict[str, Any]]:
        """Matches your SQL constraint: one live link per scope per memoir."""
        res = supabase_admin.table("memoir_link")\
            .select("*")\
            .eq("memoir_id", memoir_id)\
            .eq("scope", scope)\
            .is_("revoked_at", None)\
            .execute()
        return res.data[0] if res.data else None

    @staticmethod
    async def get_link_by_token(token: str) -> Optional[Dict[str, Any]]:
        res = supabase_admin.table("memoir_link").select("*").eq("token", token).execute()
        return res.data[0] if res.data else None

    @staticmethod
    async def insert_link(insert_data: Dict[str, Any]) -> Dict[str, Any]:
        # Token and defaults are generated automatically by your Postgres schema
        res = supabase_admin.table("memoir_link").insert(insert_data).select("*").execute()
        if not res.data:
            raise HTTPException(status_code=400, detail="Failed to create share link")
        return res.data[0]

    @staticmethod
    async def update_link(link_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        res = supabase_admin.table("memoir_link").update(update_data).eq("id", link_id).select("*").execute()
        return res.data[0]

    @staticmethod
    async def increment_open_count(link_id: str, current_count: int) -> None:
        supabase_admin.table("memoir_link").update({"open_count": current_count + 1}).eq("id", link_id).execute()

    @staticmethod
    async def get_shared_memoir_view(memoir_id: str) -> List[Dict[str, Any]]:
        res = supabase_admin.table("memory")\
            .select("*, memory_media(*, media_asset(*))")\
            .eq("memoir_id", memoir_id)\
            .eq("status", "draft")\
            .is_("deleted_at", None)\
            .order("created_at", desc=True)\
            .execute()
        return res.data or []