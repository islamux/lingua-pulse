import tomllib
from pathlib import Path

import pytest

from linguapulse import __version__


def test_version_is_exported():
    assert __version__ == "0.1.0"


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


def test_cli_version_flag(capsys):
    from linguapulse.cli import main

    assert main(["--version"]) == 0
    assert __version__ in capsys.readouterr().out
