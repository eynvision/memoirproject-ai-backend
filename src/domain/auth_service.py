"""
@file auth_service.py
@description Business logic service handling user registration, Supabase Auth synchronization,
credential authentication, and login activity tracking, fully decoupled from direct 
infrastructure and database connection calls.
"""

import logging
from datetime import datetime, timezone
from fastapi import HTTPException, status
from src.integrations import auth_repository
from src.schemas.auth import UserRegisterRequest, UserLoginRequest
from src.integrations.supabase_client import supabase

logger = logging.getLogger(__name__)


class AuthService:
    """
    Handles user authentication workflows, coordinating between external auth 
    credentials and internal application profile records through repository adapters.
    """

    @classmethod
    def register_user(cls, payload: UserRegisterRequest) -> dict:
        email = payload.email
        password = payload.password
        full_name = payload.full_name

        try:
            response = auth_repository.auth_sign_up(
                email=email,
                password=password,
                full_name=full_name
            )
            
            user = getattr(response, "user", None)
            session = getattr(response, "session", None)

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="We couldn't complete your registration. Please try again."
                )

            # CRITICAL FIX: Catch the Supabase "Fake Success" for duplicate emails
            # If a user already exists, Supabase returns a user object but empties their identities array
            if hasattr(user, "identities") and user.identities is not None:
                if len(user.identities) == 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="An account with this email already exists. Please login instead."
                    )

            user_id = str(user.id)
            
            # ... (Keep the rest of your normal immediate login session code the same)
            logger.info(f"User successfully registered and authenticated: {email}")
            return {
                "success": True,
                "message": "Registration successful.",
                "requires_confirmation": False,
                "access_token": session.access_token if session else None,
                "refresh_token": session.refresh_token if session else None,
                "user": {
                    "id": user_id,
                    "email": email,
                    "full_name": full_name
                }
            }

        except Exception as e:
            # If it's our clean HTTPException from above, re-raise it so the frontend sees it
            if isinstance(e, HTTPException):
                raise e
            
            error_msg = str(e).lower()
            
            # Catch duplicate email errors and return 409 Conflict
            if "already registered" in error_msg or "already exists" in error_msg or "user already registered" in error_msg:
                logger.warning(f"Registration attempt failed - email already in use: {email}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists. Please login instead."
                )
            
            # Catch actual invalid formats
            if "invalid email" in error_msg:
                logger.warning(f"Registration failed due to invalid email address: {email}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid email address format. Please check for typos."
                )

            # Catch Supabase SMTP / rate limit issues separately
            if "error sending confirmation email" in error_msg or "rate limit" in error_msg:
                logger.error(f"Supabase email delivery failure for {email}: {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="We are experiencing high traffic and couldn't send your confirmation email. Please try again in a few minutes."
                )
                
            # Catch weak passwords
            if "password should be" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Your password is too weak. Please use at least 6 characters."
                )

            # Log the technical error securely on the backend, but show a clean message to the user
            logger.error(f"Unexpected Supabase auth registration error for {email}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create your account right now. Please check your details and try again."
            )
            
    @staticmethod
    def login_user(payload: UserLoginRequest) -> dict:
        """
        Authenticates an existing user via Supabase Auth password verification, 
        updates their last login timestamp in the database, and returns an active access token.

        Args:
            payload (UserLoginRequest): The login request payload containing email and password.

        Returns:
            dict: A dictionary containing the user ID, email, access token, and success message.

        Raises:
            HTTPException (401): If credentials are invalid, authentication fails, or session tokens are missing.
        """
        try:
            response = auth_repository.auth_sign_in(payload.email, payload.password)
        except Exception as e:
            logger.warning(f"Login failed for {payload.email}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password. Please check your credentials and try again."
            )

        if not response or not response.session or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password. Please check your credentials and try again."
            )

        user_id = response.user.id
        access_token = response.session.access_token

        # Update last_login_at timestamp in user_account table via repository (non-blocking)
        try:
            auth_repository.update_last_login(user_id, datetime.now(timezone.utc).isoformat())
        except Exception as db_err:
            logger.warning("Failed to update last login timestamp: %s", str(db_err))

        return {
            "user_id": user_id,
            "email": response.user.email,
            "access_token": access_token,
            "message": "Login successful."
        }