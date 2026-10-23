from linguapulse import paths


def test_home_override_keeps_everything_in_one_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    assert paths.data_dir() == tmp_path / "data"
    assert paths.config_dir() == tmp_path / "config"
    assert paths.state_dir() == tmp_path / "state"


def test_files_live_in_the_expected_directories(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    assert paths.deck_path() == tmp_path / "data" / "deck.json"
    assert paths.state_path() == tmp_path / "data" / "state.json"
    assert paths.history_path() == tmp_path / "data" / "history.jsonl"
    assert paths.config_path() == tmp_path / "config" / "config.json"
    assert paths.lock_path() == tmp_path / "state" / "daemon.lock"
    assert paths.pid_path() == tmp_path / "state" / "daemon.pid"


def test_xdg_variables_are_honoured(tmp_path, monkeypatch):
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "conf"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert paths.data_dir() == tmp_path / "share" / "linguapulse"
    assert paths.config_dir() == tmp_path / "conf" / "linguapulse"
    assert paths.state_dir() == tmp_path / "state" / "linguapulse"


def test_ensure_dirs_creates_all_directories(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    assert paths.data_dir().is_dir()
    assert paths.config_dir().is_dir()
    assert paths.state_dir().is_dir()
