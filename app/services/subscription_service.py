from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.subscription import Subscription


def has_active_subscription(db: Session, user_id) -> bool:
    stmt = (
        select(Subscription.id)
        .where(Subscription.payer_user_id == user_id)
        .where(Subscription.status == "active")
        .limit(1)
    )
    result = db.execute(stmt).first()
    return result is not None