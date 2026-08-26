import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.auth import get_current_user_id
from src.domain.memoir import memoir_service
from src.models.memoir_models import (
    ContributorOut,
    MemoirCreateRequest,
    MemoirOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memoirs", tags=["memoirs"])


@router.post("", response_model=MemoirOut, status_code=status.HTTP_201_CREATED)
async def create_memoir(
    request: MemoirCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return memoir_service.create_memoir(user_id, request)
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except Exception as error:
        logger.error("Failed to create memoir: %s", error)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not create memoir.",
        )


@router.get("/{memoir_id}/contributors", response_model=List[ContributorOut])
async def list_contributors(
    memoir_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return memoir_service.list_contributors(memoir_id, user_id)
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except Exception as error:
        logger.error("Failed to list contributors: %s", error)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not load contributors.",
        )


@router.get("/{memoir_id}", response_model=MemoirOut)
async def get_memoir(
    memoir_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return memoir_service.get_memoir(memoir_id, user_id)
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memoir not found.")
