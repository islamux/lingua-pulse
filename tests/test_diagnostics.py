import os

import pytest

from linguapulse import __version__, cli, config, daemon, diagnostics, notify, paths, store

PAST = "2020-01-01T09:00:00+00:00"
FUTURE = "2099-01-01T09:00:00+00:00"


def isolate_notifications(monkeypatch):
    """Keep a check that runs everything away from the notification bus."""
    monkeypatch.setattr(notify, "notify_send_path", lambda env=None: "/usr/bin/notify-send")
    monkeypatch.setattr(
        notify, "session_bus_address", lambda env=None: "unix:path=/run/user/1000/bus"
    )
    monkeypatch.setattr(notify, "notification_daemon", lambda env=None: "dunst")
    monkeypatch.setattr(
        diagnostics.shutil, "which", lambda name, path=None: "/usr/bin/busctl"
    )


def test_a_check_reports_its_name_and_detail():
    check = diagnostics.Check("deck", True, "3 cards")
    assert check.ok is True
    assert check.detail == "3 cards"


def test_the_paths_are_reported_as_ready(home):
    check = diagnostics.check_paths()
    assert check.ok is True


def test_the_deck_check_reports_the_number_of_cards(home):
    check = diagnostics.check_deck()
    assert check.ok is True
    assert "0 cards" in check.detail


def test_the_deck_check_fails_on_a_broken_deck(home):
    store.write_json(
        paths.deck_path(),
        {"cards": {"broken": {"id": "broken", "term": "", "source_lang": "en"}}},
    )
    check = diagnostics.check_deck()
    assert check.ok is False


def test_the_notify_send_check_reports_a_missing_binary(monkeypatch):
    monkeypatch.setattr(notify, "notify_send_path", lambda env=None: None)
    check = diagnostics.check_notify_send()
    assert check.ok is False
    assert "notify-send" in check.detail


def test_the_notify_send_check_reports_an_installed_binary(monkeypatch):
    monkeypatch.setattr(notify, "notify_send_path", lambda env=None: "/usr/bin/notify-send")
    check = diagnostics.check_notify_send()
    assert check.ok is True


def test_the_session_bus_check_reports_a_missing_address(monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "")
    check = diagnostics.check_session_bus()
    assert check.ok is False


def test_the_notification_daemon_check_reports_a_running_daemon(monkeypatch):
    monkeypatch.setattr(notify, "notification_daemon", lambda env=None: "dunst")
    check = diagnostics.check_notification_daemon()
    assert check.ok is True
    assert "dunst" in check.detail


def test_the_scheduler_check_reports_a_running_scheduler(home):
    daemon.write_pid()
    check = diagnostics.check_scheduler()
    assert check.ok is True


def test_the_scheduler_check_reports_a_missing_scheduler(home):
    check = diagnostics.check_scheduler()
    assert check.ok is False


def test_every_check_has_a_name_and_a_detail(home, monkeypatch):
    isolate_notifications(monkeypatch)
    for check in diagnostics.run_checks():
        assert check.name
        assert check.detail


def test_run_checks_covers_the_installation(home, monkeypatch):
    isolate_notifications(monkeypatch)
    names = [check.name for check in diagnostics.run_checks()]
    assert names == [
        "paths",
        "config",
        "deck",
        "state",
        "notify-send",
        "busctl",
        "session bus",
        "notification daemon",
        "scheduler",
        "schedule",
    ]


def test_the_paths_check_reports_an_unwritable_directory(home, monkeypatch):
    def fail():
        raise OSError("permission denied")

    monkeypatch.setattr(paths, "ensure_dirs", fail)
    check = diagnostics.check_paths()
    assert check.ok is False
    assert "permission denied" in check.detail


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_the_paths_check_reports_a_read_only_directory(home):
    directory = paths.data_dir()
    directory.chmod(0o555)
    try:
        check = diagnostics.check_paths()
    finally:
        directory.chmod(0o755)
    assert check.ok is False
    assert str(directory) in check.detail
    assert "not writable" in check.detail


def test_the_deck_check_reports_a_file_that_is_not_json(home):
    paths.deck_path().write_text("{", encoding="utf-8")
    check = diagnostics.check_deck()
    assert check.ok is False
    assert "cannot be read" in check.detail


def test_the_state_check_reports_an_empty_state(home):
    check = diagnostics.check_state()
    assert check.ok is True
    assert "0 states" in check.detail


def test_the_state_check_reports_the_scheduled_cards(home):
    store.write_json(
        paths.state_path(),
        {"cards": {"hello": {"card_id": "hello", "due": FUTURE}}},
    )
    check = diagnostics.check_state()
    assert check.ok is True
    assert "1 state" in check.detail


def test_the_state_check_fails_on_a_broken_state_file(home):
    paths.state_path().write_text("{", encoding="utf-8")
    check = diagnostics.check_state()
    assert check.ok is False
    assert "cannot be read" in check.detail


