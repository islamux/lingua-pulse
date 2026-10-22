from conftest import make_card, write_deck, write_states

from linguapulse import cli, config, models, paths, store

PAST = "2020-01-01T09:00:00+00:00"
FUTURE = "2099-01-01T09:00:00+00:00"


def test_show_prints_the_due_card_without_the_answer(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["show"]) == 0
    out = capsys.readouterr().out
    assert "hello" in out
    assert "مرحبا" not in out


def test_show_reveals_the_translations_on_request(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["show", "--reveal"]) == 0
    assert "مرحبا" in capsys.readouterr().out


def test_show_reports_when_nothing_is_due(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=FUTURE)})
    assert cli.main(["show"]) == 0
    assert "Nothing is due" in capsys.readouterr().out


def test_show_uses_the_requested_language_without_storing_it(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["show", "--reveal", "--lang", "zh"]) == 0
    out = capsys.readouterr().out
    assert out.index("zh:") < out.index("ar:")
    assert config.load_config().target_lang == "ar"


def test_show_shows_the_requested_number_of_cards(home, capsys):
    write_deck([make_card("hello"), make_card("world")])
    write_states(
        {
            "hello": models.CardState(card_id="hello", due=PAST),
            "world": models.CardState(card_id="world", due=PAST),
        }
    )
    assert cli.main(["show", "--count", "2"]) == 0
    out = capsys.readouterr().out
    assert "1 of 2" in out
    assert "2 of 2" in out


def test_next_grades_the_due_card_and_records_the_review(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["next", "good"]) == 0
    assert "Graded 'good'" in capsys.readouterr().out
    states = models.load_states(paths.state_path())
    assert states["hello"].reps == 1
    entries = store.read_jsonl(paths.history_path())
    assert entries[-1]["card_id"] == "hello"
    assert entries[-1]["grade"] == "good"


def test_next_reports_when_nothing_is_due(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=FUTURE)})
    assert cli.main(["next", "good"]) == 0
    assert "Nothing is due" in capsys.readouterr().out


def test_next_hides_the_translations_on_request(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    assert cli.main(["next", "good", "--hide"]) == 0
    out = capsys.readouterr().out
    assert "مرحبا" not in out
    assert "Graded 'good'" in out


def test_history_lists_the_recorded_reviews(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    cli.main(["next", "good"])
    capsys.readouterr()
    assert cli.main(["history"]) == 0
    out = capsys.readouterr().out
    assert "hello" in out
    assert "good" in out


def test_history_filters_by_card(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    cli.main(["next", "good"])
    capsys.readouterr()
    assert cli.main(["history", "--card", "other"]) == 0
    assert "No reviews" in capsys.readouterr().out


def test_history_limits_the_number_of_entries(home, capsys):
    write_deck([make_card()])
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    cli.main(["next", "good"])
    capsys.readouterr()
    write_states({"hello": models.CardState(card_id="hello", due=PAST)})
    cli.main(["next", "good"])
    capsys.readouterr()
    assert cli.main(["history", "--limit", "1"]) == 0
    assert capsys.readouterr().out.count("good") == 1


def test_status_reports_the_deck_size(home, capsys):
    write_deck([make_card()])
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "1 card" in out
    assert "Time zone" in out


def test_status_reports_the_due_cards_the_next_card_and_the_languages(home, capsys):
    write_deck([make_card("hello"), make_card("later")])
    write_states(
        {
            "hello": models.CardState(card_id="hello", due=PAST),
            "later": models.CardState(card_id="later", due=FUTURE),
        }
    )
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "2 cards" in out
    assert "1 card" in out
    assert "later" in out
    assert "Languages: source en, target ar" in out


def test_validate_accepts_a_clean_deck(home, capsys):
    write_deck([make_card()])
    assert cli.main(["validate"]) == 0
    assert "no problems found" in capsys.readouterr().out


def test_validate_reports_a_broken_card(home, capsys):
    card = make_card()
    card.term = ""
    write_deck([card])
    assert cli.main(["validate"]) == 1
    out = capsys.readouterr().out
    assert "problem" in out
    assert "term" in out


def test_validate_reports_a_missing_deck(home, capsys):
    assert cli.main(["validate"]) == 1
    assert "No deck file" in capsys.readouterr().out
