"""
JWT
---
create_access_token() / create_refresh_token() / validate_token() / refresh_access_token()

Access tokens are short-lived and used to authenticate requests.
Refresh tokens are longer-lived and used only to mint new access tokens.
Both are signed with the same secret here for simplicity; in production
consider separate secrets/keys per token type.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or the wrong type."""


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: Literal["access", "refresh"],
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create a short-lived access token for the given user identifier (subject)."""
    return _create_token(
        subject,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
        extra_claims,
    )


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh token for the given user identifier (subject)."""
    return _create_token(
        subject,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
    )


def validate_token(token: str, expected_type: Literal["access", "refresh"] = "access") -> dict[str, Any]:
    """
    Decode and validate a JWT.

    Raises TokenError if the token is invalid, expired, or not of the
    expected type. Returns the decoded payload on success.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise TokenError("Invalid or expired token") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"Expected a {expected_type} token")

    return payload


def refresh_access_token(refresh_token: str) -> str:
    """Validate a refresh token and mint a brand-new access token from it."""
    payload = validate_token(refresh_token, expected_type="refresh")
    subject = payload["sub"]
    return create_access_token(subject)
