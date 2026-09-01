import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, DateTime, Boolean, ForeignKey, Integer, Float, Text, JSON, func, TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's native UUID type, otherwise uses CHAR(36) string in SQLite/MySQL.
    Accepts both uuid.UUID instances and string representations.
    """
    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            return str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    projects: Mapped[List["MemoirProject"]] = relationship("MemoirProject", back_populates="owner", cascade="all, delete-orphan")
    memories: Mapped[List["Memory"]] = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    media_assets: Mapped[List["MediaAsset"]] = relationship("MediaAsset", back_populates="user", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="user", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User")


class MemoirProject(Base):
    __tablename__ = "memoir_projects"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    subject_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    relationship_to_subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    cover_photo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cover_photo_thumbnail_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Wizard progress tracking (resumable)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=1)
    onboarding_data: Mapped[dict] = mapped_column(JSON, default=dict)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner: Mapped["User"] = relationship("User", back_populates="projects")
    memories: Mapped[List["Memory"]] = relationship("Memory", back_populates="project", cascade="all, delete-orphan")
    media_assets: Mapped[List["MediaAsset"]] = relationship("MediaAsset", back_populates="project", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="project", cascade="all, delete-orphan")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("memoir_projects.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    type: Mapped[str] = mapped_column(String(50), default="text")  # "text", "photo", "voice"
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Photo fields
    photo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    photo_caption: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Voice / Audio fields
    audio_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    audio_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transcription_status: Mapped[str] = mapped_column(String(50), default="none")  # "none", "pending", "processing", "completed", "failed"
    transcript_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="memories")
    project: Mapped[Optional["MemoirProject"]] = relationship("MemoirProject", back_populates="memories")
    media_assets: Mapped[List["MediaAsset"]] = relationship("MediaAsset", back_populates="memory", cascade="all, delete-orphan")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"), nullable=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("memoir_projects.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    asset_type: Mapped[str] = mapped_column(String(50))  # "photo", "audio", "cover_photo", "subject_photo"
    file_key: Mapped[str] = mapped_column(String(500))
    file_url: Mapped[str] = mapped_column(String(1000))
    thumbnail_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Transcription state
    transcription_status: Mapped[str] = mapped_column(String(50), default="none")  # "none", "pending", "processing", "completed", "failed"
    transcript_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcription_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_cover_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_subject_photo: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="media_assets")
    memory: Mapped[Optional["Memory"]] = relationship("Memory", back_populates="media_assets")
    project: Mapped[Optional["MemoirProject"]] = relationship("MemoirProject", back_populates="media_assets")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memoir_projects.id"), nullable=False)

    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    amount: Mapped[int] = mapped_column(Integer, default=29900)  # Amount in cents ($299.00 = 29900)
    currency: Mapped[str] = mapped_column(String(10), default="usd")
    status: Mapped[str] = mapped_column(String(50), default="pending")  # "pending", "completed", "failed", "canceled"

    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    billing_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="orders")
    project: Mapped["MemoirProject"] = relationship("MemoirProject", back_populates="orders")