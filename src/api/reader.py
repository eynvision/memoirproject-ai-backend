# Public reading routes (no auth) plus the owner's moderation and share routes.

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import get_current_user_id
from src.domain.reader import reader_service
from src.models.reader_models import (
    BookOut,
    CommentCreateRequest,
    CommentNode,
    ReactionRequest,
    ReactionToggleOut,
    SearchOut,
    ShareLinkOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reader"])


@router.get("/public/book/{token}", response_model=BookOut)
async def public_book(token: str, reader_name: Optional[str] = Query(None)):
    try:
        return reader_service.get_book_by_token(token, reader_name)
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    except Exception as error:
        logger.error("Failed to load public book: %s", error)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not load the book."
        )


@router.get("/public/memoirs/{memoir_id}/book", response_model=BookOut)
async def public_book_by_memoir(memoir_id: UUID):
    """Anonymous readers opening /read/<memoirId> land here via the frontend."""
    try:
        return reader_service.get_public_book_by_memoir(memoir_id)
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))


@router.get("/memoirs/{memoir_id}/book", response_model=BookOut)
async def owner_book(
    memoir_id: UUID,
    reader_name: Optional[str] = Query(None),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return reader_service.get_book_for_owner(memoir_id, user_id, reader_name)
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))


@router.get("/memoirs/{memoir_id}/share-link", response_model=ShareLinkOut)
async def share_link(memoir_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        return ShareLinkOut(token=reader_service.get_share_link(memoir_id, user_id))
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))


@router.post(
    "/public/memoirs/{memoir_id}/comments",
    response_model=CommentNode,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(memoir_id: UUID, request: CommentCreateRequest):
    try:
        return reader_service.create_comment(memoir_id, request)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))


@router.delete(
    "/memoirs/{memoir_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_comment(
    memoir_id: UUID, comment_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    try:
        reader_service.owner_hide_comment(memoir_id, comment_id, user_id)
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))


@router.post("/public/memoirs/{memoir_id}/reactions", response_model=ReactionToggleOut)
async def toggle_reaction(memoir_id: UUID, request: ReactionRequest):
    try:
        return reader_service.toggle_reaction(memoir_id, request)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))


@router.get("/public/memoirs/{memoir_id}/search", response_model=SearchOut)
async def search(memoir_id: UUID, q: str = Query(..., min_length=2, max_length=100)):
    try:
        return reader_service.search_book(memoir_id, q)
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))