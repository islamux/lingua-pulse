"""Deck, card and scheduling state models."""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import store

SUPPORTED_LANGUAGES = ("ar", "en", "es", "fr", "tr", "zh")
PINYIN_TONE_MARKS = frozenset("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüńňǹḿ")


def now_utc() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    """Format a datetime as an ISO 8601 UTC timestamp."""
    return moment.astimezone(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp into an aware UTC datetime."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def safe_parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 timestamp, returning None when it cannot be parsed."""
    try:
        return parse_iso(value)
    except (TypeError, ValueError):
        return None


def _zone_from_name(name: str) -> tzinfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def local_zone() -> tzinfo:
    """Return the system timezone, resolved without hardcoding a location.

    The lookup order is the TZ environment variable, then /etc/timezone, then
    the /etc/localtime symlink target. UTC is the final fallback.
    """
    zone = _zone_from_name(os.environ.get("TZ", ""))
    if zone is not None:
        return zone
    try:
        name = Path("/etc/timezone").read_text(encoding="utf-8").strip()
    except OSError:
        name = ""
    zone = _zone_from_name(name)
    if zone is not None:
        return zone
    try:
        target = os.readlink("/etc/localtime")
    except OSError:
        target = ""
    marker = "zoneinfo/"
    if marker in target:
        zone = _zone_from_name(target.split(marker, 1)[1])
        if zone is not None:
            return zone
    return timezone.utc


def add_wall_clock(base: datetime, days: float, zone: tzinfo) -> datetime:
    """Add a wall-clock duration, keeping the same local time of day.

    A daylight-saving transition does not move the scheduled local time, so a
    one day interval stays one day apart on the wall clock.
    """
    local = base.astimezone(zone)
    naive = local.replace(tzinfo=None) + timedelta(days=days)
    return naive.replace(tzinfo=zone, fold=0).astimezone(timezone.utc)


@dataclass
class Card:
    """One vocabulary entry."""

    id: str
    term: str
    source_lang: str = "en"
    translations: dict[str, str] = field(default_factory=dict)
    pinyin: str | None = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "term": self.term,
            "source_lang": self.source_lang,
            "translations": dict(self.translations),
            "pinyin": self.pinyin,
            "notes": self.notes,
            "tags": list(self.tags),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Card":
        translations = raw.get("translations") or {}
        pinyin = raw.get("pinyin")
        return cls(
            id=str(raw.get("id", "")),
            term=str(raw.get("term", "")),
            source_lang=str(raw.get("source_lang", "en")),
            translations={str(key): str(value) for key, value in dict(translations).items()},
            pinyin=str(pinyin) if pinyin else None,
            notes=str(raw.get("notes", "")),
            tags=[str(tag) for tag in (raw.get("tags") or [])],
            created_at=str(raw.get("created_at", "")),
        )

    def has_translation(self, lang: str) -> bool:
        """Return True when the card carries a translation for the language."""
        return lang in self.translations


@dataclass
class CardState:
    """The scheduling state of one card."""

    card_id: str
    due: str
    interval_days: float = 0.0
    ease: float = 2.5
    reps: int = 0
    lapses: int = 0
    last_graded_at: str | None = None
    handled_due: str | None = None
    notifiable: bool = True

    def due_dt(self) -> datetime:
        """Return the due time as an aware UTC datetime."""
        return parse_iso(self.due)

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "due": self.due,
            "interval_days": self.interval_days,
            "ease": self.ease,
            "reps": self.reps,
            "lapses": self.lapses,
            "last_graded_at": self.last_graded_at,
            "handled_due": self.handled_due,
            "notifiable": self.notifiable,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CardState":
        return cls(
            card_id=str(raw.get("card_id", "")),
            due=str(raw.get("due", "")),
            interval_days=float(raw.get("interval_days", 0.0)),
            ease=float(raw.get("ease", 2.5)),
            reps=int(raw.get("reps", 0)),
            lapses=int(raw.get("lapses", 0)),
            last_graded_at=raw.get("last_graded_at"),
            handled_due=raw.get("handled_due"),
            notifiable=bool(raw.get("notifiable", True)),
        )


def load_deck(path: Path) -> dict[str, Card]:
    """Load the deck from disk, returning an empty deck when the file is absent."""
    raw = store.read_json(path, None)
    if raw is None:
        return {}
    cards = raw.get("cards") if isinstance(raw, Mapping) else None
    if not isinstance(cards, Mapping):
        raise ValueError(f"{path} is not a valid deck file")
    deck: dict[str, Card] = {}
    for card_id, card_raw in cards.items():
        data = dict(card_raw)
        data.setdefault("id", card_id)
        card = Card.from_dict(data)
        deck[card.id] = card
    return deck


def save_deck(path: Path, deck: Mapping[str, Card]) -> None:
    """Write the deck to disk atomically."""
    store.write_json(
        path,
        {"version": 1, "cards": {card_id: card.to_dict() for card_id, card in deck.items()}},
    )


def load_states(path: Path) -> dict[str, CardState]:
    """Load the scheduling state, returning an empty mapping when it is absent."""
    raw = store.read_json(path, None)
    if raw is None:
        return {}
    cards = raw.get("cards") if isinstance(raw, Mapping) else None
    if not isinstance(cards, Mapping):
        raise ValueError(f"{path} is not a valid state file")
    states: dict[str, CardState] = {}
    for card_id, state_raw in cards.items():
        data = dict(state_raw)
        data.setdefault("card_id", card_id)
        states[str(card_id)] = CardState.from_dict(data)
    return states


def save_states(path: Path, states: Mapping[str, CardState]) -> None:
    """Write the scheduling state to disk atomically."""
    store.write_json(
        path,
        {"version": 1, "cards": {card_id: state.to_dict() for card_id, state in states.items()}},
    )


def _check_normalized(problems: list[str], label: str, field_name: str, value: str) -> None:
    if value != unicodedata.normalize("NFC", value):
        problems.append(f"{label}: {field_name} is not in Unicode Normalization Form C")


def validate_deck_raw(raw: Mapping[str, Any]) -> list[str]:
    """Validate a raw deck document and return the list of problems found."""
    problems: list[str] = []
    if not isinstance(raw, Mapping):
        return ["deck file is not a JSON object"]
    cards = raw.get("cards")
    if not isinstance(cards, Mapping):
        return ["deck file has no 'cards' object"]
    seen: set[str] = set()
    for card_id, card_raw in cards.items():
        label = str(card_id)
        if not isinstance(card_raw, Mapping):
            problems.append(f"{label}: card entry is not an object")
            continue
        stored_id = str(card_raw.get("id", label))
        if stored_id != label:
            problems.append(f"{label}: 'id' field is {stored_id!r} but the key is {label!r}")
        if stored_id in seen:
            problems.append(f"{label}: duplicate card id")
        seen.add(stored_id)
        source_lang = str(card_raw.get("source_lang", "en"))
        if source_lang not in SUPPORTED_LANGUAGES:
            problems.append(f"{label}: unsupported source language {source_lang!r}")
        term = str(card_raw.get("term", ""))
        if not term.strip():
            problems.append(f"{label}: 'term' is empty")
        _check_normalized(problems, label, "term", term)
        translations = card_raw.get("translations")
        if not isinstance(translations, Mapping) or not translations:
            problems.append(f"{label}: 'translations' is missing or empty")
            translations = {}
        for lang, value in sorted(translations.items(), key=lambda item: str(item[0])):
            language = str(lang)
            if language not in SUPPORTED_LANGUAGES:
                problems.append(f"{label}: unsupported language {language!r}")
            translation = str(value)
            if not translation.strip():
                problems.append(f"{label}: translation for {language!r} is empty")
            _check_normalized(problems, label, f"translations.{language}", translation)
        pinyin = card_raw.get("pinyin")
        if pinyin:
            pinyin_text = str(pinyin)
            _check_normalized(problems, label, "pinyin", pinyin_text)
            if "zh" not in translations:
                problems.append(f"{label}: 'pinyin' is set but there is no 'zh' translation")
            elif not any(mark in PINYIN_TONE_MARKS for mark in pinyin_text):
                problems.append(f"{label}: pinyin {pinyin_text!r} contains no tone marks")
        if "zh" in translations and not pinyin:
            problems.append(f"{label}: 'zh' translation has no 'pinyin'")
    return problems
