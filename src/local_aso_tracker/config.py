"""Local configuration and storage path handling."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_DATA_DIR = Path("~/.local-aso-tracker").expanduser()
SUPPORTED_DEVICES = {"iphone": "software", "ipad": "iPadSoftware"}


class Settings(BaseModel):
    """Validated runtime settings persisted as TOML."""

    model_config = ConfigDict(extra="ignore")

    request_timeout: float = Field(default=15.0, gt=0)
    retry_count: int = Field(default=3, ge=0, le=10)
    request_delay: float = Field(default=1.0, ge=0)
    concurrency: int = Field(default=2, ge=1, le=10)
    result_limit: int = Field(default=200, ge=1, le=200)
    default_countries: list[str] = Field(default_factory=lambda: ["us", "fr", "gb", "ca", "au"])
    default_app_id: int = 6771773264

    @field_validator("default_countries")
    @classmethod
    def validate_countries(cls, values: list[str]) -> list[str]:
        return [validate_country_code(value) for value in values]


def validate_country_code(value: str) -> str:
    """Normalize and validate an ISO-like two-letter storefront code."""

    normalized = value.strip().lower()
    if len(normalized) != 2 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError("country code must contain exactly two ASCII letters")
    return normalized


def validate_device(value: str) -> str:
    """Normalize a supported public iTunes software result entity."""

    normalized = value.strip().lower()
    if normalized not in SUPPORTED_DEVICES:
        raise ValueError("device must be 'iphone' or 'ipad'")
    return normalized


def data_dir() -> Path:
    """Return the environment-overridable application data directory."""

    override = os.getenv("ASO_DATA_DIR")
    return Path(override).expanduser().resolve() if override else DEFAULT_DATA_DIR


def config_path() -> Path:
    return data_dir() / "config.toml"


def database_path() -> Path:
    return data_dir() / "aso.db"


def log_path() -> Path:
    return data_dir() / "logs" / "aso.log"


def load_settings() -> Settings:
    """Load settings, using defaults when initialization has not run yet."""

    path = config_path()
    if not path.exists():
        return Settings()
    with path.open("rb") as handle:
        return Settings.model_validate(tomllib.load(handle))


def write_default_config(*, overwrite: bool = False) -> Path:
    """Write the human-editable default configuration file."""

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return path
    path.write_text(
        """# Local ASO Tracker configuration (no secrets are required)
request_timeout = 15.0
retry_count = 3
request_delay = 1.0
concurrency = 2
result_limit = 200
default_countries = ["us", "fr", "gb", "ca", "au"]
default_app_id = 6771773264
""",
        encoding="utf-8",
    )
    return path
