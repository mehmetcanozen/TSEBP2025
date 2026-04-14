from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from database.db import engine, Base
from routers import auth, model_update, history, devices


# ──────────────────────────────────────────────
# Startup / Shutdown
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tabloları oluştur (production'da alembic kullan)
    Base.metadata.create_all(bind=engine)
    print(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} başlatıldı")
    yield
    print("👋 Uygulama kapatılıyor")


# ──────────────────────────────────────────────
# Uygulama
# ──────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## 🎵 Audio Extractor Backend

Edge deployment mimarisi için backend API.
Model işleme cihazda (edge) yapılır; bu API şu işlemleri yönetir:

- **Auth** → Kayıt, giriş, çıkış, token yenileme
- **Model** → Versiyon sorgulama ve güncelleme indirme
- **Geçmiş** → İşlem logları
- **Cihaz** → Cihaz kaydı
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ──────────────────────────────────────────────
# CORS (Windows app ve mobil için)
# ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [
        # Production'da buraya domain ekle
        # "https://yourdomain.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Router'lar
# ──────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(model_update.router)
app.include_router(history.router)
app.include_router(devices.router)


# ──────────────────────────────────────────────
# Sağlık Kontrolü
# ──────────────────────────────────────────────
@app.get("/health", tags=["Sistem"])
def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/", tags=["Sistem"])
def root():
    return {"message": f"👋 {settings.APP_NAME} çalışıyor", "docs": "/docs"}
