import mimetypes
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from app.core.auth import get_current_user_id
from app.domain.schemas import (
    SignedUploadUrlRequest,
    SignedUploadUrlResponse,
    SignedReadUrlRequest,
    SignedReadUrlResponse,
)
from app.services.storage import storage_service

router = APIRouter(prefix="/storage", tags=["File Storage"])


@router.post("/signed-upload-url", response_model=SignedUploadUrlResponse)
def get_signed_upload_url(
    payload: SignedUploadUrlRequest,
    user_id: int = Depends(get_current_user_id),
):
    """
    Generate signed upload URL so clients upload directly to storage, keeping backend lightweight.
    """
    res = storage_service.generate_signed_upload_url(
        filename=payload.filename,
        content_type=payload.content_type,
        folder=payload.folder,
        is_public=payload.is_public,
    )
    return res


@router.put("/upload")
async def direct_upload_handler(
    request: Request,
    token: str = Query(..., description="Signed upload token"),
):
    """
    Direct upload endpoint for signed upload tokens (used by local/dev storage and backend upload proxy).
    """
    payload = storage_service.verify_upload_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired upload token.",
        )

    file_key = payload.get("file_key")
    content_type = payload.get("content_type", "application/octet-stream")
    if not file_key:
        raise HTTPException(status_code=400, detail="Invalid token payload.")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body.")

    # If it's an image, process and generate thumbnail
    if content_type.startswith("image/"):
        result = storage_service.process_and_save_image(file_key, body, generate_thumb=True)
        return {
            "message": "File uploaded successfully",
            "file_key": result["file_key"],
            "file_url": result["file_url"],
            "thumbnail_url": result.get("thumbnail_url"),
            "file_size_bytes": result["file_size_bytes"],
        }

    # Non-image files (e.g. audio, docs)
    file_url = storage_service.save_bytes(file_key, body)
    return {
        "message": "File uploaded successfully",
        "file_key": file_key,
        "file_url": file_url,
        "file_size_bytes": len(body),
    }


@router.post("/signed-read-url", response_model=SignedReadUrlResponse)
def get_signed_read_url(
    payload: SignedReadUrlRequest,
    user_id: int = Depends(get_current_user_id),
):
    """
    Generate signed/expiring read URL for private media.
    """
    read_url = storage_service.generate_signed_read_url(
        file_key=payload.file_key,
        expires_in=payload.expires_in,
    )
    from datetime import datetime, timedelta, timezone
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload.expires_in)
    return {"read_url": read_url, "expires_at": expires_at}


@router.get("/files/{file_key:path}")
def serve_file(
    file_key: str,
    token: Optional[str] = Query(None, description="Signed read token"),
):
    """
    Serve private or public media with signed token verification.
    """
    try:
        file_path = storage_service.get_file_path(file_key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    # If token is provided, verify it; if no token, allow if public or raise 403
    if token:
        if not storage_service.verify_read_token(file_key, token):
            raise HTTPException(status_code=403, detail="Invalid or expired access token.")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = "application/octet-stream"

    return FileResponse(path=str(file_path), media_type=mime_type)
