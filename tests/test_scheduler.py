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


def test_pending_occurrences_holds_the_cards_that_are_due():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    assert [occurrence.card.id for occurrence in pending] == ["hello"]


def test_pending_occurrences_skips_cards_that_are_not_due_yet():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T10:00:00+00:00")}
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_pending_occurrences_skips_an_occurrence_that_was_already_handled():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello",
            "2026-10-21T08:00:00+00:00",
            handled_due="2026-10-21T08:00:00+00:00",
        )
    }
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_pending_occurrences_reminds_a_card_that_got_a_new_due_time():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello",
            "2026-10-21T08:00:00+00:00",
            handled_due="2026-10-20T08:00:00+00:00",
        )
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    assert [occurrence.card.id for occurrence in pending] == ["hello"]


def test_pending_occurrences_skips_relearn_cards():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:55:00+00:00", notifiable=False)}
    assert scheduler.pending_occurrences(cards, states, NOW) == []


def test_a_card_without_a_state_has_no_scheduled_review():
    cards = {"hello": make_card()}
    assert scheduler.pending_occurrences(cards, {}, NOW) == []
    assert scheduler.next_wakeup(cards, {}, NOW) is None


def test_a_card_without_a_state_does_not_suppress_a_card_that_is_due():
    cards = {
        "fresh": make_card("fresh", created_at="2026-10-21T08:58:00+00:00"),
        "due": make_card("due"),
    }
    states = {"due": state_for("due", "2026-10-21T08:55:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert [occurrence.card.id for occurrence in reminder.group] == ["due"]
    assert reminder.skipped == ()


def test_next_wakeup_returns_the_soonest_future_occurrence():
    cards = {"hello": make_card(), "world": make_card()}
    states = {
        "hello": state_for("hello", "2026-10-22T09:00:00+00:00"),
        "world": state_for("world", "2026-10-21T12:00:00+00:00"),
    }
    assert scheduler.next_wakeup(cards, states, NOW) == datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def test_next_wakeup_is_none_without_a_future_occurrence():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-20T09:00:00+00:00")}
    assert scheduler.next_wakeup(cards, states, NOW) is None


def test_a_relearn_card_does_not_produce_a_wakeup():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T12:00:00+00:00", notifiable=False)}
    assert scheduler.next_wakeup(cards, states, NOW) is None


def test_an_already_handled_occurrence_does_not_produce_a_wakeup():
    cards = {"hello": make_card()}
    states = {
        "hello": state_for(
            "hello",
            "2026-10-21T12:00:00+00:00",
            handled_due="2026-10-21T12:00:00+00:00",
        )
    }
    assert scheduler.next_wakeup(cards, states, NOW) is None


def test_the_latest_overdue_reminder_within_the_grace_window_is_selected():
    cards = {"old": make_card("old"), "late": make_card("late")}
    states = {
        "old": state_for("old", "2026-10-21T06:00:00+00:00"),
        "late": state_for("late", "2026-10-21T08:55:00+00:00"),
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert [occurrence.card.id for occurrence in reminder.group] == ["late"]
    assert [occurrence.card.id for occurrence in reminder.skipped] == ["old"]
    assert reminder.due == datetime(2026, 10, 21, 8, 55, tzinfo=timezone.utc)


def test_a_reminder_that_is_exactly_at_the_grace_limit_is_delivered():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:45:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert [occurrence.card.id for occurrence in reminder.group] == ["hello"]
    assert reminder.skipped == ()


def test_older_reminders_are_never_replayed():
    cards = {"old": make_card("old"), "late": make_card("late")}
    states = {
        "old": state_for("old", "2026-10-21T06:00:00+00:00"),
        "late": state_for("late", "2026-10-21T08:55:00+00:00"),
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert len(reminder.handled) == 2


def test_stale_backlog_is_not_delivered():
    cards = {"old": make_card("old")}
    states = {"old": state_for("old", "2026-10-21T06:00:00+00:00")}
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert reminder.group == ()
    assert [occurrence.card.id for occurrence in reminder.skipped] == ["old"]


def test_cards_that_are_due_at_the_same_moment_form_one_group():
    cards = {"a": make_card("a"), "b": make_card("b")}
    states = {
        "a": state_for("a", "2026-10-21T08:55:00+00:00"),
        "b": state_for("b", "2026-10-21T08:55:00+00:00"),
    }
    pending = scheduler.pending_occurrences(cards, states, NOW)
    reminder = scheduler.plan_reminder(pending, NOW)
    assert sorted(occurrence.card.id for occurrence in reminder.group) == ["a", "b"]
    assert reminder.skipped == ()


def test_an_empty_backlog_plans_nothing():
    assert scheduler.plan_reminder([], NOW) is None


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
