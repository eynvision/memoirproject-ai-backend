from fastapi import APIRouter, Depends
from app.api.deps import CurrentUser, get_current_user
from app.models.user_account import UserAccount
from app.schemas.user import UserRead, OnboardingData
from app.api.deps import get_current_user, require_active_subscription
from app.services.user_service import save_onboarding
from app.db.session import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserRead)
def read_me(current: CurrentUser = Depends(get_current_user)):
    return current.user            # the UserAccount is now at .user


# here we are checking if the user has an active subscription. If not, we will return a 402 Payment Required error. This is useful for endpoints that require a subscription to access, like creating a memoir.
@router.get("/premium-check", response_model=UserRead)
def premium_check(current: CurrentUser = Depends(require_active_subscription)):
    return current.user



@router.post("/onboarding", response_model=UserRead)
def submit_onboarding(
    data: OnboardingData,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updated = save_onboarding(db, current.user, data)
    return updated