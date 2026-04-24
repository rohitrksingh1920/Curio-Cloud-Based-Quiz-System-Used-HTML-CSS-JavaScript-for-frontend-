


import os
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".env")
)


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME:    str = "Curio"
    APP_VERSION: str = "1.0.0"
    DEBUG:       bool = True
    ENVIRONMENT: str = "development"

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    DATABASE_URL:    str = "postgresql://postgres:1234@localhost:5432/curio_db"
    DB_POOL_SIZE:    int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # ── JWT ───────────────────────────────────────────────────────────────────
    SECRET_KEY:                  str = "supersecret-CHANGE-THIS-in-production"
    ALGORITHM:                   str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # ── CORS — include all origins that the frontend is served from ───────────
    FRONTEND_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:80",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "null",                  # file:// origin used during local dev
    ]

    # ── SMTP (OTP emails) ─────────────────────────────────────────────────────
    SMTP_HOST:         str = "smtp.gmail.com"
    SMTP_PORT:         int = 587
    SMTP_USER:         str = ""
    SMTP_PASS:         str = ""
    EMAILS_FROM_NAME:  str = "Curio"

    # ── Static files ──────────────────────────────────────────────────────────
    STATIC_BASE_URL: str = ""

    # ── Deployment (EC2 / production) ─────────────────────────────────────────
    EC2_PUBLIC_IP:  str       = ""
    ALLOWED_HOSTS:  List[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def get_all_origins(self) -> List[str]:
        """Return CORS origins, automatically adding EC2 IP if configured."""
        origins = list(self.FRONTEND_ORIGINS)
        if self.EC2_PUBLIC_IP:
            origins += [
                f"http://{self.EC2_PUBLIC_IP}",
                f"http://{self.EC2_PUBLIC_IP}:80",
                f"http://{self.EC2_PUBLIC_IP}:8000",
            ]
        return list(set(origins))


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()