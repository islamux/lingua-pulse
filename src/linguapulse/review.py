"""Card selection and terminal rendering."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from . import models, scheduler, text


def due_cards(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[models.Card]:
    """Return the cards that are due, the most overdue one first."""
    entries: list[tuple[datetime, str, models.Card]] = []
    for card_id in sorted(cards):
        card = cards[card_id]
        state = states.get(card_id)
        due = scheduler.occurrence_due(card, state, moment)
        if due <= moment:
            entries.append((due, card_id, card))
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return [entry[2] for entry in entries]


def current_card(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> models.Card | None:
    """Return the card to review next, or None when nothing is due."""
    due = due_cards(cards, states, moment)
    return due[0] if due else None


def next_due(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> tuple[models.Card, datetime] | None:
    """Return the soonest card that is not due yet."""
    entries: list[tuple[datetime, str, models.Card]] = []
    for card_id in sorted(cards):
        card = cards[card_id]
        state = states.get(card_id)
        due = scheduler.occurrence_due(card, state, moment)
        if due > moment:
            entries.append((due, card_id, card))
    if not entries:
        return None
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return entries[0][2], entries[0][0]


def render_card(
    card: models.Card,
    *,
    target_lang: str | None = None,
    reveal: bool = False,
    index: int | None = None,
    total: int | None = None,
) -> str:
    """Render a card for the terminal."""
    lines: list[str] = []
    heading = card.id
    if index is not None and total is not None:
        heading = f"{index} of {total}  ({card.id})"
    if card.tags:
        heading = f"{heading}  [{', '.join(card.tags)}]"
    lines.append(heading)
    lines.append("")
    lines.append(f"{card.source_lang}: {text.isolate(card.term)}")
    if card.pinyin:
        lines.append(f"pinyin: {text.isolate(card.pinyin)}")
    if reveal:
        lines.append("")
        languages = sorted(card.translations)
        if target_lang and target_lang in card.translations:
            languages = [target_lang] + [lang for lang in languages if lang != target_lang]
        for language in languages:
            lines.append(f"{language}: {text.isolate(card.translations[language])}")
        if card.notes:
            lines.append(f"notes: {text.isolate(card.notes)}")
    return "\n".join(lines)
