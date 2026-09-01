from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional

from app.db.dependencies import get_db
from app.core.auth import get_current_user, get_current_user_id
from app.domain.model import MemoirProject, MediaAsset, User
from app.domain.schemas import (
    MediaAssetOut,
    OnboardingPhotoUploadOut,
    ProjectCreate,
    ProjectUpdate,
    ProjectCoverUpdate,
    ProjectOut,
)
from app.services.storage import storage_service

router = APIRouter(prefix="/projects", tags=["Projects"])


def _get_owned_project(db: Session, project_id: UUID, user_id: int) -> MemoirProject:
    project = db.query(MemoirProject).filter(
        MemoirProject.id == project_id,
        MemoirProject.owner_id == user_id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = MemoirProject(
        owner_id=current_user.id,
        subject_name=payload.subject_name,
        relationship_to_subject=payload.relationship_to_subject,
        start_date=payload.start_date,
        end_date=payload.end_date,
        onboarding_step=1,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(MemoirProject).filter(MemoirProject.owner_id == current_user.id).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_owned_project(db, project_id, current_user.id)
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_owned_project(db, project_id, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


@router.patch("/{project_id}/cover", response_model=ProjectOut)
def update_cover(
    project_id: UUID,
    payload: ProjectCoverUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_owned_project(db, project_id, current_user.id)
    project.cover_photo_url = payload.cover_photo_url
    if payload.cover_photo_thumbnail_url:
        project.cover_photo_thumbnail_url = payload.cover_photo_thumbnail_url
    db.commit()
    db.refresh(project)
    return project


# --- Step 4 Onboarding Photo Upload & Cover Selection ---

@router.post("/{project_id}/photos", response_model=OnboardingPhotoUploadOut)
async def upload_onboarding_photo(
    project_id: UUID,
    file: Optional[UploadFile] = File(None),
    file_key: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    is_cover: bool = Form(False),
    is_subject: bool = Form(True),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Support onboarding photo upload (subject photos, cover photo selection — Step 4 of wizard).
    Stores image, generates thumbnail, and associates it with the project.
    """
    project = _get_owned_project(db, project_id, user_id)

    if file:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded photo is empty.")

        content_type = file.content_type or "image/jpeg"
        key = storage_service.generate_file_key(file.filename or "subject_photo.jpg", folder="projects")
        result = storage_service.process_and_save_image(key, file_bytes, generate_thumb=True)

        stored_file_key = result["file_key"]
        stored_file_url = result["file_url"]
        stored_thumb_url = result.get("thumbnail_url")
        file_size = result["file_size_bytes"]
        mime_type = content_type
    elif file_key:
        try:
            file_bytes = storage_service.read_bytes(file_key)
            result = storage_service.process_and_save_image(file_key, file_bytes, generate_thumb=True)
            stored_file_url = result["file_url"]
            stored_thumb_url = result.get("thumbnail_url")
            file_size = len(file_bytes)
        except Exception:
            stored_file_url = f"/storage/files/{file_key}"
            stored_thumb_url = None
            file_size = 0
        stored_file_key = file_key
        mime_type = "image/jpeg"
    else:
        raise HTTPException(status_code=400, detail="Either 'file' or 'file_key' must be provided.")

    media_asset = MediaAsset(
        project_id=project.id,
        user_id=user_id,
        asset_type="cover_photo" if is_cover else "subject_photo",
        file_key=stored_file_key,
        file_url=stored_file_url,
        thumbnail_url=stored_thumb_url,
        caption=caption,
        mime_type=mime_type,
        file_size_bytes=file_size,
        is_cover_photo=is_cover,
        is_subject_photo=is_subject,
    )
    db.add(media_asset)

    if is_cover or not project.cover_photo_url:
        project.cover_photo_url = stored_file_url
        project.cover_photo_thumbnail_url = stored_thumb_url

    db.commit()
    db.refresh(media_asset)

    return OnboardingPhotoUploadOut(
        id=media_asset.id,
        project_id=project.id,
        file_key=stored_file_key,
        file_url=stored_file_url,
        thumbnail_url=stored_thumb_url,
        caption=caption,
        is_cover_photo=is_cover,
        is_subject_photo=is_subject,
        created_at=media_asset.created_at,
    )


@router.get("/{project_id}/photos", response_model=List[MediaAssetOut])
def list_project_photos(
    project_id: UUID,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    List all photos attached to a project (subject photos, cover photos, memory photos).
    """
    _get_owned_project(db, project_id, user_id)
    assets = db.query(MediaAsset).filter(
        MediaAsset.project_id == project_id,
        MediaAsset.asset_type.in_(["photo", "cover_photo", "subject_photo"]),
    ).order_by(MediaAsset.created_at.desc()).all()
    return assets


@router.post("/{project_id}/cover-photo", response_model=ProjectOut)
async def set_project_cover_photo(
    project_id: UUID,
    file: Optional[UploadFile] = File(None),
    file_key: Optional[str] = Form(None),
    photo_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Set or upload cover photo for project, generating thumbnails.
    """
    project = _get_owned_project(db, project_id, user_id)

    if file:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded photo is empty.")

        key = storage_service.generate_file_key(file.filename or "cover.jpg", folder="covers")
        result = storage_service.process_and_save_image(key, file_bytes, generate_thumb=True)

        project.cover_photo_url = result["file_url"]
        project.cover_photo_thumbnail_url = result.get("thumbnail_url")

        media_asset = MediaAsset(
            project_id=project.id,
            user_id=user_id,
            asset_type="cover_photo",
            file_key=result["file_key"],
            file_url=result["file_url"],
            thumbnail_url=result.get("thumbnail_url"),
            is_cover_photo=True,
            is_subject_photo=False,
        )
        db.add(media_asset)
    elif photo_url:
        project.cover_photo_url = photo_url
    elif file_key:
        project.cover_photo_url = f"/storage/files/{file_key}"
    else:
        raise HTTPException(status_code=400, detail="Provide 'file', 'photo_url', or 'file_key'.")

    db.commit()
    db.refresh(project)
    return project