from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from core.dependencies import get_current_user
from core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from database.db import get_db
from database import models
from database.schemas import (
    RegisterRequest, LoginRequest, TokenResponse,
    RefreshRequest, UserResponse, MessageResponse,
    ProfileUpdateRequest,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ──────────────────────────────────────────────
# Kayıt Ol
# ──────────────────────────────────────────────
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Bu e-posta zaten kayıtlı")
    if db.query(models.User).filter(models.User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Bu kullanıcı adı alınmış")

    user = models.User(
        email=body.email,
        username=body.username,
        password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ──────────────────────────────────────────────
# Giriş Yap
# ──────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not verify_password(body.password, user.password):
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Hesabınız devre dışı")

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    # Refresh token'ı kaydet
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(models.RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    ))
    db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ──────────────────────────────────────────────
# Token Yenile
# ──────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Geçersiz refresh token")

    db_token = db.query(models.RefreshToken).filter(
        models.RefreshToken.token == body.refresh_token,
        models.RefreshToken.is_revoked == False,
    ).first()

    if not db_token:
        raise HTTPException(status_code=401, detail="Token iptal edilmiş veya bulunamadı")

    if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token süresi dolmuş")

    user_id = int(payload.get("sub"))
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")

    # Eski token'ı iptal et (rotation)
    db_token.is_revoked = True

    new_access = create_access_token({"sub": str(user.id)})
    new_refresh = create_refresh_token({"sub": str(user.id)})

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(models.RefreshToken(
        user_id=user.id,
        token=new_refresh,
        expires_at=expires_at,
    ))
    db.commit()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


# ──────────────────────────────────────────────
# Çıkış Yap
# ──────────────────────────────────────────────
@router.post("/logout", response_model=MessageResponse)
def logout(body: RefreshRequest, db: Session = Depends(get_db)):
    db_token = db.query(models.RefreshToken).filter(
        models.RefreshToken.token == body.refresh_token
    ).first()
    if db_token:
        db_token.is_revoked = True
        db.commit()
    return {"message": "Başarıyla çıkış yapıldı"}


# ──────────────────────────────────────────────
# Benim Bilgilerim
# ──────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ──────────────────────────────────────────────
# Şifre Değiştir
# ──────────────────────────────────────────────
@router.put("/change-password", response_model=MessageResponse)
def change_password(
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    old_password = body.get("old_password")
    new_password = body.get("new_password")

    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="Eski ve yeni şifre gerekli")
    if not verify_password(old_password, current_user.password):
        raise HTTPException(status_code=400, detail="Mevcut şifre hatalı")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Yeni şifre en az 8 karakter olmalı")

    current_user.password = hash_password(new_password)

    # Tüm refresh token'ları iptal et
    db.query(models.RefreshToken).filter(
        models.RefreshToken.user_id == current_user.id
    ).update({"is_revoked": True})

    db.commit()
    return {"message": "Şifre başarıyla değiştirildi"}


# ──────────────────────────────────────────────
# Profil Güncelle
# ──────────────────────────────────────────────
@router.put("/profile", response_model=UserResponse)
def update_profile(
    body: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.bio is not None:
        current_user.bio = body.bio
    if body.photo_uri is not None:
        current_user.photo_uri = body.photo_uri

    db.commit()
    db.refresh(current_user)
    return current_user
