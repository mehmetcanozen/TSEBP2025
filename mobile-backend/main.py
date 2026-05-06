from contextlib import asynccontextmanager
import sys
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from database.db import Base, engine
from routers import auth, devices, history


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    print(f"[OK] {settings.APP_NAME} v{settings.APP_VERSION} started")
    yield
    print("[EXIT] Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## Audio Extractor Backend

The mobile suppression model is app-local. This backend does not serve model
files, model update metadata, or server-side suppression inference for the
mobile app.

- **Auth**: registration, login, logout, token refresh
- **History**: processing/session logs
- **Devices**: device registration
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(history.router)
app.include_router(devices.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = f"GLOBAL ERROR: {exc}\n{traceback.format_exc()}"
    print(error_msg, file=sys.stderr)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        },
    )


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/", tags=["System"])
def root():
    return {"message": f"{settings.APP_NAME} is running", "docs": "/docs"}
