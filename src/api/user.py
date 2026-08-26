import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.auth import get_current_user_id
from src.integrations.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


class UserCreateRequest(BaseModel):
    id: UUID
    email: str
    full_name: str = Field(..., min_length=1, max_length=200)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreateRequest,
    current_user_id: UUID = Depends(get_current_user_id),
):
    """Create or update the backend account for the authenticated user."""
    if request.id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User identity does not match the access token.",
        )

    full_name = request.full_name.strip()
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Full name cannot be blank.",
        )

    try:
        client = get_supabase()
        client.table("user_account").upsert(
            {
                "id": str(current_user_id),
                "email": request.email.strip(),
                "full_name": full_name,
                "auth_provider_uid": str(current_user_id),
            },
            on_conflict="id",
        ).execute()

        return {"success": True}
    except Exception as error:
        logger.error("Failed to synchronize user account: %s", error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user account.",
        )
