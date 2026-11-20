
from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict

from app.domain.enums.user_role import UserRole


class RegisterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    name: str
    email: EmailStr
    role: UserRole
    created_at: datetime
