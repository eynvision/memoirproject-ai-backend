"""
Authentication Dependency
--------------------------
get_current_user()

FastAPI dependency that extracts the bearer token from the Authorization
header, validates it, and resolves it to a User. Attach this to any
protected route via `Depends(get_current_user)`.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.jwt import TokenError, validate_token
from app.models.user import User, user_repository

_bearer_scheme = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = validate_token(credentials.credentials, expected_type="access")
    except TokenError:
        raise unauthorized

    user_id = payload.get("sub")
    if user_id is None:
        raise unauthorized

    user = user_repository.get_by_id(str(user_id))
    if user is None:
        raise unauthorized


    return user