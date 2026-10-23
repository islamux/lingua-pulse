from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from linguapulse import models


def make_card(card_id="hello", **overrides):
    data = {
        "id": card_id,
        "term": "hello",
        "source_lang": "en",
        "translations": {"ar": "مرحبا", "zh": "你好"},
        "pinyin": "nǐ hǎo",
    }
    data.update(overrides)
    return models.Card.from_dict(data)


def test_card_round_trip_keeps_every_field():
    card = make_card(notes="greeting", tags=["greetings"], created_at="2026-10-21T09:00:00+00:00")
    assert models.Card.from_dict(card.to_dict()) == card


def test_load_deck_returns_an_empty_deck_when_the_file_is_missing(tmp_path):
    assert models.load_deck(tmp_path / "deck.json") == {}


def test_save_and_load_deck_round_trip(tmp_path):
    deck = {"hello": make_card()}
    target = tmp_path / "deck.json"
    models.save_deck(target, deck)
    assert models.load_deck(target) == deck


def test_load_deck_rejects_a_file_without_cards(tmp_path):
    target = tmp_path / "deck.json"
    target.write_text('{"version": 1}', encoding="utf-8")
    try:
        models.load_deck(target)
    except ValueError as exc:
        assert "not a valid deck file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_load_deck_rejects_a_null_card(tmp_path):
    target = tmp_path / "deck.json"
    target.write_text('{"cards": {"hello": null}}', encoding="utf-8")
    try:
        models.load_deck(target)
    except ValueError as exc:
        assert "not a valid deck file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_load_deck_rejects_a_card_that_is_not_an_object(tmp_path):
    target = tmp_path / "deck.json"
    target.write_text('{"cards": {"hello": "a card"}}', encoding="utf-8")
    try:
        models.load_deck(target)
    except ValueError as exc:
        assert "not a valid deck file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_card_state_round_trip():
    state = models.CardState(
        card_id="hello",
        due="2026-10-22T09:00:00+00:00",
        last_reminded_at="2026-10-21T09:00:00+00:00",
    )
    assert models.CardState.from_dict(state.to_dict()) == state


def test_an_old_state_file_ignores_handled_due():
    state = models.CardState.from_dict(
        {
            "card_id": "hello",
            "due": "2026-10-22T09:00:00+00:00",
            "handled_due": "2026-10-21T09:00:00+00:00",
        }
    )
    assert state.last_reminded_at is None


def test_card_state_due_dt_parses_the_timestamp():
    state = models.CardState(card_id="hello", due="2026-10-22T09:00:00+00:00")
    assert state.due_dt() == datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)


def test_load_states_returns_an_empty_mapping_when_the_file_is_missing(tmp_path):
    assert models.load_states(tmp_path / "state.json") == {}


def test_save_and_load_states_round_trip(tmp_path):
    states = {
        "hello": models.CardState(
            card_id="hello",
            due="2026-10-22T09:00:00+00:00",
            last_reminded_at="2026-10-21T09:00:00+00:00",
        )
    }
    target = tmp_path / "state.json"
    models.save_states(target, states)
    assert models.load_states(target) == states


def test_load_states_rejects_a_file_without_cards(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"version": 1}', encoding="utf-8")
    try:
        models.load_states(target)
    except ValueError as exc:
        assert "is not a valid state file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_load_states_rejects_a_null_card(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"cards": {"hello": null}}', encoding="utf-8")
    try:
        models.load_states(target)
    except ValueError as exc:
        assert "is not a valid state file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_load_states_rejects_a_card_that_is_not_an_object(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"cards": {"hello": "a card"}}', encoding="utf-8")
    try:
        models.load_states(target)
    except ValueError as exc:
        assert "is not a valid state file" in str(exc)
    else:
        raise AssertionError("expected a ValueError")


def test_validate_accepts_a_correct_card():
    raw = {"cards": {"hello": make_card().to_dict()}}
    assert models.validate_deck_raw(raw) == []


def test_validate_reports_a_missing_pinyin_for_chinese():
    card = make_card().to_dict()
    card["pinyin"] = ""
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("no 'pinyin'" in problem for problem in problems)


def test_validate_reports_pinyin_without_tone_marks():
    card = make_card().to_dict()
    card["pinyin"] = "ni hao"
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("no tone marks" in problem for problem in problems)


def test_validate_reports_pinyin_with_a_bare_umlaut_as_having_no_tone_marks():
    card = make_card().to_dict()
    card["pinyin"] = "lü"
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("no tone marks" in problem for problem in problems)


def test_validate_reports_decomposed_text():
    card = make_card().to_dict()
    card["term"] = "xi\u030c"
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("Normalization Form C" in problem for problem in problems)


def test_validate_reports_an_unsupported_language():
    card = make_card().to_dict()
    card["translations"]["de"] = "hallo"
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("unsupported language" in problem for problem in problems)


def test_validate_reports_an_empty_term():
    card = make_card().to_dict()
    card["term"] = "  "
    problems = models.validate_deck_raw({"cards": {"hello": card}})
    assert any("'term' is empty" in problem for problem in problems)


def test_local_zone_prefers_the_tz_variable(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    assert str(models.local_zone()) == "Europe/Berlin"


def test_add_wall_clock_keeps_the_local_time_of_day_across_a_dst_change():
    zone = ZoneInfo("Europe/Berlin")
    before = datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc)
    after = models.add_wall_clock(before, 1, zone)
    assert after.astimezone(zone).strftime("%Y-%m-%d %H:%M") == "2026-03-29 10:00"
    assert after == datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)


def test_safe_parse_iso_returns_none_for_broken_input():
    assert models.safe_parse_iso("not a timestamp") is None
    assert models.safe_parse_iso("2026-10-22T09:00:00+00:00") == datetime(
        2026, 10, 22, 9, 0, tzinfo=timezone.utc
    )
