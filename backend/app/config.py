"""
Configuration settings using Pydantic Settings.
"""

from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings
from functools import lru_cache

import os

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    BACKBOARD_API_KEY: str = os.environ.get("BACKBOARD_API_KEY") or ""
    BACKBOARD_API_BASE_URL: str = "https://app.backboard.io/api"
    BACKBOARD_MAX_RETRIES: int = 2
    BACKBOARD_RETRY_BASE_SECONDS: float = 0.5
    BACKBOARD_RETRY_MAX_SECONDS: float = 4.0
    BACKBOARD_INDEXING_WAIT_SECONDS: int = 120
    BACKBOARD_INDEXING_RETRY_SECONDS: float = 2.0

    NOTE_ANALYSIS_CHUNK_MAX_CHARS: int = 1000
    NOTE_ANALYSIS_CHUNK_OVERLAP_CHARS: int = 150
    NOTE_ANALYSIS_MAX_CHUNKS: int = 200
    NOTE_ANALYSIS_PARSE_ATTEMPTS: int = 2
    NOTE_ANALYSIS_TIMEOUT_SPLIT_MAX_DEPTH: int = 2
    NOTE_ANALYSIS_TIMEOUT_SPLIT_MIN_CHARS: int = 2200
    NOTE_ANALYSIS_ENTITY_CONTEXT_MAX_ENTRIES: int = 120
    NOTE_ANALYSIS_ENTITY_CONTEXT_MAX_CHARS: int = 1000

    RAG_AUTO_COMPILE_CHANGE_THRESHOLD: int = 5
    RAG_AUTO_COMPILE_COOLDOWN_SECONDS: int = 600

    DATABASE_PATH: str = "database/world.db"
    DOCUMENTS_PATH: str = "documents"

    LLM_PROVIDER: str = "openai"
    MODEL_NAME: str = "gpt-4.1-mini"
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    DEBUG: bool = False
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

    @model_validator(mode="after")
    def resolve_relative_paths(self):
        db_path = Path(self.DATABASE_PATH)
        if not db_path.is_absolute():
            self.DATABASE_PATH = str((BASE_DIR / db_path).resolve())

        docs_path = Path(self.DOCUMENTS_PATH)
        if not docs_path.is_absolute():
            self.DOCUMENTS_PATH = str((BASE_DIR / docs_path).resolve())

        return self


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    :return: Cached Settings instance
    :rtype: Settings
    """
    return Settings()


settings = get_settings()
