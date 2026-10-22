import pytest

from linguapulse import models, paths


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Point every XDG directory of lingua-pulse at a temporary directory."""
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    return tmp_path


def make_card(card_id="hello"):
    """Return a small card used by the CLI tests."""
    return models.Card(
        id=card_id,
        term="hello",
        source_lang="en",
        translations={"ar": "مرحبا", "zh": "你好"},
        pinyin="nǐ hǎo",
        created_at="2020-01-01T09:00:00+00:00",
    )


def write_deck(cards):
    """Write cards to the deck file."""
    models.save_deck(paths.deck_path(), {card.id: card for card in cards})


def write_broken_deck():
    """Write a deck file that is not valid JSON."""
    paths.deck_path().write_text('{"version": 1, "cards": {', encoding="utf-8")


def write_states(states):
    """Write card states to the state file."""
    models.save_states(paths.state_path(), states)
