# deps.py file used to handle dependencies for the FastAPI application, including authentication and database connections.
# Instead of copying and pasting complex security logic, database connections, or validation checks into every single API endpoint, we write them once in deps.py
import logging
import jwt  # used to decode, verify, and validate JWTs
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.user_service import get_or_create_user
from app.models.user_account import UserAccount
from app.core.config import settings
from app.services.subscription_service import has_active_subscription
# (Session, get_db, HTTPException, status, UserAccount are already imported)



from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CurrentUser:
    user: UserAccount      # the real row from your database (persisted)
    email_verified: bool   # read live from the token — NOT stored



# Fetches Supabase's public keys from the JWKS URL and caches them in memory.
#  It caches them in memory. It eliminates making a slow network call to Supabase for every single API request.
jwks_client = PyJWKClient(settings.supabase_jwks_url)

# Tells FastAPI to expect an "Authorization: Bearer <token>" header in each request if header is missing it will raise an error 403 forbidden.
bearer_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserAccount:
    token = credentials.credentials

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience=settings.supabase_jwt_aud,
            issuer=f"{settings.supabase_url}/auth/v1",
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        # Never log the token itself — only that verification failed and why.
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


    # turn the verified claims into a real DB user (create on first login).
    user = get_or_create_user(db, sub=payload["sub"], email=payload.get("email"))

    # read the verification flag from the token, at its real nested location
    email_verified = payload.get("user_metadata", {}).get("email_verified", False)

    logger.info("Authenticated user_id=%s email_verified=%s", user.id, email_verified)

     # bundle both — decode once, carry both
    return CurrentUser(user=user, email_verified=email_verified)  # return the real DB user row, not the dataclass


def require_verified_email(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if not current_user.email_verified:
        logger.info("Access denied (email not verified): user_id=%s", current_user.user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address to access this feature.",
        )
    return current_user # returning the CurrentUser dataclass instance, which contains both the user(UserAccount row) and the email_verified flag. This allows downstream dependencies or route handlers to access both pieces of information if needed.



# authenticated user, but this needs payment.
# This function checks if the current user has an active subscription. If not, it raises an HTTP 402 Payment Required error(when user try to access features that require a subscription, like creating memoir.). It uses the `has_active_subscription` function from the subscription service to check the user's subscription status.
def require_active_subscription(
    current_user : CurrentUser = Depends(require_verified_email),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if not has_active_subscription(db, current_user.user.id):
        logger.info("Access denied (no active subscription): user_id=%s", current_user.user.id)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="An active subscription is required to access this feature.",
        )
    return current_user





