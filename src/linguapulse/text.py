"""Unicode helpers for rendering mixed direction text in a terminal."""

from __future__ import annotations

import unicodedata

LRI = "⁦"
RLI = "⁧"
FSI = "⁨"
PDI = "⁩"

_ZERO_WIDTH_CATEGORIES = frozenset({"Mn", "Me", "Cf"})


def normalize(text: str) -> str:
    """Return the text in Unicode Normalization Form C."""
    return unicodedata.normalize("NFC", text)


def char_width(ch: str) -> int:
    """Return the number of terminal columns a single character occupies."""
    if unicodedata.category(ch) in _ZERO_WIDTH_CATEGORIES:
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def display_width(text: str) -> int:
    """Return the number of terminal columns a string occupies."""
    return sum(char_width(ch) for ch in text)


def pad(text: str, width: int, align: str = "left") -> str:
    """Pad the text to the given number of terminal columns."""
    gap = width - display_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def contains_rtl(text: str) -> bool:
    """Return True when the text holds characters with a right to left direction."""
    return any(unicodedata.bidirectional(ch) in ("R", "AL", "AN") for ch in text)


def isolate(text: str) -> str:
    """Wrap right to left text in directional isolates.

    Text without right to left characters is returned unchanged, so terminals
    without bidirectional support are not disturbed by the markers.
    """
    if not text or not contains_rtl(text):
        return text
    return RLI + text + PDI


def strip_isolates(text: str) -> str:
    """Remove every directional isolate marker from the text."""
    for marker in (LRI, RLI, FSI, PDI):
        text = text.replace(marker, "")
    return text
