from datetime import datetime, timezone

from linguapulse import models, scheduler

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def make_card(card_id="hello", created_at="2026-10-20T09:00:00+00:00"):
    return models.Card(
        id=card_id,
        term=card_id,
        source_lang="en",
        translations={"ar": card_id},
        created_at=created_at,
    )


def state_for(card_id, due, **overrides):
    data = {"card_id": card_id, "due": due}
    data.update(overrides)
    return models.CardState.from_dict(data)


def test_a_due_card_is_pending():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    assert [o.card.id for o in scheduler.pending_occurrences(cards, states, NOW)] == ["hello"]


def test_a_card_that_is_not_due_is_not_pending():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T10:00:00+00:00")}
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_a_reminder_is_not_repeated_inside_the_ten_minute_slot():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="2026-10-21T08:55:00+00:00"
        )
    }
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_a_reminder_repeats_at_the_exact_ten_minute_boundary():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="2026-10-21T08:50:00+00:00"
        )
    }
    assert [o.card.id for o in scheduler.pending_occurrences(cards, states, NOW)] == ["hello"]


def test_a_broken_reminder_clock_is_treated_as_never_reminded():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="not a timestamp"
        )
    }
    assert [o.card.id for o in scheduler.pending_occurrences(cards, states, NOW)] == ["hello"]


def test_a_relearn_card_is_never_pending():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:55:00+00:00", notifiable=False)}
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_a_card_without_a_state_has_no_scheduled_review():
    cards = {"hello": make_card()}
    assert scheduler.pending_occurrences(cards, {}, NOW) == []
    assert scheduler.next_wakeup(cards, {}, NOW) is None


def test_next_wakeup_returns_the_soonest_future_due():
    cards = {"hello": make_card(), "world": make_card()}
    states = {
        "hello": state_for("hello", "2026-10-22T09:00:00+00:00"),
        "world": state_for("world", "2026-10-21T12:00:00+00:00"),
    }
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def test_next_wakeup_counts_the_remaining_minutes_of_the_reminder_slot():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="2026-10-21T08:55:00+00:00"
        )
    }
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 21, 9, 5, tzinfo=timezone.utc)


def test_a_reminder_slot_in_the_past_is_returned_for_an_immediate_wakeup():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T08:00:00+00:00", last_reminded_at="2026-10-21T08:20:00+00:00"
        )
    }
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 21, 8, 30, tzinfo=timezone.utc)


def test_a_card_that_was_never_reminded_wakes_at_its_past_due():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-20T09:00:00+00:00")}
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def test_next_wakeup_ignores_reminders_when_notifications_are_disabled():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello", "2026-10-21T10:00:00+00:00", last_reminded_at="2026-10-21T09:55:00+00:00"
        )
    }
    assert scheduler.next_wakeup(cards, states, NOW, notify_enabled=True) == datetime(
        2026, 10, 21, 10, 5, tzinfo=timezone.utc
    )
    assert scheduler.next_wakeup(cards, states, NOW, notify_enabled=False) == datetime(
        2026, 10, 21, 10, 0, tzinfo=timezone.utc
    )


def test_next_wakeup_without_notifications_is_none_for_an_overdue_card():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    assert scheduler.next_wakeup(cards, states, NOW, notify_enabled=False) is None


def test_plan_reminder_groups_every_pending_card():
    cards = {"old": make_card("old"), "late": make_card("late")}
    states = {
        "old": state_for("old", "2026-10-21T06:00:00+00:00"),
        "late": state_for("late", "2026-10-21T08:55:00+00:00"),
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    group = scheduler.plan_reminder(pending)
    assert [o.card.id for o in group] == ["old", "late"]


def test_an_empty_backlog_plans_nothing():
    assert scheduler.plan_reminder([]) == ()


def test_a_broken_due_falls_back_to_the_creation_time():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "not a timestamp")}
    due = scheduler.occurrence_due(cards["hello"], states["hello"], NOW)
    assert due == datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def test_the_due_iso_of_an_occurrence_round_trips():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    assert models.safe_parse_iso(pending[0].due_iso) == pending[0].due
