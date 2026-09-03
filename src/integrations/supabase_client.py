import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from supabase import Client, create_client

logger = logging.getLogger(__name__)

_BUCKET = "memoir-media"
_UPLOAD_TTL_SECONDS = 60 * 10
_READ_TTL_SECONDS = 60 * 60


def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def build_storage_key(memoir_id: str, kind: str, mime_type: str) -> str:
    """Build a unique key scoped below the memoir and media kind."""
    ext = _mime_to_ext(mime_type)
    return f"{memoir_id}/{kind}/{uuid4()}.{ext}"


def _signed_url(response: object) -> str:
    """Support the response key names used by Supabase client versions."""
    if isinstance(response, dict):
        value = response.get("signedURL") or response.get("signed_url")
        if isinstance(value, str) and value:
            return value

    for attribute in ("signedURL", "signed_url"):
        value = getattr(response, attribute, None)
        if isinstance(value, str) and value:
            return value

    raise RuntimeError("Supabase did not return a signed URL.")


def create_upload_url(storage_key: str) -> tuple[str, datetime]:
    client = get_supabase()
    response = client.storage.from_(_BUCKET).create_signed_upload_url(storage_key)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=_UPLOAD_TTL_SECONDS
    )
    return _signed_url(response), expires_at


def create_read_url(storage_key: str) -> str:
    """Return a private, time-limited URL for image/audio playback."""
    client = get_supabase()
    response = client.storage.from_(_BUCKET).create_signed_url(
        storage_key,
        _READ_TTL_SECONDS,
    )
    return _signed_url(response)


def delete_object(storage_key: str) -> None:
    client = get_supabase()
    client.storage.from_(_BUCKET).remove([storage_key])


_EXT_MAP = {
    "audio/webm": "webm",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/wav": "wav",
    "audio/ogg": "ogg",
    "audio/aac": "aac",
    "audio/x-m4a": "m4a",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _mime_to_ext(mime_type: str) -> str:
    base_mime = mime_type.split(";")[0].strip().lower()
    ext = _EXT_MAP.get(base_mime)

    if ext:
        return ext
    if "webm" in base_mime:
        return "webm"
    if "mp4" in base_mime or "m4a" in base_mime:
        return "m4a"
    if "wav" in base_mime:
        return "wav"
    if "mpeg" in base_mime or "mp3" in base_mime:
        return "mp3"

    raise ValueError(f"Unsupported mime type: {mime_type}")
