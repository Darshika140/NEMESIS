"""Environment-backed API configuration."""

from __future__ import annotations

import os
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".secrets" / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("NEMESIS_DATABASE_URL", "sqlite:///./nemesis.db")
    groq_model: str = os.getenv("NEMESIS_GROQ_MODEL", "openai/gpt-oss-20b")
    groq_fixer_model: str = os.getenv(
        "NEMESIS_GROQ_FIXER_MODEL", "openai/gpt-oss-20b"
    )
    groq_red_team_model: str = os.getenv(
        "NEMESIS_GROQ_RED_TEAM_MODEL", "openai/gpt-oss-120b"
    )
    ollama_model: str = os.getenv("NEMESIS_OLLAMA_MODEL", "gemma4:e2b")
    ollama_base_url: str = os.getenv(
        "NEMESIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
    ).rstrip("/")
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "NEMESIS_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )

    def require_loopback_ollama_url(self) -> str:
        parsed = urlsplit(self.ollama_base_url)
        hostname = parsed.hostname
        is_loopback = hostname == "localhost"
        if hostname:
            try:
                is_loopback = is_loopback or ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                pass
        if parsed.scheme != "http" or not is_loopback or parsed.username or parsed.password:
            raise ValueError("Local inference requires an unauthenticated loopback Ollama URL.")
        return self.ollama_base_url


settings = Settings()
