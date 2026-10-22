from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from linguapulse import models, srs

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
ZONE = ZoneInfo("UTC")


def test_new_state_is_due_immediately():
    state = srs.new_state("hello", NOW)
    assert state.due == models.iso(NOW)
    assert state.reps == 0
    assert state.ease == srs.DEFAULT_EASE
    assert state.notifiable is True


def test_good_on_a_new_card_schedules_one_day():
    state = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    assert state.interval_days == 1.0
    assert state.due_dt() == NOW + timedelta(days=1)
    assert state.reps == 1


def test_good_on_the_second_review_schedules_six_days():
    first = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    second = srs.apply_grade(first, "good", NOW, ZONE)
    assert second.interval_days == 6.0


def test_hard_grows_the_interval_slowly_and_lowers_the_ease():
    first = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    second = srs.apply_grade(first, "hard", NOW, ZONE)
    assert second.interval_days == pytest.approx(1.2)
    assert second.ease == pytest.approx(srs.DEFAULT_EASE - 0.15)


def test_easy_multiplies_the_interval_and_raises_the_ease():
    first = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    second = srs.apply_grade(first, "easy", NOW, ZONE)
    assert second.interval_days == pytest.approx(8.0)
    assert second.ease == pytest.approx(srs.DEFAULT_EASE + 0.15)


def test_again_schedules_a_ten_minute_relearn_and_resets_the_reps():
    state = srs.apply_grade(srs.new_state("hello", NOW), "again", NOW, ZONE)
    assert state.due_dt() == NOW + timedelta(minutes=srs.RELEARN_MINUTES)
    assert state.reps == 0
    assert state.lapses == 1
    assert state.notifiable is False


def test_ease_never_falls_below_the_minimum():
    state = srs.new_state("hello", NOW)
    for _ in range(10):
        state = srs.apply_grade(state, "again", NOW, ZONE)
    assert state.ease == srs.MIN_EASE


def test_ease_never_rises_above_the_maximum():
    state = srs.new_state("hello", NOW)
    for _ in range(20):
        state = srs.apply_grade(state, "easy", NOW, ZONE)
    assert state.ease == srs.MAX_EASE


def test_the_interval_is_capped():
    state = srs.new_state("hello", NOW)
    for _ in range(30):
        state = srs.apply_grade(state, "easy", NOW, ZONE)
    assert state.interval_days == srs.MAX_INTERVAL_DAYS


def test_grading_clears_the_handled_occurrence():
    first = srs.apply_grade(srs.new_state("hello", NOW), "good", NOW, ZONE)
    first.handled_due = first.due
    second = srs.apply_grade(first, "good", NOW, ZONE)
    assert second.handled_due is None


def test_an_unknown_grade_is_rejected():
    with pytest.raises(ValueError):
        srs.apply_grade(srs.new_state("hello", NOW), "perfect", NOW, ZONE)


def test_a_day_interval_keeps_the_local_time_of_day_across_a_dst_change():
    zone = ZoneInfo("Europe/Berlin")
    before = datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc)
    state = srs.apply_grade(srs.new_state("hello", before), "good", before, zone)
    assert state.due_dt().astimezone(zone).strftime("%Y-%m-%d %H:%M") == "2026-03-29 10:00"


def test_apply_grade_does_not_mutate_the_input_state():
    state = srs.new_state("hello", NOW)
    before = (
        state.due,
        state.interval_days,
        state.ease,
        state.reps,
        state.lapses,
        state.handled_due,
        state.notifiable,
    )
    _ = srs.apply_grade(state, "good", NOW, ZONE)
    after = (
        state.due,
        state.interval_days,
        state.ease,
        state.reps,
        state.lapses,
        state.handled_due,
        state.notifiable,
    )
    assert after == before
