import uuid
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict


# --- Auth Schemas ---
class UsersignupSchema(BaseModel):
    full_name: str
    email: EmailStr
    password: str


class userloginSchema(BaseModel):
    email: EmailStr
    password: str


class UserResponseSchema(BaseModel):
    id: int
    full_name: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# --- Project Schemas ---
class ProjectCreate(BaseModel):
    subject_name: Optional[str] = None
    relationship_to_subject: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class ProjectUpdate(BaseModel):
    subject_name: Optional[str] = None
    relationship_to_subject: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    onboarding_step: Optional[int] = None
    onboarding_data: Optional[Dict[str, Any]] = None


class ProjectCoverUpdate(BaseModel):
    cover_photo_url: str
    cover_photo_thumbnail_url: Optional[str] = None


class ProjectOut(BaseModel):
    id: UUID
    owner_id: int
    subject_name: Optional[str] = None
    relationship_to_subject: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    cover_photo_url: Optional[str] = None
    cover_photo_thumbnail_url: Optional[str] = None
    onboarding_step: int
    onboarding_data: Optional[Dict[str, Any]] = None
    is_paid: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Storage Schemas ---
class SignedUploadUrlRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    folder: str = "media"
    is_public: bool = False


class SignedUploadUrlResponse(BaseModel):
    upload_url: str
    file_key: str
    download_url: str
    expires_in: int
    method: str = "PUT"


class SignedReadUrlRequest(BaseModel):
    file_key: str
    expires_in: int = 3600


class SignedReadUrlResponse(BaseModel):
    read_url: str
    expires_at: datetime


# --- Media Asset Schemas ---
class MediaAssetOut(BaseModel):
    id: UUID
    memory_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    user_id: int
    asset_type: str
    file_key: str
    file_url: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    transcription_status: str
    transcript_text: Optional[str] = None
    is_cover_photo: bool
    is_subject_photo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OnboardingPhotoUploadOut(BaseModel):
    id: UUID
    project_id: UUID
    file_key: str
    file_url: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    is_cover_photo: bool
    is_subject_photo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Memory Schemas ---
class MemoryCreate(BaseModel):
    project_id: Optional[UUID] = None
    type: str = "text"  # "text", "photo", "voice"
    title: Optional[str] = None
    body: Optional[str] = None
    is_draft: bool = False
    location: Optional[str] = None
    photo_url: Optional[str] = None
    photo_caption: Optional[str] = None
    audio_url: Optional[str] = None
    audio_duration_seconds: Optional[float] = None


class MemoryUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    is_draft: Optional[bool] = None
    location: Optional[str] = None
    photo_caption: Optional[str] = None


class MemoryOut(BaseModel):
    id: UUID
    project_id: Optional[UUID] = None
    user_id: int
    type: str
    title: Optional[str] = None
    body: Optional[str] = None
    is_draft: bool
    location: Optional[str] = None
    photo_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    photo_caption: Optional[str] = None
    audio_url: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    transcription_status: str
    transcript_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    media_assets: List[MediaAssetOut] = []

    model_config = ConfigDict(from_attributes=True)


class PhotoUploadResponse(BaseModel):
    memory_id: UUID
    media_asset_id: UUID
    photo_url: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    type: str = "photo"


class AudioUploadResponse(BaseModel):
    memory_id: UUID
    media_asset_id: UUID
    audio_url: str
    transcription_status: str
    message: str = "Audio uploaded and transcription job queued."


class AudioStatusResponse(BaseModel):
    memory_id: UUID
    media_asset_id: Optional[UUID] = None
    status: str
    transcript: Optional[str] = None
    audio_url: Optional[str] = None
    error: Optional[str] = None


# --- Checkout & Payment Schemas ---
class CheckoutSummaryOut(BaseModel):
    project_id: UUID
    project_title: str
    relationship_focus: str
    estimated_length: str
    interview_time: str
    subtotal: float
    tax: float
    total_due: float
    currency: str = "usd"


class PaymentIntentCreate(BaseModel):
    project_id: UUID


class PaymentIntentOut(BaseModel):
    client_secret: str
    payment_intent_id: str
    amount: int
    currency: str
    publishable_key: str
    status: str = "requires_payment_method"


class OrderCreate(BaseModel):
    project_id: UUID
    payment_intent_id: Optional[str] = None
    billing_details: Optional[Dict[str, Any]] = None


class OrderOut(BaseModel):
    id: UUID
    user_id: int
    project_id: UUID
    stripe_payment_intent_id: Optional[str] = None
    amount: int
    currency: str
    status: str
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentConfirmRequest(BaseModel):
    project_id: UUID
    payment_intent_id: str