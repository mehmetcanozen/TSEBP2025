import hashlib
import os
import shutil
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.config import settings
from core.dependencies import get_current_user, get_admin_user
from database.db import get_db
from database import models
from database.schemas import (
    ModelVersionResponse, LatestModelResponse,
    ModelVersionCreate, MessageResponse,
)

router = APIRouter(prefix="/model", tags=["Model Güncelleme"])

MODELS_DIR = Path(settings.MODELS_DIR)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def _compute_checksum(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ──────────────────────────────────────────────
# Güncel Sürümü Sorgula
# ──────────────────────────────────────────────
@router.get("/latest", response_model=LatestModelResponse)
def get_latest_version(
    platform: str = Query(default="all", description="windows | android | ios | all"),
    current_version: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    # Platforma uygun aktif modeli bul
    query = db.query(models.ModelVersion).filter(models.ModelVersion.is_active == True)
    platform_filter = query.filter(
        models.ModelVersion.platform.in_([platform, "all"])
    ).order_by(models.ModelVersion.created_at.desc()).first()

    if not platform_filter:
        raise HTTPException(status_code=404, detail="Aktif model bulunamadı")

    has_update = (current_version != platform_filter.version) if current_version else True

    download_url = (
        f"/model/download/{platform_filter.id}" if has_update else None
    )

    return LatestModelResponse(
        has_update=has_update,
        current_version=current_version,
        latest_version=platform_filter.version,
        download_url=download_url,
        file_size_mb=platform_filter.file_size_mb,
        checksum=platform_filter.checksum,
    )


# ──────────────────────────────────────────────
# Model İndir
# ──────────────────────────────────────────────
@router.get("/download/{version_id}")
def download_model(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    version = db.query(models.ModelVersion).filter(
        models.ModelVersion.id == version_id,
        models.ModelVersion.is_active == True,
    ).first()

    if not version:
        raise HTTPException(status_code=404, detail="Model bulunamadı")

    file_path = Path(version.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Model dosyası sunucuda bulunamadı")

    # İndirme logu
    db.add(models.ModelDownloadLog(
        user_id=current_user.id,
        model_version_id=version.id,
    ))
    db.commit()

    return FileResponse(
        path=str(file_path),
        filename=f"audio_model_v{version.version}.onnx",
        media_type="application/octet-stream",
    )


# ──────────────────────────────────────────────
# Model Yükle (sadece admin)
# ──────────────────────────────────────────────
@router.post("/upload", response_model=ModelVersionResponse, status_code=201)
async def upload_model(
    version: str = Form(...),
    description: Optional[str] = Form(default=None),
    platform: str = Form(default="all"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_admin_user),
):
    if db.query(models.ModelVersion).filter(models.ModelVersion.version == version).first():
        raise HTTPException(status_code=400, detail=f"v{version} zaten mevcut")

    dest_path = MODELS_DIR / f"model_v{version}_{platform}.onnx"

    async with aiofiles.open(dest_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):  # 1MB chunk
            await out.write(chunk)

    file_size_mb = round(dest_path.stat().st_size / (1024 * 1024), 2)
    checksum = _compute_checksum(dest_path)

    db_version = models.ModelVersion(
        version=version,
        description=description,
        file_path=str(dest_path),
        file_size_mb=file_size_mb,
        checksum=checksum,
        platform=platform,
    )
    db.add(db_version)
    db.commit()
    db.refresh(db_version)
    return db_version


# ──────────────────────────────────────────────
# Tüm Versiyonları Listele (admin)
# ──────────────────────────────────────────────
@router.get("/versions", response_model=list[ModelVersionResponse])
def list_versions(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_admin_user),
):
    return db.query(models.ModelVersion).order_by(models.ModelVersion.created_at.desc()).all()


# ──────────────────────────────────────────────
# Versiyon Aktif/Pasif Yap (admin)
# ──────────────────────────────────────────────
@router.patch("/versions/{version_id}/toggle", response_model=MessageResponse)
def toggle_version(
    version_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_admin_user),
):
    version = db.query(models.ModelVersion).filter(models.ModelVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Versiyon bulunamadı")

    version.is_active = not version.is_active
    db.commit()
    state = "aktif" if version.is_active else "pasif"
    return {"message": f"v{version.version} {state} yapıldı"}
