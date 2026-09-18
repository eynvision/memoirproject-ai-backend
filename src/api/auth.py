"""
@file api/routers/auth.py
@description FastAPI router for user registration and authentication endpoints.
"""

from fastapi import APIRouter, status
from src.schemas.auth import UserRegisterRequest, UserLoginRequest # Import login request schema
from src.domain.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/signup", status_code=status.HTTP_201_CREATED)
@router.post("/signup/", status_code=status.HTTP_201_CREATED)
def register_user_endpoint(payload: UserRegisterRequest):
    """
    Registers a new user account, triggers automatic database account provisioning,
    and returns the session access token for immediate frontend use.
    """
    result = AuthService.register_user(payload)
    user_data = result.get("user", {})
    
    return {
        "success": True,
        "message": result["message"],
        "requires_confirmation": result.get("requires_confirmation", False),
        "data": {
            "user_id": user_data.get("id"),
            "email": user_data.get("email"),
            "full_name": user_data.get("full_name"),
            "access_token": result.get("access_token")
        }
    }
    
@router.post("/login", status_code=status.HTTP_200_OK)
@router.post("/login/", status_code=status.HTTP_200_OK)
def login_user_endpoint(payload: UserLoginRequest):
    """
    Authenticates an existing user and returns their session access token.
    """
    result = AuthService.login_user(payload)
    return {
        "success": True,
        "message": result.get("message", "Login successful"),
        "access_token": result["access_token"], # Directly at top level for easy frontend parsing
        "data": {
            "user_id": result.get("user_id"),
            "email": result.get("email"),
            "full_name": result.get("full_name"),
            "access_token": result["access_token"],
            "active_memoir": result.get("active_memoir") # Optional: if fetched during login
        }
    }