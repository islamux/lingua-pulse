from linguapulse import service


def test_render_unit_contains_the_exec_start():
    unit = service.render_unit("/usr/local/bin/linguapulse")
    assert "ExecStart=/usr/local/bin/linguapulse daemon" in unit


def test_render_unit_passes_the_session_bus():
    unit = service.render_unit("/usr/local/bin/linguapulse")
    assert "PassEnvironment=DBUS_SESSION_BUS_ADDRESS DISPLAY XAUTHORITY" in unit


def test_render_unit_restarts_after_a_failure():
    unit = service.render_unit("/usr/local/bin/linguapulse")
    assert "Restart=on-failure" in unit


def test_install_unit_writes_the_unit_file(home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    path = service.install_unit("/usr/local/bin/linguapulse")
    assert path.exists()
    assert "linguapulse daemon" in path.read_text(encoding="utf-8")


def test_install_autostart_keeps_the_existing_content(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\nhc() { :; }\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    assert service.install_autostart() is True
    content = target.read_text(encoding="utf-8")
    assert "# my own settings" in content
    assert "hc() { :; }" in content
    assert service.AUTOSTART_BEGIN in content
    assert "systemctl --user start linguapulse.service" in content


def test_install_autostart_creates_a_backup(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    service.install_autostart()
    backup = tmp_path / "autostart.linguapulse.bak"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "# my own settings\n"


def test_install_autostart_is_idempotent(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    service.install_autostart()
    once = target.read_text(encoding="utf-8")
    assert service.install_autostart() is False
    assert target.read_text(encoding="utf-8") == once


def test_install_autostart_creates_the_file_when_it_is_missing(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    assert service.install_autostart() is True
    assert target.exists()


def test_remove_autostart_removes_only_the_block(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    service.install_autostart()
    assert service.remove_autostart() is True
    content = target.read_text(encoding="utf-8")
    assert "# my own settings" in content
    assert service.AUTOSTART_BEGIN not in content
    assert "linguapulse" not in content


def test_remove_autostart_without_a_block_does_nothing(home, tmp_path, monkeypatch):
    target = tmp_path / "autostart"
    target.write_text("# my own settings\n", encoding="utf-8")
    monkeypatch.setenv(service.ENV_AUTOSTART, str(target))
    assert service.remove_autostart() is False
    assert target.read_text(encoding="utf-8") == "# my own settings\n"
