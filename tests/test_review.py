from datetime import datetime, timezone

from linguapulse import models, review

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def make_card(card_id="hello", created_at="2026-10-20T09:00:00+00:00"):
    return models.Card(
        id=card_id,
        term="hello",
        source_lang="en",
        translations={"ar": "مرحبا", "zh": "你好"},
        pinyin="nǐ hǎo",
        notes="a greeting",
        tags=["greetings"],
        created_at=created_at,
    )


def state_for(card_id, due, **overrides):
    data = {"card_id": card_id, "due": due}
    data.update(overrides)
    return models.CardState(**data)


def test_due_cards_orders_the_most_overdue_card_first():
    cards = {"later": make_card("later"), "earlier": make_card("earlier")}
    states = {
        "later": state_for("later", "2026-10-21T08:50:00+00:00"),
        "earlier": state_for("earlier", "2026-10-21T08:00:00+00:00"),
    }
    assert [card.id for card in review.due_cards(cards, states, NOW)] == ["earlier", "later"]


def test_due_cards_ignores_cards_that_are_not_due():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T10:00:00+00:00")}
    assert review.due_cards(cards, states, NOW) == []


def test_due_cards_holds_a_card_without_a_state():
    cards = {"hello": make_card(created_at="2026-10-21T08:00:00+00:00")}
    assert [card.id for card in review.due_cards(cards, {}, NOW)] == ["hello"]


def test_due_cards_holds_a_relearn_card():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:55:00+00:00", notifiable=False)}
    assert [card.id for card in review.due_cards(cards, states, NOW)] == ["hello"]


def test_a_card_created_in_the_future_is_not_due():
    cards = {"hello": make_card(created_at="2026-10-21T10:00:00+00:00")}
    assert review.due_cards(cards, {}, NOW) == []
    card, when = review.next_due(cards, {}, NOW)
    assert card.id == "hello"
    assert when == datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)


def test_current_card_returns_the_most_overdue_card():
    cards = {"later": make_card("later"), "earlier": make_card("earlier")}
    states = {
        "later": state_for("later", "2026-10-21T08:50:00+00:00"),
        "earlier": state_for("earlier", "2026-10-21T08:00:00+00:00"),
    }
    assert review.current_card(cards, states, NOW).id == "earlier"


def test_current_card_returns_none_when_nothing_is_due():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T10:00:00+00:00")}
    assert review.current_card(cards, states, NOW) is None


def test_next_due_is_none_when_nothing_is_scheduled():
    cards = {"hello": make_card()}
    states = {"hello": state_for("hello", "2026-10-21T08:00:00+00:00")}
    assert review.next_due(cards, states, NOW) is None


def test_next_due_reports_the_soonest_future_card():
    cards = {"hello": make_card(), "world": make_card("world")}
    states = {
        "hello": state_for("hello", "2026-10-21T12:00:00+00:00"),
        "world": state_for("world", "2026-10-21T10:00:00+00:00"),
    }
    card, when = review.next_due(cards, states, NOW)
    assert card.id == "world"
    assert when == datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)


def test_render_card_hides_the_translations_by_default():
    output = review.render_card(make_card())
    assert "hello" in output
    assert "مرحبا" not in output
    assert "a greeting" not in output


def test_render_card_reveals_the_translations():
    output = review.render_card(make_card(), reveal=True)
    assert "مرحبا" in output
    assert "你好" in output
    assert "a greeting" in output


def test_render_card_isolates_right_to_left_translations():
    output = review.render_card(make_card(), reveal=True)
    assert "ar: ⁧مرحبا⁩" in output


def test_render_card_shows_the_pinyin():
    assert "nǐ hǎo" in review.render_card(make_card())


def test_render_card_puts_the_requested_language_first():
    output = review.render_card(make_card(), reveal=True, target_lang="zh")
    assert output.index("zh:") < output.index("ar:")


def test_render_card_falls_back_to_the_sorted_languages():
    output = review.render_card(make_card(), reveal=True, target_lang="fr")
    assert output.index("ar:") < output.index("zh:")


def test_render_card_isolates_a_right_to_left_id():
    output = review.render_card(make_card(card_id="مرحبا"))
    assert output.splitlines()[0] == "⁧مرحبا⁩  [greetings]"


def test_render_card_isolates_right_to_left_tags():
    card = make_card()
    card.tags = ["تحية"]
    output = review.render_card(card)
    assert output.splitlines()[0] == "hello  [⁧تحية⁩]"


def test_render_card_shows_the_position_and_the_id():
    output = review.render_card(make_card(), index=2, total=7)
    assert output.splitlines()[0] == "2 of 7  (hello)  [greetings]"
