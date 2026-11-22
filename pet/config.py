"""Configuration persistence for the Gemini Catgirl desktop pet."""

import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
CONFIG_PATH = ROOT_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "pet_height": 300,
    "always_on_top": True,
    "auto_pose": True,
    "hide_on_fullscreen": True,
    "activity_aware": True,
    "pos_x": None,
    "pos_y": None,
    "reminders": {
        "lunch_enabled": True,
        "lunch_time": "12:00",
        "dinner_enabled": True,
        "dinner_time": "18:30",
        "sleep_enabled": True,
        "sleep_time": "23:30",
        "study_enabled": True,
        "study_interval_minutes": 45,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    """Load config from disk, falling back to defaults for missing keys."""
    if not CONFIG_PATH.exists():
        return _deep_merge(DEFAULT_CONFIG, {})
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return _deep_merge(DEFAULT_CONFIG, data)
    except (OSError, json.JSONDecodeError):
        pass
    return _deep_merge(DEFAULT_CONFIG, {})


def save_config(config: dict[str, Any]) -> None:
    """Persist config to disk."""
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
