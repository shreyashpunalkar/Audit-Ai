"""Application configuration using Pydantic Settings."""
from __future__ import annotations
from functools import lru_cache
from typing import List
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings
import os


class Settings(BaseSettings):
    # App
    app_name: str = "AI Checksheet to JSON Converter"
    app_env: str = "development"
    secret_key: str = "change_me"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://auditai:auditai123@localhost:5432/auditai_db"

    # AI — Google Gemini / NVIDIA NIM / Groq
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_model: str = "gemini-1.5-pro"

    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "minimaxai/minimax-m2.7"

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    mock_ai: bool = False

    # CORS
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # Upload
    max_upload_size_mb: int = 25
    upload_dir: str = "./uploads"

    # Allowed mime types
    allowed_extensions: List[str] = [
        ".xlsx", ".xls", ".pdf", ".docx"
    ]

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    def ensure_upload_dir(self):
        os.makedirs(self.upload_dir, exist_ok=True)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"   # silently ignore unknown env vars like old GEMINI_API_KEY


    @property
    def ai_configured(self) -> bool:
        return bool(self.groq_api_key) or bool(self.gemini_api_key) or bool(self.nvidia_api_key)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
