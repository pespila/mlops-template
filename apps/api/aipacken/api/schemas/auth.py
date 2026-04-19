from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    role: str
    full_name: str | None = None
    is_active: bool


class SessionRead(BaseModel):
    user: UserRead
