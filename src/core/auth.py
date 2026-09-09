import os
import logging
from typing import Optional
from uuid import UUID
from fastapi import Header, HTTPException, status

from src.integrations.supabase_client import get_supabase

logger = logging.getLogger(__name__)

DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def get_current_user_id(authorization: Optional[str] = Header(None)) -> UUID:
    """
    Extract user ID from Supabase JWT token.
    Uses the Supabase client's built-in verification, which automatically
    handles key rotation, ES256/RS256/HS256 algorithms, and JWKS caching.
    """
    if not authorization:
        if os.getenv("ENVIRONMENT", "development") == "development":
            logger.info("No Authorization header. Using DEV_USER_ID for local development.")
            return DEV_USER_ID
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header.",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    
    try:
        client = get_supabase()
        # The Supabase client automatically fetches/caches JWKS and verifies the signature
        user_response = client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
            )
            
        return UUID(user_response.user.id)
        
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        
        # Graceful fallback for local development if strict verification fails
        if os.getenv("ENVIRONMENT", "development") == "development":
            logger.warning("Development mode: Attempting unverified decode as fallback.")
            try:
                from jose import jwt
                payload = jwt.get_unverified_claims(token)
                user_id = payload.get("sub")
                if user_id:
                    return UUID(user_id)
            except Exception as fallback_error:
                logger.error(f"Unverified decode also failed: {fallback_error}")
                
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )