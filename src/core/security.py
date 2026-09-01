"""
Password Security
------------------
hash_password() / verify_password()

Uses passlib's bcrypt scheme. Bcrypt automatically salts each hash, so no
separate salt storage/handling is required.
"""
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage."""
    if not plain_password:
        raise ValueError("Password must not be empty")
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        # Malformed hash or bad input — treat as verification failure,
        # never raise on user-facing auth paths.
        return False
