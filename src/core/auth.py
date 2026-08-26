# File: backend/src/core/auth.py

import os
import logging
from typing import Optional
from uuid import UUID
from fastapi import Header, HTTPException, status
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

# Development fallback - only used when no auth is present
DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def get_current_user_id(authorization: Optional[str] = Header(None)) -> UUID:
    """
    Extract user ID from Supabase JWT token.
    Falls back to DEV_USER_ID only in local development without auth.
    """
    if not authorization:
        # In production this should raise 401, but for local dev we allow fallback
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
        jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        
        # In development without JWT secret, just decode without verification
        if not jwt_secret or os.getenv("ENVIRONMENT", "development") == "development":
            logger.debug("Development mode: Decoding token without verification")
            payload = jwt.get_unverified_claims(token)
        else:
            # Production: verify with RS256 (Supabase uses asymmetric keys)
            # For RS256, SUPABASE_JWT_SECRET should be the public key
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["RS256", "HS256"],  # Support both for flexibility
                audience="authenticated",
                options={"verify_aud": False}  # Supabase tokens may not have 'aud'
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing 'sub' claim.",
            )
        
        return UUID(user_id)
        
    except JWTError as e:
        # In development, fall back to unverified decode
        if os.getenv("ENVIRONMENT", "development") == "development":
            logger.warning(f"JWT verification failed in dev mode: {e}. Using unverified decode.")
            try:
                payload = jwt.get_unverified_claims(token)
                user_id = payload.get("sub")
                if user_id:
                    logger.info(f"Using unverified user ID: {user_id}")
                    return UUID(user_id)
            except Exception as fallback_error:
                logger.error(f"Even unverified decode failed: {fallback_error}")
        
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )
    except ValueError as e:
        logger.error(f"Invalid UUID in token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format in token.",
        )