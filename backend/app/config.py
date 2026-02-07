"""
Configuration settings using Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache

import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    BACKBOARD_API_KEY: str = os.environ.get("BACKBOARD_API_KEY") or ""
    BACKBOARD_API_BASE_URL: str = "https://app.backboard.io/api"

    DATABASE_PATH: str = "database/world.db"
    DOCUMENTS_PATH: str = "documents"

    LLM_PROVIDER: str = "snowflake"  
    MODEL_NAME: str = "gpt-5.0"
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    DEBUG: bool = False
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    :return: Cached Settings instance
    :rtype: Settings
    """
    return Settings()


settings = get_settings()