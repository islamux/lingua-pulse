from linguapulse import config, models, paths


def test_defaults_are_used_when_no_file_exists(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    settings = config.load_config()
    assert settings.source_lang == config.DEFAULT_SOURCE_LANG
    assert settings.target_lang == config.DEFAULT_TARGET_LANG
    assert settings.notify_enabled is True


def test_saving_and_loading_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    config.save_config(config.Config(source_lang="ar", target_lang="zh", notify_enabled=False))
    settings = config.load_config()
    assert settings.source_lang == "ar"
    assert settings.target_lang == "zh"
    assert settings.notify_enabled is False


def test_a_broken_file_falls_back_to_the_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    paths.config_path().write_text('{"source_lang": 5}', encoding="utf-8")
    settings = config.load_config()
    assert settings.source_lang == config.DEFAULT_SOURCE_LANG


def test_a_file_that_is_not_valid_json_falls_back_to_the_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    paths.config_path().write_text("{not json", encoding="utf-8")
    settings = config.load_config()
    assert settings.source_lang == config.DEFAULT_SOURCE_LANG
    assert settings.target_lang == config.DEFAULT_TARGET_LANG
    assert settings.notify_enabled is True


def test_an_unsupported_language_falls_back_to_the_default(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    paths.ensure_dirs()
    paths.config_path().write_text(
        '{"source_lang": "de", "target_lang": "fr"}', encoding="utf-8"
    )
    assert "de" not in models.SUPPORTED_LANGUAGES
    settings = config.load_config()
    assert settings.source_lang == config.DEFAULT_SOURCE_LANG
    assert settings.target_lang == "fr"
