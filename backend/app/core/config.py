from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    ACCESS_TOKEN_EXPIRE_MINUTES: int
    FRONTEND_HOST: str

    def all_cors_origins(self) -> list[str]:
        return [self.FRONTEND_HOST]

    PROJECT_NAME: str
    DATABASE_URL: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    SECRET_KEY: str
    ALGORITHM: str
    BACKEND_PUBLIC_URL: str


settings = Settings()
