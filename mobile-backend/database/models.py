from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, Float
)
from sqlalchemy.orm import relationship

from database.db import Base


def _now():
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────
# Kullanıcı
# ──────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    email      = Column(String(255), unique=True, index=True, nullable=False)
    username   = Column(String(100), unique=True, index=True, nullable=False)
    password   = Column(String(255), nullable=False)
    full_name  = Column(String(255), nullable=True)
    bio        = Column(Text, nullable=True)
    photo_uri  = Column(String(500), nullable=True)
    is_active  = Column(Boolean, default=True)
    is_admin   = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    # İlişkiler
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    history        = relationship("ProcessingHistory", back_populates="user", cascade="all, delete-orphan")
    devices        = relationship("UserDevice", back_populates="user", cascade="all, delete-orphan")


# ──────────────────────────────────────────────
# Refresh Token (logout için takip)
# ──────────────────────────────────────────────

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    token      = Column(Text, unique=True, nullable=False, index=True)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="refresh_tokens")


# ──────────────────────────────────────────────
# Model Versiyonları
# ──────────────────────────────────────────────

class ModelVersion(Base):
    __tablename__ = "model_versions"

    id           = Column(Integer, primary_key=True, index=True)
    version      = Column(String(50), unique=True, nullable=False)   # örn: "1.2.0"
    description  = Column(Text, nullable=True)
    file_path    = Column(String(500), nullable=False)               # S3 key veya local path
    file_size_mb = Column(Float, nullable=True)
    checksum     = Column(String(64), nullable=True)                 # SHA-256
    is_active    = Column(Boolean, default=True)                     # Yayında mı?
    platform     = Column(String(50), default="all")                 # "all", "windows", "android", "ios"
    created_at   = Column(DateTime(timezone=True), default=_now)

    download_logs = relationship("ModelDownloadLog", back_populates="model_version")


# ──────────────────────────────────────────────
# Model İndirme Logu
# ──────────────────────────────────────────────

class ModelDownloadLog(Base):
    __tablename__ = "model_download_logs"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), nullable=False)
    platform         = Column(String(50), nullable=True)   # "windows", "android", "ios"
    downloaded_at    = Column(DateTime(timezone=True), default=_now)

    model_version = relationship("ModelVersion", back_populates="download_logs")


# ──────────────────────────────────────────────
# İşlem Geçmişi
# ──────────────────────────────────────────────

class ProcessingHistory(Base):
    __tablename__ = "processing_history"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_name        = Column(String(255), nullable=True)
    duration_seconds = Column(Float, nullable=True)     # Ses süresi
    model_version    = Column(String(50), nullable=True)
    platform         = Column(String(50), nullable=True)
    status           = Column(String(20), default="success")  # "success", "failed"
    error_message    = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="history")


# ──────────────────────────────────────────────
# Cihaz Kaydı (push notification / analitik için)
# ──────────────────────────────────────────────

class UserDevice(Base):
    __tablename__ = "user_devices"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id    = Column(String(255), nullable=False)
    platform     = Column(String(50), nullable=False)   # "windows", "android", "ios"
    app_version  = Column(String(50), nullable=True)
    registered_at = Column(DateTime(timezone=True), default=_now)
    last_seen_at  = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="devices")
