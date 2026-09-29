import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import settings
from app.constants.limits import NAME_MAX_LENGTH, PASSWORD_MAX_LENGTH


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    full_name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if len(value) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain at least one letter and one number")
        return value

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name is required")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    is_demo: bool = False
    created_at: datetime
