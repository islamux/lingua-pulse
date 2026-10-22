"""Command line interface.

The full command set is added by later tasks. This module owns the argument
parser and the dispatch table, so every later task only registers one more
command.
"""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top level argument parser."""
    parser = argparse.ArgumentParser(
        prog="linguapulse",
        description="Terminal first vocabulary trainer with spaced repetition.",
    )
    parser.add_argument("--version", action="version", version=f"linguapulse {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface and return the process exit code.

    The parser ends the process for `--help` and for a wrong usage, that
    exit code is returned instead, so that `main` always returns a number.
    """
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as request:
        return int(request.code or 0)
    return 0
