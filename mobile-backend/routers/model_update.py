from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core import mobile_model_bundle
from core.config import settings
from core.dependencies import get_admin_user, get_current_user
from core.mobile_model_bundle import (
    compute_checksum,
    ensure_default_android_model_version,
    prepare_download_artifact,
)
from database import models
from database.db import get_db
from database.schemas import (
    LatestModelResponse,
    MessageResponse,
    ModelVersionResponse,
)

router = APIRouter(prefix="/model", tags=["Model Update"])

MODELS_DIR = Path(settings.MODELS_DIR)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
BUNDLE_CACHE_DIR = MODELS_DIR / "android_bundles"


def _query_active_versions(db: Session, platform: str) -> list[models.ModelVersion]:
    return (
        db.query(models.ModelVersion)
        .filter(models.ModelVersion.is_active == True)
        .filter(models.ModelVersion.platform.in_([platform, "all"]))
        .order_by(models.ModelVersion.created_at.desc())
        .all()
    )


def _default_android_version_string() -> str | None:
    try:
        packaged_model = mobile_model_bundle.load_active_packaged_model("android")
    except (FileNotFoundError, KeyError):
        return None
    return mobile_model_bundle.default_android_model_version_string(packaged_model)


def _artifact_exists(version: models.ModelVersion) -> bool:
    return Path(version.file_path).exists()


def _latest_active_version(db: Session, platform: str) -> models.ModelVersion:
    candidates = _query_active_versions(db, platform)

    if platform == "android":
        default_version = _default_android_version_string()
        for version in candidates:
            if default_version and version.version == default_version:
                continue
            if _artifact_exists(version):
                return version

        default_model = ensure_default_android_model_version(db)
        if default_model and _artifact_exists(default_model):
            return default_model

    else:
        for version in candidates:
            if _artifact_exists(version):
                return version

    raise HTTPException(status_code=404, detail="No active model version was found")


@router.get("/latest", response_model=LatestModelResponse)
def get_latest_version(
    platform: str = Query(default="all", description="windows | android | ios | all"),
    current_version: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    platform = platform.strip().lower()
    version = _latest_active_version(db, platform)
    has_update = (current_version != version.version) if current_version else True

    try:
        artifact = prepare_download_artifact(version, BUNDLE_CACHE_DIR, requested_platform=platform)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    download_url = f"/model/download/{version.id}?platform={platform}" if has_update else None

    return LatestModelResponse(
        has_update=has_update,
        current_version=current_version,
        latest_version=version.version,
        download_url=download_url,
        file_size_mb=artifact.file_size_mb,
        checksum=artifact.checksum,
        bundle_kind=artifact.bundle_kind,
        filename=artifact.filename,
    )


@router.get("/download/{version_id}")
def download_model(
    version_id: int,
    platform: Optional[str] = Query(default=None, description="windows | android | ios | all"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    version = (
        db.query(models.ModelVersion)
        .filter(models.ModelVersion.id == version_id, models.ModelVersion.is_active == True)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Model version was not found")

    try:
        artifact = prepare_download_artifact(
            version,
            BUNDLE_CACHE_DIR,
            requested_platform=platform,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    db.add(
        models.ModelDownloadLog(
            user_id=current_user.id,
            model_version_id=version.id,
            platform=version.platform,
        )
    )
    db.commit()

    return FileResponse(
        path=str(artifact.path),
        filename=artifact.filename,
        media_type=artifact.media_type,
    )


@router.post("/upload", response_model=ModelVersionResponse, status_code=201)
async def upload_model(
    version: str = Form(...),
    description: Optional[str] = Form(default=None),
    platform: str = Form(default="all"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_admin_user),
):
    existing = db.query(models.ModelVersion).filter(models.ModelVersion.version == version).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Version {version} already exists")

    suffix = Path(file.filename or "artifact.bin").suffix or ".bin"
    dest_path = MODELS_DIR / f"model_v{version}_{platform}{suffix}"
    async with aiofiles.open(dest_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            await out.write(chunk)

    db_version = models.ModelVersion(
        version=version,
        description=description,
        file_path=str(dest_path),
        file_size_mb=round(dest_path.stat().st_size / (1024 * 1024), 2),
        checksum=compute_checksum(dest_path),
        platform=platform,
    )
    db.add(db_version)
    db.commit()
    db.refresh(db_version)
    return db_version


@router.get("/versions", response_model=list[ModelVersionResponse])
def list_versions(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_admin_user),
):
    return db.query(models.ModelVersion).order_by(models.ModelVersion.created_at.desc()).all()


@router.patch("/versions/{version_id}/toggle", response_model=MessageResponse)
def toggle_version(
    version_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_admin_user),
):
    version = db.query(models.ModelVersion).filter(models.ModelVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version was not found")

    version.is_active = not version.is_active
    db.commit()
    state = "active" if version.is_active else "inactive"
    return {"message": f"Version {version.version} is now {state}"}
