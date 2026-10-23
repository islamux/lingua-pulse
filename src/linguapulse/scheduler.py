"""The policy that decides which due occurrences become reminders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Mapping

from . import models
from .srs import REMINDER_MINUTES


@dataclass(frozen=True)
class Occurrence:
    """One scheduled review of one card."""

    card: models.Card
    due: datetime
    state: models.CardState | None

    @property
    def due_iso(self) -> str:
        """Return the due time as an ISO 8601 timestamp."""
        return self.due.isoformat()


def occurrence_due(
    card: models.Card,
    state: models.CardState | None,
    moment: datetime,
) -> datetime:
    """Return the time at which a card becomes due.

    A broken timestamp in the state file must not stop the scheduler, so the
    creation time of the card is used as the fallback.
    """
    if state is not None:
        due = models.safe_parse_iso(state.due)
        if due is not None:
            return due
    if card.created_at:
        parsed = models.safe_parse_iso(card.created_at)
        if parsed is not None:
            return parsed
    return moment


def reminder_time(
    card: models.Card,
    state: models.CardState | None,
    moment: datetime,
) -> datetime | None:
    """Return the time of the next reminder for one card, if it has one.

    A card without a state has no scheduled review: it is never due, it never
    wakes the scheduler up and it is never reminded. The relearn step of an
    "again" grade is not notifiable, so it is not reminded either.
    """
    if state is None or not state.notifiable:
        return None
    due = occurrence_due(card, state, moment)
    last = models.safe_parse_iso(state.last_reminded_at)
    if last is None:
        return due
    return max(due, last + timedelta(minutes=REMINDER_MINUTES))


def pending_occurrences(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[Occurrence]:
    """Return the cards that are due and whose reminder slot has passed."""
    pending: list[Occurrence] = []
    for card_id in sorted(cards):
        card = cards[card_id]
        state = states.get(card_id)
        slot = reminder_time(card, state, moment)
        if slot is None or slot > moment:
            continue
        pending.append(
            Occurrence(card=card, due=occurrence_due(card, state, moment), state=state)
        )
    return pending


def next_wakeup(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
    notify_enabled: bool = True,
) -> datetime | None:
    """Return the exact time of the next event worth waking up for."""
    candidates: list[datetime] = []
    for card_id in sorted(cards):
        card = cards[card_id]
        state = states.get(card_id)
        if notify_enabled:
            slot = reminder_time(card, state, moment)
            if slot is not None:
                candidates.append(slot)
        elif state is not None and state.notifiable:
            due = occurrence_due(card, state, moment)
            if due > moment:
                candidates.append(due)
    return min(candidates) if candidates else None


def plan_reminder(pending: Iterable[Occurrence]) -> tuple[Occurrence, ...]:
    """Group every pending occurrence into one reminder, oldest first."""
    return tuple(sorted(pending, key=lambda occurrence: occurrence.due))
