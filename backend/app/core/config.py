from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    FRONTEND_HOST: str = "http://localhost:5173"

    def all_cors_origins(self) -> list[str]:
        return [self.FRONTEND_HOST, "http://localhost:8080"]

    PROJECT_NAME: str = "Gomguk"
    DATABASE_URL: str = "postgresql://postgres:password@localhost/gomguk-db"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    SECRET_KEY: str = "secret"
    ALGORITHM: str = "HS256"
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"


settings = Settings()
