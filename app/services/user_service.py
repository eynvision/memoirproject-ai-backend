import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_account import UserAccount

logger = logging.getLogger(__name__)


def get_or_create_user(db: Session, *, sub: str, email: str | None) -> UserAccount:
    # 1. Look for an existing row by the Supabase id (the bridge value).
    stmt = select(UserAccount).where(UserAccount.auth_provider_uid == sub)
    user = db.execute(stmt).scalar_one_or_none()

    # 2. Normally the on_auth_user_created Postgres trigger already created
    # this row in the same transaction as the Supabase signup, so reaching
    # here means the trigger didn't run (or this row predates it) — worth
    # knowing about, not just silently patching over.
    if user is None:
        logger.warning(
            "No user_account row found for auth uid=%s — creating via API fallback "
            "(expected the on_auth_user_created trigger to have done this already)",
            sub,
        )
        user = UserAccount(auth_provider_uid=sub, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # 3. Existing user → update last_login_at so we track activity.
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    logger.debug("Updated last_login_at for user_id=%s", user.id)
    return user



def save_onboarding(db: Session, user: UserAccount, data) -> UserAccount:
    user.full_name = data.full_name
    user.subject_name = data.subject_name
    user.subject_relationship = data.subject_relationship
    db.commit()
    db.refresh(user)
    return user