from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, APIRouter, Depends
from sqlalchemy.orm import Session

from app.domain.model import User, PasswordResetToken
from app.domain.schemas import (
    userloginSchema,
    UsersignupSchema,
    UserResponseSchema,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.utils.security import hash_password, verify_password
from app.utils.token import generate_reset_token, hash_token
from app.utils.email import send_password_reset_email
from app.db.dependencies import get_db
from app.core.jwt import create_access_token
from app.core.auth import get_current_user_id


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

RESET_TOKEN_EXPIRE_MINUTES = 30


@router.post("/signup", response_model=UserResponseSchema)
def signup(data: UsersignupSchema, db: Session = Depends(get_db)):

    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    user = User(
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/login")
def login(data: userloginSchema, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    password_correct = verify_password(data.password, user.password_hash)

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    access_token = create_access_token(user.id)

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserResponseSchema)
def get_me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == payload.email).first()

    # IMPORTANT: hamesha same generic message do, chahe user exist kare ya na kare
    # (isse attacker yeh pata nahi laga sakta ke kaunse emails registered hain)
    generic_response = {"message": "Agar yeh email registered hai, reset link bhej diya gaya hai."}

    if not user:
        return generic_response

    raw_token, token_hash = generate_reset_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(reset_token)
    db.commit()

    reset_link = f"http://localhost:3000/reset-password?token={raw_token}"
    send_password_reset_email(user.email, reset_link)

    return generic_response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):

    token_hash = hash_token(payload.token)

    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used == False
    ).first()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid ya expired token")

    if reset_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expire ho chuka hai")

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    user.password_hash = hash_password(payload.new_password)

    reset_token.used = True

    db.commit()

    return {"message": "Password successfully reset ho gaya"}