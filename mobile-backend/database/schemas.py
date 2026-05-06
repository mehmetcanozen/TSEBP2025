from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, value: str):
        value = value.strip()
        if len(value) < 3 or len(value) > 50:
            raise ValueError("Username must be 3-50 characters")
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username can only contain letters, numbers, '_' and '-'")
        return value

    @field_validator("password")
    @classmethod
    def password_strong(cls, value: str):
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    photo_uri: Optional[str] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    photo_uri: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime


class HistoryCreate(BaseModel):
    file_name: Optional[str] = None
    duration_seconds: Optional[float] = None
    model_version: Optional[str] = None
    platform: Optional[str] = None
    status: str = "success"
    error_message: Optional[str] = None


class HistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: Optional[str]
    duration_seconds: Optional[float]
    model_version: Optional[str]
    platform: Optional[str]
    status: str
    created_at: datetime


class PaginatedHistory(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[HistoryResponse]


class DeviceRegisterRequest(BaseModel):
    device_id: str
    platform: str
    app_version: Optional[str] = None


class MessageResponse(BaseModel):
    message: str
