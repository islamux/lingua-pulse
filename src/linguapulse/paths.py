"""Filesystem locations that follow the XDG base directory specification."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "linguapulse"
ENV_HOME = "LINGUAPULSE_HOME"


def _override_root() -> Path | None:
    raw = os.environ.get(ENV_HOME)
    return Path(raw).expanduser() if raw else None


def _xdg(variable: str, fallback: str) -> Path:
    raw = os.environ.get(variable)
    base = Path(raw).expanduser() if raw else Path.home() / fallback
    return base / APP_NAME


def data_dir() -> Path:
    """Return the directory that holds the deck, the state and the history."""
    root = _override_root()
    if root is not None:
        return root / "data"
    return _xdg("XDG_DATA_HOME", ".local/share")


def config_dir() -> Path:
    """Return the directory that holds the configuration file."""
    root = _override_root()
    if root is not None:
        return root / "config"
    return _xdg("XDG_CONFIG_HOME", ".config")


def state_dir() -> Path:
    """Return the directory that holds the lock and the process id file."""
    root = _override_root()
    if root is not None:
        return root / "state"
    return _xdg("XDG_STATE_HOME", ".local/state")


def deck_path() -> Path:
    """Return the path of the deck file."""
    return data_dir() / "deck.json"


def state_path() -> Path:
    """Return the path of the scheduling state file."""
    return data_dir() / "state.json"


def history_path() -> Path:
    """Return the path of the review history file."""
    return data_dir() / "history.jsonl"


def config_path() -> Path:
    """Return the path of the configuration file."""
    return config_dir() / "config.json"


def lock_path() -> Path:
    """Return the path of the scheduler lock file."""
    return state_dir() / "daemon.lock"


def pid_path() -> Path:
    """Return the path of the scheduler process id file."""
    return state_dir() / "daemon.pid"


def ensure_dirs() -> None:
    """Create the data, config and state directories when they are missing."""
    for directory in (data_dir(), config_dir(), state_dir()):
        directory.mkdir(parents=True, exist_ok=True)
