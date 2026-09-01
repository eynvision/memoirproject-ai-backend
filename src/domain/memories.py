import os
import uuid
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.dependencies import get_db
from app.domain.model import MediaAsset, Memory, MemoirProject, User
from app.domain.schemas import (
    AudioStatusResponse,
    AudioUploadResponse,
    MediaAssetOut,
    MemoryCreate,
    MemoryOut,
    MemoryUpdate,
    PhotoUploadResponse,
)
from app.services.storage import storage_service
from app.services.transcription import run_transcription_job

router = APIRouter(tags=["Memories"])


def _get_owned_memory(db: Session, memory_id: UUID, user_id: int) -> Memory:
    memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return memory


@router.post("/memories", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Create a new memory (text, photo draft, or voice draft).
    """
    if payload.project_id:
        project = db.query(MemoirProject).filter(
            MemoirProject.id == payload.project_id,
            MemoirProject.owner_id == user_id,
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found.")

    memory = Memory(
        project_id=payload.project_id,
        user_id=user_id,
        type=payload.type,
        title=payload.title,
        body=payload.body,
        is_draft=payload.is_draft,
        location=payload.location,
        photo_url=payload.photo_url,
        photo_caption=payload.photo_caption,
        audio_url=payload.audio_url,
        audio_duration_seconds=payload.audio_duration_seconds,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


@router.get("/memories/{memory_id}", response_model=MemoryOut)
def get_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Get memory details including associated media assets.
    """
    memory = _get_owned_memory(db, memory_id, user_id)
    return memory


@router.get("/projects/{project_id}/memories", response_model=List[MemoryOut])
def list_project_memories(
    project_id: UUID,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    List all memories belonging to a project.
    """
    project = db.query(MemoirProject).filter(
        MemoirProject.id == project_id,
        MemoirProject.owner_id == user_id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    memories = db.query(Memory).filter(
        Memory.project_id == project_id,
        Memory.user_id == user_id,
    ).order_by(Memory.created_at.desc()).all()
    return memories


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: UUID,
    payload: MemoryUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Update memory title, body, location, caption, or draft status.
    """
    memory = _get_owned_memory(db, memory_id, user_id)
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(memory, key, value)
    db.commit()
    db.refresh(memory)
    return memory


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Delete a memory and its associated media assets.
    """
    memory = _get_owned_memory(db, memory_id, user_id)
    db.delete(memory)
    db.commit()
    return None


@router.post("/memories/{memory_id}/photos", response_model=PhotoUploadResponse)
async def upload_memory_photo(
    memory_id: UUID,
    file: Optional[UploadFile] = File(None),
    file_key: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    POST /memories/:id/photos — Upload photo(s), generate thumbnail, attach optional caption.
    Supports direct multipart file upload or linking a file uploaded via signed upload URL.
    """
    memory = _get_owned_memory(db, memory_id, user_id)

    if file:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        content_type = file.content_type or "image/jpeg"
        key = storage_service.generate_file_key(file.filename or "photo.jpg", folder="photos")
        result = storage_service.process_and_save_image(key, file_bytes, generate_thumb=True)

        file_key = result["file_key"]
        file_url = result["file_url"]
        thumbnail_key = result.get("thumbnail_key")
        thumbnail_url = result.get("thumbnail_url")
        file_size = result["file_size_bytes"]
        mime_type = content_type
    elif file_key:
        # File was uploaded via direct signed upload URL
        try:
            file_bytes = storage_service.read_bytes(file_key)
            result = storage_service.process_and_save_image(file_key, file_bytes, generate_thumb=True)
            file_url = result["file_url"]
            thumbnail_url = result.get("thumbnail_url")
            file_size = len(file_bytes)
            mime_type = "image/jpeg"
        except Exception:
            file_url = f"{storage_service.storage_dir}/{file_key}"
            thumbnail_url = None
            file_size = 0
            mime_type = "image/jpeg"
    else:
        raise HTTPException(status_code=400, detail="Either 'file' or 'file_key' must be provided.")

    # Create MediaAsset record
    media_asset = MediaAsset(
        memory_id=memory.id,
        project_id=memory.project_id,
        user_id=user_id,
        asset_type="photo",
        file_key=file_key,
        file_url=file_url,
        thumbnail_url=thumbnail_url,
        caption=caption,
        mime_type=mime_type,
        file_size_bytes=file_size,
    )
    db.add(media_asset)

    # Update Memory record
    memory.type = "photo"
    memory.photo_url = file_url
    memory.thumbnail_url = thumbnail_url
    if caption:
        memory.photo_caption = caption

    db.commit()
    db.refresh(media_asset)

    return PhotoUploadResponse(
        memory_id=memory.id,
        media_asset_id=media_asset.id,
        photo_url=file_url,
        thumbnail_url=thumbnail_url,
        caption=caption,
        type="photo",
    )


@router.post("/memories/{memory_id}/audio", response_model=AudioUploadResponse)
async def upload_memory_audio(
    memory_id: UUID,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    file_key: Optional[str] = Form(None),
    duration_seconds: Optional[float] = Form(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    POST /memories/:id/audio — Upload audio file (or direct signed upload key),
    create MediaAsset, and dispatch async speech-to-text transcription job.
    """
    memory = _get_owned_memory(db, memory_id, user_id)

    if file:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

        key = storage_service.generate_file_key(file.filename or "recording.wav", folder="audio")
        file_url = storage_service.save_bytes(key, file_bytes)
        file_key = key
        file_size = len(file_bytes)
        mime_type = file.content_type or "audio/wav"
    elif file_key:
        try:
            file_bytes = storage_service.read_bytes(file_key)
            file_size = len(file_bytes)
        except Exception:
            file_size = 0
        file_url = f"/storage/files/{file_key}"
        mime_type = "audio/wav"
    else:
        raise HTTPException(status_code=400, detail="Either 'file' or 'file_key' must be provided.")

    # Create MediaAsset record
    media_asset = MediaAsset(
        memory_id=memory.id,
        project_id=memory.project_id,
        user_id=user_id,
        asset_type="audio",
        file_key=file_key,
        file_url=file_url,
        duration_seconds=duration_seconds,
        mime_type=mime_type,
        file_size_bytes=file_size,
        transcription_status="pending",
    )
    db.add(media_asset)

    # Update Memory record
    memory.type = "voice"
    memory.audio_url = file_url
    if duration_seconds:
        memory.audio_duration_seconds = duration_seconds
    memory.transcription_status = "pending"

    db.commit()
    db.refresh(media_asset)

    # Kick off async speech-to-text transcription job
    background_tasks.add_task(run_transcription_job, media_asset.id, memory.id, file_key)

    return AudioUploadResponse(
        memory_id=memory.id,
        media_asset_id=media_asset.id,
        audio_url=file_url,
        transcription_status="pending",
        message="Audio uploaded successfully. Transcription job queued.",
    )


@router.get("/memories/{memory_id}/audio/status", response_model=AudioStatusResponse)
def get_memory_audio_status(
    memory_id: UUID,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    GET /memories/:id/audio/status — Poll transcription status,
    store transcript on MediaAsset once complete, and serve playback audio via signed URL.
    """
    memory = _get_owned_memory(db, memory_id, user_id)

    # Find latest audio media asset for this memory
    media_asset = db.query(MediaAsset).filter(
        MediaAsset.memory_id == memory_id,
        MediaAsset.asset_type == "audio",
    ).order_by(MediaAsset.created_at.desc()).first()

    status_val = memory.transcription_status
    transcript_val = memory.transcript_text
    error_val = None
    media_asset_id = None
    audio_playback_url = memory.audio_url

    if media_asset:
        media_asset_id = media_asset.id
        status_val = media_asset.transcription_status
        transcript_val = media_asset.transcript_text
        error_val = media_asset.transcription_error
        # Generate signed/expiring playback URL for private audio access
        if media_asset.file_key:
            audio_playback_url = storage_service.generate_signed_read_url(media_asset.file_key, expires_in=7200)

    return AudioStatusResponse(
        memory_id=memory.id,
        media_asset_id=media_asset_id,
        status=status_val,
        transcript=transcript_val,
        audio_url=audio_playback_url,
        error=error_val,
    )
