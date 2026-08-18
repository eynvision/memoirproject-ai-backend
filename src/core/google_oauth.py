"""
Google OAuth
------------
Google authentication + Google token/security handling.

Flow:
  1. Client hits GET /auth/google/login  -> redirected to Google's consent screen.
  2. Google redirects back to GET /auth/google/callback?code=...&state=...
  3. We exchange the code for Google tokens, verify the ID token, and
     upsert a local user record, then issue our own access/refresh JWTs
     (so the rest of the app only ever deals with our own tokens).

`state` is a CSRF-protection nonce: we generate it before redirecting and
require it to match on callback.
"""
import secrets
from typing import Any

import httpx
from authlib.jose import JsonWebToken
from authlib.jose.errors import JoseError

from app.core.config import get_settings

settings = get_settings()

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_ENDPOINT = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUER = {"https://accounts.google.com", "accounts.google.com"}


class GoogleOAuthError(Exception):
    """Raised for any failure in the Google OAuth exchange or token verification."""


def generate_state() -> str:
    """Generate a random CSRF-protection state value to store in the user's session."""
    return secrets.token_urlsafe(32)


def build_authorization_url(state: str) -> str:
    """Build the URL to redirect the user to for Google's consent screen."""
    settings = get_settings()
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    query = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items())
    return f"{GOOGLE_AUTH_ENDPOINT}?{query}"


async def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    """Exchange an authorization code for Google access/id/refresh tokens."""
    settings = get_settings()
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(GOOGLE_TOKEN_ENDPOINT, data=data)

    if response.status_code != 200:
        raise GoogleOAuthError(f"Token exchange failed: {response.text}")

    return response.json()


async def _fetch_google_jwks() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(GOOGLE_JWKS_ENDPOINT)
    response.raise_for_status()
    return response.json()


async def verify_id_token(id_token: str) -> dict[str, Any]:
    """
    Verify a Google-issued ID token's signature, issuer, audience, and
    expiry, and return its decoded claims (sub, email, email_verified, ...).
    """
    settings = get_settings()
    jwks = await _fetch_google_jwks()
    jwt_lib = JsonWebToken(["RS256"])

    try:
        claims = jwt_lib.decode(id_token, jwks)
        claims.validate()
    except JoseError as exc:
        raise GoogleOAuthError(f"Invalid Google ID token: {exc}") from exc

    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise GoogleOAuthError("ID token audience mismatch")

    if claims.get("iss") not in GOOGLE_ISSUER:
        raise GoogleOAuthError("ID token issuer mismatch")

    if not claims.get("email_verified", False):
        raise GoogleOAuthError("Google account email is not verified")

    return dict(claims)

