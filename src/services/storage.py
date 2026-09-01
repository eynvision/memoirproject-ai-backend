import io
import os
import uuid
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import jwt
from PIL import Image

from app.core.config import settings


class StorageService:
    def __init__(self):
        self.storage_dir = Path(settings.STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.signing_secret = settings.STORAGE_SIGNING_SECRET
        self.algorithm = "HS256"

    def _sanitize_filename(self, filename: str) -> str:
        base = os.path.basename(filename)
        clean_name = "".join(c for c in base if c.isalnum() or c in (".", "-", "_")).strip()
        return clean_name or "file"

    def generate_file_key(self, filename: str, folder: str = "media") -> str:
        clean_name = self._sanitize_filename(filename)
        unique_id = uuid.uuid4().hex[:12]
        return f"{folder}/{unique_id}_{clean_name}"

    def generate_signed_upload_url(
        self,
        filename: str,
        content_type: str = "application/octet-stream",
        folder: str = "media",
        is_public: bool = False,
        expires_in: int = 3600,
    ) -> Dict[str, Any]:
        file_key = self.generate_file_key(filename, folder=folder)

        if settings.STORAGE_BACKEND == "s3" and settings.AWS_S3_BUCKET:
            try:
                import boto3
                s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
                    region_name=settings.AWS_REGION or "us-east-1",
                )
                upload_url = s3_client.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": settings.AWS_S3_BUCKET,
                        "Key": file_key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=expires_in,
                )
                download_url = f"https://{settings.AWS_S3_BUCKET}.s3.amazonaws.com/{file_key}"
                return {
                    "upload_url": upload_url,
                    "file_key": file_key,
                    "download_url": download_url,
                    "expires_in": expires_in,
                    "method": "PUT",
                }
            except Exception:
                pass  # Fallback to local storage

        # Local storage signed token upload URL
        exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        token_payload = {
            "file_key": file_key,
            "content_type": content_type,
            "is_public": is_public,
            "exp": exp,
        }
        token = jwt.encode(token_payload, self.signing_secret, algorithm=self.algorithm)

        base_url = settings.BASE_URL.rstrip("/")
        upload_url = f"{base_url}/storage/upload?token={token}"
        download_url = f"{base_url}/storage/files/{file_key}"

        return {
            "upload_url": upload_url,
            "file_key": file_key,
            "download_url": download_url,
            "expires_in": expires_in,
            "method": "PUT",
        }

    def verify_upload_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            payload = jwt.decode(token, self.signing_secret, algorithms=[self.algorithm])
            return payload
        except Exception:
            return None

    def generate_signed_read_url(self, file_key: str, expires_in: int = 3600) -> str:
        if settings.STORAGE_BACKEND == "s3" and settings.AWS_S3_BUCKET:
            try:
                import boto3
                s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
                    region_name=settings.AWS_REGION or "us-east-1",
                )
                return s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": settings.AWS_S3_BUCKET, "Key": file_key},
                    ExpiresIn=expires_in,
                )
            except Exception:
                pass

        exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        token_payload = {
            "file_key": file_key,
            "exp": exp,
            "action": "read",
        }
        token = jwt.encode(token_payload, self.signing_secret, algorithm=self.algorithm)
        base_url = settings.BASE_URL.rstrip("/")
        return f"{base_url}/storage/files/{file_key}?token={token}"

    def verify_read_token(self, file_key: str, token: str) -> bool:
        try:
            payload = jwt.decode(token, self.signing_secret, algorithms=[self.algorithm])
            return payload.get("file_key") == file_key
        except Exception:
            return False

    def get_file_path(self, file_key: str) -> Path:
        safe_key = os.path.normpath(file_key).lstrip(r"\/")
        full_path = (self.storage_dir / safe_key).resolve()
        # Prevent directory traversal
        if not str(full_path).startswith(str(self.storage_dir.resolve())):
            raise ValueError("Invalid file key path")
        return full_path

    def save_bytes(self, file_key: str, data: bytes) -> str:
        target_path = self.get_file_path(file_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(data)
        base_url = settings.BASE_URL.rstrip("/")
        return f"{base_url}/storage/files/{file_key}"

    def read_bytes(self, file_key: str) -> bytes:
        target_path = self.get_file_path(file_key)
        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {file_key}")
        with open(target_path, "rb") as f:
            return f.read()

    def generate_thumbnail(
        self, image_bytes: bytes, max_size: Tuple[int, int] = (300, 300)
    ) -> Tuple[bytes, str]:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            # Handle EXIF orientation if available
            try:
                from PIL import ImageOps
                image = ImageOps.exif_transpose(image)
            except Exception:
                pass

            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            output_format = "JPEG"
            mime_type = "image/jpeg"

            if image.mode in ("RGBA", "LA", "P"):
                # Convert with white background for transparent images if saving JPEG
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                background.paste(image, mask=image.split()[-1])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            buffer = io.BytesIO()
            image.save(buffer, format=output_format, quality=85, optimize=True)
            return buffer.getvalue(), mime_type
        except Exception as e:
            raise ValueError(f"Failed to generate thumbnail: {str(e)}")

    def process_and_save_image(
        self,
        file_key: str,
        image_bytes: bytes,
        generate_thumb: bool = True,
        thumb_size: Tuple[int, int] = (300, 300),
    ) -> Dict[str, Any]:
        # Save original
        file_url = self.save_bytes(file_key, image_bytes)
        thumbnail_key = None
        thumbnail_url = None

        if generate_thumb:
            try:
                thumb_bytes, _ = self.generate_thumbnail(image_bytes, max_size=thumb_size)
                folder, name = os.path.split(file_key)
                thumbnail_key = f"{folder}/thumb_{name}"
                thumbnail_url = self.save_bytes(thumbnail_key, thumb_bytes)
            except Exception:
                # If thumbnail generation fails, fallback gracefully
                thumbnail_key = None
                thumbnail_url = None

        return {
            "file_key": file_key,
            "file_url": file_url,
            "thumbnail_key": thumbnail_key,
            "thumbnail_url": thumbnail_url,
            "file_size_bytes": len(image_bytes),
        }


storage_service = StorageService()
