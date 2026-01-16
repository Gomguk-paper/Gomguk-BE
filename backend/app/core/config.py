import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import PostgresDsn, AnyUrl, BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    # BACKEND_CORS_ORIGINS: Annotated[
    #     list[AnyUrl] | str, BeforeValidator(parse_cors)
    # ] = []
    #
    # def all_cors_origins(self) -> list[str]:
    #     return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
    #         self.FRONTEND_HOST
    #     ]

    PROJECT_NAME: str
    DATABASE_URL: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    SECRET_KEY: str


settings = Settings()
