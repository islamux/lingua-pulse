import json

from conftest import write_broken_deck
from linguapulse import cli, models, paths


def test_add_stores_a_new_card(home, capsys):
    assert cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"]) == 0
    assert "Added" in capsys.readouterr().out
    deck = models.load_deck(paths.deck_path())
    assert len(deck) == 1
    card = next(iter(deck.values()))
    assert card.translations["ar"] == "مرحبا"
    assert card.source_lang == "en"


def test_add_normalizes_the_text(home, capsys):
    assert cli.main(["add", "--term", "cafe\u0301", "--lang", "es", "--text", "hola"]) == 0
    capsys.readouterr()
    deck = models.load_deck(paths.deck_path())
    card = next(iter(deck.values()))
    assert card.term == "caf\u00e9"


def test_add_refuses_a_duplicate_card(home, capsys):
    cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"])
    capsys.readouterr()
    assert cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert len(models.load_deck(paths.deck_path())) == 1


def test_add_rejects_mismatched_language_and_text(home, capsys):
    assert cli.main(["add", "--term", "hello", "--lang", "ar"]) == 2
    assert "--text" in capsys.readouterr().err


def test_add_creates_a_due_state(home, capsys):
    cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"])
    capsys.readouterr()
    states = models.load_states(paths.state_path())
    assert len(states) == 1


def test_add_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["add", "--term", "new", "--lang", "ar", "--text", "جديد"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""
    assert paths.deck_path().read_text(encoding="utf-8").startswith('{"version": 1, "cards": {')


def test_list_prints_the_cards(home, capsys):
    cli.main(["add", "--term", "hello", "--lang", "ar", "--text", "مرحبا"])
    capsys.readouterr()
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "hello" in out
    assert "مرحبا" in out


def test_list_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["list"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""


def test_seed_adds_the_bundled_cards(home, capsys):
    assert cli.main(["seed"]) == 0
    assert "Added" in capsys.readouterr().out
    assert len(models.load_deck(paths.deck_path())) == len(cli.seed_cards())


def test_seed_does_not_duplicate_cards(home, capsys):
    cli.main(["seed"])
    capsys.readouterr()
    assert cli.main(["seed"]) == 0
    assert "0" in capsys.readouterr().out
    assert len(models.load_deck(paths.deck_path())) == len(cli.seed_cards())


def test_seed_reports_a_broken_deck_file(home, capsys):
    write_broken_deck()
    assert cli.main(["seed"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""


def test_the_bundled_seed_cards_are_valid(home):
    for card in cli.seed_cards():
        raw = json.loads(json.dumps(card.to_dict()))
        assert models.validate_deck_raw({"cards": {card.id: raw}}) == []


def test_config_shows_the_current_settings(home, capsys):
    assert cli.main(["config"]) == 0
    out = capsys.readouterr().out
    assert "source_lang" in out


def test_config_updates_the_settings(home, capsys):
    assert cli.main(["config", "--target-lang", "zh"]) == 0
    capsys.readouterr()
    assert cli.main(["config"]) == 0
    assert "zh" in capsys.readouterr().out


def test_config_rejects_an_unknown_language(home, capsys):
    assert cli.main(["config", "--target-lang", "zh"]) == 0
    capsys.readouterr()
    assert cli.main(["config", "--source-lang", "xx"]) == 2
    captured = capsys.readouterr()
    assert captured.err == (
        "error: unknown language 'xx', the supported languages are ar, en, es, fr, tr, zh\n"
    )
    assert captured.out == ""
    assert cli.main(["config", "--target-lang", "yy"]) == 2
    assert "unknown language 'yy'" in capsys.readouterr().err
    assert cli.main(["config"]) == 0
    out = capsys.readouterr().out
    assert "source_lang = en" in out
    assert "target_lang = zh" in out
