from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Uygulama
    APP_NAME: str = "AudioExtractorAPI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Veritabanı
    DATABASE_URL: str

    # Güvenlik
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Model Depolama
    STORAGE_TYPE: str = "local"       # "local" veya "s3"
    MODELS_DIR: str = "./models_store"

    # AWS S3 (isteğe bağlı)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_BUCKET_NAME: Optional[str] = None
    AWS_REGION: str = "eu-central-1"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
