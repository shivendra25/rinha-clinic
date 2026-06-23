from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH)


@dataclass
class Config:
    sarvam_api_key: str = field(
        default_factory=lambda: os.environ.get("SARVAM_API_KEY", ""))

    groq_api_key: str = field(
        default_factory=lambda: os.environ.get("GROQ_API_KEY", ""))

    clinic_name: str = field(
        default_factory=lambda: os.environ.get("CLINIC_NAME", "Dr. Sharma Clinic"))

    clinic_languages: list[str] = field(init=False)

    def __post_init__(self):
        raw = os.environ.get("CLINIC_LANGUAGES", "hi,en")
        self.clinic_languages = [lang.strip() for lang in raw.split(",")]


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
