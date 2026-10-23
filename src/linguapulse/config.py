"""User preferences stored in the configuration directory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import models, paths, store

DEFAULT_SOURCE_LANG = "en"
DEFAULT_TARGET_LANG = "ar"


@dataclass
class Config:
    """The preferences that steer the CLI and the scheduler."""

    source_lang: str = DEFAULT_SOURCE_LANG
    target_lang: str = DEFAULT_TARGET_LANG
    notify_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "notify_enabled": self.notify_enabled,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "Config":
        """Build a configuration from a raw document, ignoring broken values."""
        settings = cls()
        if not isinstance(raw, Mapping):
            return settings
        source = raw.get("source_lang")
        target = raw.get("target_lang")
        if isinstance(source, str) and source.strip() in models.SUPPORTED_LANGUAGES:
            settings.source_lang = source.strip()
        if isinstance(target, str) and target.strip() in models.SUPPORTED_LANGUAGES:
            settings.target_lang = target.strip()
        if "notify_enabled" in raw:
            settings.notify_enabled = bool(raw["notify_enabled"])
        return settings


def load_config() -> Config:
    """Load the configuration, falling back to the defaults."""
    try:
        raw = store.read_json(paths.config_path(), {})
    except ValueError:
        return Config()
    return Config.from_dict(raw)


def save_config(settings: Config) -> None:
    """Write the configuration to disk atomically."""
    store.write_json(paths.config_path(), settings.to_dict())
