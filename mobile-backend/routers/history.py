from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from database.db import get_db
from database import models
from database.schemas import (
    HistoryCreate, HistoryResponse,
    PaginatedHistory, MessageResponse,
)

router = APIRouter(prefix="/history", tags=["İşlem Geçmişi"])


# ──────────────────────────────────────────────
# Geçmiş Kaydet (uygulama tarafından çağrılır)
# ──────────────────────────────────────────────
@router.post("", response_model=HistoryResponse, status_code=201)
def save_history(
    body: HistoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = models.ProcessingHistory(
        user_id=current_user.id,
        **body.model_dump(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ──────────────────────────────────────────────
# Geçmişi Getir (sayfalı)
# ──────────────────────────────────────────────
@router.get("", response_model=PaginatedHistory)
def get_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    base = db.query(models.ProcessingHistory).filter(
        models.ProcessingHistory.user_id == current_user.id
    )
    total = base.count()
    items = (
        base.order_by(models.ProcessingHistory.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return PaginatedHistory(total=total, page=page, per_page=per_page, items=items)


# ──────────────────────────────────────────────
# Geçmişi Temizle
# ──────────────────────────────────────────────
@router.delete("", response_model=MessageResponse)
def clear_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    deleted = db.query(models.ProcessingHistory).filter(
        models.ProcessingHistory.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": f"{deleted} kayıt silindi"}
