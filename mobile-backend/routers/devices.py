from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from database.db import get_db
from database import models
from database.schemas import DeviceRegisterRequest, MessageResponse

router = APIRouter(prefix="/devices", tags=["Cihaz"])


@router.post("/register", response_model=MessageResponse)
def register_device(
    body: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    existing = db.query(models.UserDevice).filter(
        models.UserDevice.user_id == current_user.id,
        models.UserDevice.device_id == body.device_id,
    ).first()

    if existing:
        existing.app_version = body.app_version
        existing.last_seen_at = datetime.now(timezone.utc)
    else:
        db.add(models.UserDevice(
            user_id=current_user.id,
            device_id=body.device_id,
            platform=body.platform,
            app_version=body.app_version,
        ))

    db.commit()
    return {"message": "Cihaz kaydedildi"}