def test_the_busctl_check_reports_a_missing_binary(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name, path=None: None)
    check = diagnostics.check_busctl()
    assert check.ok is False
    assert "busctl" in check.detail


def test_the_busctl_check_reports_an_installed_binary(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name, path=None: "/usr/bin/busctl")
    check = diagnostics.check_busctl()
    assert check.ok is True
    assert "/usr/bin/busctl" in check.detail


def test_the_notification_daemon_check_reports_an_unowned_bus_name(monkeypatch):
    monkeypatch.setattr(notify, "notification_daemon", lambda env=None: "-")
    check = diagnostics.check_notification_daemon()
    assert check.ok is False
    assert "no daemon" in check.detail


def test_the_config_check_reports_the_defaults(home):
    check = diagnostics.check_config()
    assert check.ok is True
    assert "defaults" in check.detail
    assert "source en" in check.detail
    assert "target ar" in check.detail


def test_the_config_check_reports_the_effective_file(home):
    config.save_config(config.Config(source_lang="fr", target_lang="zh", notify_enabled=False))
    check = diagnostics.check_config()
    assert check.ok is True
    assert "source fr" in check.detail
    assert "target zh" in check.detail
    assert "notifications disabled" in check.detail


def test_the_config_check_surfaces_a_rejected_file(home):
    paths.config_path().write_text("{", encoding="utf-8")
    check = diagnostics.check_config()
    assert check.ok is False
    assert "not valid JSON" in check.detail
    assert "defaults" in check.detail


def test_the_config_check_surfaces_a_rejected_value(home):
    store.write_json(paths.config_path(), {"source_lang": "de", "target_lang": "ar"})
    check = diagnostics.check_config()
    assert check.ok is False
    assert "source_lang 'de'" in check.detail
    assert "source en" in check.detail


def test_the_scheduler_check_reports_a_dead_process(home, monkeypatch):
    daemon.write_pid()
    monkeypatch.setattr(daemon, "scheduler_is_running", lambda path=None: False)
    check = diagnostics.check_scheduler()
    assert check.ok is False
    assert "not running" in check.detail


def test_the_schedule_check_reports_nothing_scheduled(home):
    check = diagnostics.check_schedule()
    assert check.ok is True
    assert "nothing is scheduled" in check.detail


def test_the_schedule_check_reports_the_next_wakeup(home):
    store.write_json(
        paths.deck_path(),
        {
            "cards": {
                "hello": {
                    "id": "hello",
                    "term": "hello",
                    "source_lang": "en",
                    "translations": {"ar": "مرحبا"},
                    "created_at": PAST,
                }
            }
        },
    )
    store.write_json(
        paths.state_path(),
        {"cards": {"hello": {"card_id": "hello", "due": FUTURE}}},
    )
    check = diagnostics.check_schedule()
    assert check.ok is True
    assert "next wakeup" in check.detail
    assert "2099" in check.detail


def test_the_schedule_check_reports_a_due_card(home):
    store.write_json(
        paths.deck_path(),
        {
            "cards": {
                "hello": {
                    "id": "hello",
                    "term": "hello",
                    "source_lang": "en",
                    "translations": {"ar": "مرحبا"},
                    "created_at": PAST,
                }
            }
        },
    )
    store.write_json(
        paths.state_path(),
        {"cards": {"hello": {"card_id": "hello", "due": PAST}}},
    )
    check = diagnostics.check_schedule()
    assert check.ok is True
    assert "due now" in check.detail


def test_the_doctor_prints_the_version_and_the_checks(monkeypatch, capsys):
    monkeypatch.setattr(
        diagnostics, "run_checks", lambda: [diagnostics.Check("deck", True, "3 cards")]
    )
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert f"lingua-pulse {__version__}" in out
    assert "[ok] deck: 3 cards" in out


def test_the_doctor_exits_with_one_when_a_check_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        diagnostics,
        "run_checks",
        lambda: [diagnostics.Check("scheduler", False, "not running")],
    )
    assert cli.main(["doctor"]) == 1
    assert "[FAIL] scheduler: not running" in capsys.readouterr().out


def test_the_doctor_explains_how_to_diagnose_a_notification_failure(monkeypatch, capsys):
    monkeypatch.setattr(diagnostics, "run_checks", lambda: [])
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "notify-send" in out
    assert "busctl" in out
    assert "DBUS_SESSION_BUS_ADDRESS" in out


def test_status_reports_the_notifications_and_the_scheduler(home, capsys, monkeypatch):
    monkeypatch.setattr(daemon, "scheduler_is_running", lambda path=None: False)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Notify:     enabled" in out
    assert "Scheduler: not running" in out


def test_status_reports_disabled_notifications_and_a_running_scheduler(home, capsys, monkeypatch):
    config.save_config(config.Config(notify_enabled=False))
    monkeypatch.setattr(daemon, "scheduler_is_running", lambda path=None: True)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Notify:     disabled" in out
    assert "Scheduler: running" in out
