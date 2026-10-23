"""The policy that decides which due occurrences become reminders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from . import models
from .srs import GRACE_MINUTES


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


@dataclass(frozen=True)
class Reminder:
    """The outcome of planning a reminder for one wake up."""

    due: datetime
    group: tuple[Occurrence, ...]
    skipped: tuple[Occurrence, ...]

    @property
    def handled(self) -> tuple[Occurrence, ...]:
        """Return every occurrence that was acted on, delivered or skipped."""
        return self.group + self.skipped


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


def _scheduled_review(
    card: models.Card,
    state: models.CardState | None,
    moment: datetime,
) -> Occurrence | None:
    """Return the scheduled review of a card, or None when it has none.

    A card without a state has no scheduled review: it is never due, it never
    wakes the scheduler up and it is never reminded. The relearn step of an
    "again" grade is not notifiable, so it is not reminded either. An
    occurrence that was already acted on is not a review any more.
    """
    if state is None or not state.notifiable:
        return None
    due = occurrence_due(card, state, moment)
    if state.handled_due:
        handled = models.safe_parse_iso(state.handled_due)
        if handled is not None and handled == due:
            return None
    return Occurrence(card=card, due=due, state=state)


def pending_occurrences(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> list[Occurrence]:
    """Return the occurrences that are due and that were not acted on yet."""
    pending: list[Occurrence] = []
    for card_id in sorted(cards):
        occurrence = _scheduled_review(cards[card_id], states.get(card_id), moment)
        if occurrence is None or occurrence.due > moment:
            continue
        pending.append(occurrence)
    return pending


def next_wakeup(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
) -> datetime | None:
    """Return the exact time of the next occurrence worth waking up for."""
    candidates: list[datetime] = []
    for card_id in sorted(cards):
        occurrence = _scheduled_review(cards[card_id], states.get(card_id), moment)
        if occurrence is None or occurrence.due <= moment:
            continue
        candidates.append(occurrence.due)
    return min(candidates) if candidates else None


def plan_reminder(pending: Iterable[Occurrence], moment: datetime) -> Reminder | None:
    """Pick the single reminder to deliver and mark the older ones as skipped."""
    ordered = sorted(pending, key=lambda occurrence: occurrence.due)
    if not ordered:
        return None
    latest = ordered[-1].due
    group = tuple(occurrence for occurrence in ordered if occurrence.due == latest)
    older = tuple(occurrence for occurrence in ordered if occurrence.due != latest)
    if (moment - latest).total_seconds() > GRACE_MINUTES * 60:
        return Reminder(due=latest, group=(), skipped=tuple(ordered))
    return Reminder(due=latest, group=group, skipped=older)
