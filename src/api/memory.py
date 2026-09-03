import logging
from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.core.auth import get_current_user_id
from src.domain.memory import memory_service
from src.models.memory_models import (
    MediaAssetOut,
    MediaConfirmRequest,
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryOut,
    MemoryPatchRequest,
    PresignRequest,
    PresignResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memoirs/{memoir_id}/memories", tags=["memories"])


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    memoir_id: UUID,
    include_drafts: bool = True,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        memories, total = memory_service.list_memories(
            memoir_id, user_id, include_drafts=include_drafts
        )
        return MemoryListResponse(memories=memories, total=total)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory(
    memoir_id: UUID,
    request: MemoryCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return memory_service.create_draft(memoir_id, user_id, request)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(
    memoir_id: UUID, memory_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    try:
        return memory_service.get_memory(memory_id, memoir_id, user_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.patch("/{memory_id}", response_model=MemoryOut)
async def patch_memory(
    memoir_id: UUID,
    memory_id: UUID,
    patch: MemoryPatchRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return memory_service.patch_memory(memory_id, memoir_id, user_id, patch)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.post("/{memory_id}/submit", response_model=MemoryOut)
async def submit_memory(
    memoir_id: UUID,
    memory_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return memory_service.submit_memory(
            memory_id, memoir_id, user_id, background_tasks
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memoir_id: UUID, memory_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    try:
        memory_service.delete_memory(memory_id, memoir_id, user_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.post("/{memory_id}/media/presign", response_model=PresignResponse)
async def presign_media_upload(
    memoir_id: UUID,
    memory_id: UUID,
    request: PresignRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return memory_service.presign_upload(memoir_id, memory_id, user_id, request)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.post(
    "/{memory_id}/media/confirm",
    response_model=MediaAssetOut,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_media_upload(
    memoir_id: UUID,
    memory_id: UUID,
    request: MediaConfirmRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return memory_service.confirm_media(memoir_id, memory_id, user_id, request)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.delete(
    "/{memory_id}/media/{media_asset_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_media(
    memoir_id: UUID,
    memory_id: UUID,
    media_asset_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        memory_service.remove_media(memoir_id, memory_id, media_asset_id, user_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))