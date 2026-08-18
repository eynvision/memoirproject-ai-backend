from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.core.google_oauth import (
    GoogleOAuthError,
    build_authorization_url,
    exchange_code_for_tokens,
    generate_state,
    verify_id_token,
)
from app.core.jwt import TokenError, create_access_token, create_refresh_token, refresh_access_token
from app.core.security import hash_password, verify_password
from app.models.user import User, user_repository
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest) -> TokenResponse:
    if user_repository.get_by_email(body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = user_repository.create(
        email=body.email,
        hashed_password=hash_password(body.password),
        name=body.name,
    )
    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    user = user_repository.get_by_email(body.email)
    if user is None or user.hashed_password is None:
        raise invalid
    if not verify_password(body.password, user.hashed_password):
        raise invalid

    return _issue_tokens(user)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(body: RefreshRequest) -> AccessTokenResponse:
    try:
        new_access_token = refresh_access_token(body.refresh_token)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    return AccessTokenResponse(access_token=new_access_token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        is_oauth_user=current_user.is_oauth_user,
    )



# --- Google OAuth ---

@router.get("/google/login")
def google_login(request: Request) -> RedirectResponse:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env",
        )
    state = generate_state()
    request.session["oauth_state"] = state
    return RedirectResponse(build_authorization_url(state))



@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str) -> RedirectResponse:
    expected_state = request.session.pop("oauth_state", None)
    if not expected_state or state != expected_state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")

    try:
        tokens = await exchange_code_for_tokens(code)
        claims = await verify_id_token(tokens["id_token"])
    except GoogleOAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))

    email = claims["email"]
    name = claims.get("name") or claims.get("given_name")
    user = user_repository.get_by_email(email)
    if user is None:
        user = user_repository.create(email=email, name=name, is_oauth_user=True)

    issued = _issue_tokens(user)
    return RedirectResponse(
        url=f"/?access_token={issued.access_token}&refresh_token={issued.refresh_token}"
    )


