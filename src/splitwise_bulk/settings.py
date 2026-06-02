from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

SETTINGS_FILE = Path.home() / ".splitwise_bulk_settings.json"


def project_root() -> Path:
    """Repo root (parent of src/), works regardless of process cwd."""
    return Path(__file__).resolve().parents[2]


def load_app_env() -> None:
    """Load .env from project root, cwd, or ~/.splitwise_bulk.env."""
    for path in (
        project_root() / ".env",
        Path.cwd() / ".env",
        Path.home() / ".splitwise_bulk.env",
    ):
        if path.is_file():
            load_dotenv(path, override=True)


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open(encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(data: dict) -> None:
    existing = load_settings()
    existing.update(data)
    with SETTINGS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(existing, handle, indent=2)


def get_saved_api_key() -> str:
    load_app_env()
    env_key = os.getenv("SPLITWISE_API_KEY", "").strip()
    if env_key:
        return env_key
    return str(load_settings().get("api_key", "")).strip()
