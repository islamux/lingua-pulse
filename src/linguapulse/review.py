"""Card selection and terminal rendering."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from . import models, scheduler, text


def _due_entries(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[tuple[datetime, str, models.Card]]:
    """Return the due time, the id and the card of every card, the earliest due first.

    The card id breaks the tie, so two cards that are due at the same moment always
    keep the same order.
    """
    entries = [
        (scheduler.occurrence_due(card, states.get(card_id), moment), card_id, card)
        for card_id, card in cards.items()
    ]
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return entries


def due_cards(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[models.Card]:
    """Return the cards that are due, the most overdue one first."""
    return [
        card for due, _, card in _due_entries(cards, states, moment) if due <= moment
    ]


def current_card(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> models.Card | None:
    """Return the card to review next, or None when nothing is due."""
    for due, _, card in _due_entries(cards, states, moment):
        if due <= moment:
            return card
    return None


def next_due(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> tuple[models.Card, datetime] | None:
    """Return the soonest card that is not due yet."""
    for due, _, card in _due_entries(cards, states, moment):
        if due > moment:
            return card, due
    return None


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
    identifier = text.isolate(card.id)
    heading = identifier
    if index is not None and total is not None:
        heading = f"{index} of {total}  ({identifier})"
    if card.tags:
        tags = ", ".join(text.isolate(tag) for tag in card.tags)
        heading = f"{heading}  [{tags}]"
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
