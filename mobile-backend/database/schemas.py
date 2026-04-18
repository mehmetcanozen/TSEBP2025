from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator


# ══════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        v = v.strip()
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Kullanıcı adı 3-50 karakter olmalı")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Sadece harf, rakam, _ ve - kullanılabilir")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v):
        if len(v) < 8:
            raise ValueError("Şifre en az 8 karakter olmalı")
        return v


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
    id: int
    email: str
    username: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    photo_uri: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════
# MODEL
# ══════════════════════════════════════════════

class ModelVersionResponse(BaseModel):
    version: str
    description: Optional[str]
    file_size_mb: Optional[float]
    checksum: Optional[str]
    platform: str
    created_at: datetime

    class Config:
        from_attributes = True


class ModelVersionCreate(BaseModel):
    version: str
    description: Optional[str] = None
    file_path: str
    file_size_mb: Optional[float] = None
    checksum: Optional[str] = None
    platform: str = "all"


class LatestModelResponse(BaseModel):
    has_update: bool
    current_version: Optional[str]
    latest_version: str
    download_url: Optional[str]
    file_size_mb: Optional[float]
    checksum: Optional[str]
    bundle_kind: Optional[str] = None
    filename: Optional[str] = None


# ══════════════════════════════════════════════
# GEÇMİŞ
# ══════════════════════════════════════════════

class HistoryCreate(BaseModel):
    file_name: Optional[str] = None
    duration_seconds: Optional[float] = None
    model_version: Optional[str] = None
    platform: Optional[str] = None
    status: str = "success"
    error_message: Optional[str] = None


class HistoryResponse(BaseModel):
    id: int
    file_name: Optional[str]
    duration_seconds: Optional[float]
    model_version: Optional[str]
    platform: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedHistory(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[HistoryResponse]


# ══════════════════════════════════════════════
# CİHAZ
# ══════════════════════════════════════════════

class DeviceRegisterRequest(BaseModel):
    device_id: str
    platform: str
    app_version: Optional[str] = None


# ══════════════════════════════════════════════
# GENEL
# ══════════════════════════════════════════════

class MessageResponse(BaseModel):
    message: str
