from datetime import date
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required: the app fails at startup if any of these is missing from .env
    mongodb_uri: str
    mongodb_db: str
    jwt_secret: str

    # Optional: without a Groq key the chat runs in degraded mode; without Voyage, retrieval is keyword-only
    groq_api_key: str = ""
    voyage_api_key: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    today_override: date | None = None
    confirm_ttl_s: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_today() -> date:
    """The ONLY place in the project that reads the clock."""
    s = get_settings()
    return s.today_override or date.today()
