import uuid
from sqlalchemy import Column, String, DateTime, func
from app.db.database import Base, SessionLocal


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column("password_hash", String, nullable=True)
    provider = Column("provider", String, nullable=False, default="email")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def hashed_password(self) -> str | None:
        return self.password_hash

    @hashed_password.setter
    def hashed_password(self, value: str | None) -> None:
        self.password_hash = value

    @property
    def is_oauth_user(self) -> bool:
        return self.provider == "google" or self.provider == "oauth"

    @is_oauth_user.setter
    def is_oauth_user(self, value: bool) -> None:
        self.provider = "google" if value else "email"



class UserRepository:
    def get_by_id(self, user_id: str | int) -> User | None:
        with SessionLocal() as db:
            return db.query(User).filter(User.id == str(user_id)).first()

    def get_by_email(self, email: str) -> User | None:
        with SessionLocal() as db:
            return db.query(User).filter(User.email == email).first()

    def create(
        self,
        email: str,
        hashed_password: str | None = None,
        is_oauth_user: bool = False,
        name: str | None = None
    ) -> User:
        user_name = name if name and name.strip() else email.split("@")[0]
        with SessionLocal() as db:
            user = User(
                email=email,
                name=user_name,
                password_hash=hashed_password,
                provider="google" if is_oauth_user else "email"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            # Ensure the object's attributes remain available after session closes
            db.expunge(user)
            return user



user_repository = UserRepository()

