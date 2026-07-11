from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime, timezone


class User(BaseModel):
    name: str
    email: EmailStr
    password_hash: str
    role: str = "admin"          # currently only "admin" is used
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None


class UserSignup(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str
