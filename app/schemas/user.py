import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    # Tells Pydantic it can read straight from an ORM object's attributes,
    # not just a dict — so it can serialize a UserAccount directly.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    created_at: datetime
    last_login_at: datetime | None 

class OnboardingData(BaseModel):
    full_name: str
    subject_name: str
    subject_relationship: str