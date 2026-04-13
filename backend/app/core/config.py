
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List


_ENV_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".env")
)


class Settings(BaseSettings):
    #  Application 
    APP_NAME: str = "Curio"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    #  PostgreSQL 
    DATABASE_URL: str = "postgresql://postgres:1234@localhost:5432/curio_db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    #  JWT 
    SECRET_KEY: str = "supersecret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    #  CORS 
    FRONTEND_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:80",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "null",
    ]

    #  SMTP (OTP emails) 
    # Gmail App Password: generate at myaccount.google.com → Security → App Passwords
    # Store WITHOUT spaces, e.g.:  SMTP_PASS=cdjnzlsyvpirxcko
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "rohitrk.singh1920@gmail.com"
    SMTP_PASS: str = "cdjnzlsyvpirxcko"
    EMAILS_FROM_NAME: str = "Curio"

    #  Static files 
    STATIC_BASE_URL: str = ""

    #  AWS / Deployment 
    EC2_PUBLIC_IP: str = ""
    ALLOWED_HOSTS: List[str] = ["*"]

    # pydantic-settings v2 — replaces old inner `class Config`
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",   # silently ignore unknown .env keys
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
