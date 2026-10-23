import json

import pytest

from linguapulse import store


def test_read_json_returns_the_default_when_the_file_is_missing(tmp_path):
    assert store.read_json(tmp_path / "missing.json", {"a": 1}) == {"a": 1}


def test_read_json_raises_on_broken_json(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        store.read_json(broken, None)


def test_read_json_raises_a_plain_value_error_for_a_broken_document(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        store.read_json(broken, None)
    assert not isinstance(excinfo.value, json.JSONDecodeError)
    assert str(broken) in str(excinfo.value)


def test_write_json_keeps_unicode_unescaped(tmp_path):
    target = tmp_path / "deck.json"
    store.write_json(target, {"term": "مرحبا"})
    assert "مرحبا" in target.read_text(encoding="utf-8")


def test_write_json_replaces_the_file_atomically(tmp_path):
    target = tmp_path / "deck.json"
    store.write_json(target, {"version": 1})
    store.write_json(target, {"version": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 2}
    assert list(tmp_path.glob("*.tmp")) == []


def test_jsonl_round_trip_skips_broken_lines(tmp_path):
    target = tmp_path / "history.jsonl"
    store.append_jsonl(target, {"card_id": "a"})
    with target.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    store.append_jsonl(target, {"card_id": "b"})
    assert store.read_jsonl(target) == [{"card_id": "a"}, {"card_id": "b"}]


def test_read_jsonl_returns_an_empty_list_when_the_file_is_missing(tmp_path):
    assert store.read_jsonl(tmp_path / "missing.jsonl") == []
