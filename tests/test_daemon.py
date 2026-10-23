import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import linguapulse
from linguapulse import cli, config, daemon, models, notify, paths, srs

PAST = "2020-01-01T09:00:00+00:00"
DUE = "2026-10-21T08:55:00+00:00"


class FakeNotifier:
    """Record the notifications that were sent."""

    def __init__(self, result=None):
        self.sent = []
        self.result = result or notify.NotifyResult(True, 0, "")

    def __call__(self, title, body):
        self.sent.append((title, body))
        return self.result


def make_card(card_id="hello"):
    return models.Card(
        id=card_id,
        term="hello",
        source_lang="en",
        translations={"ar": "مرحبا"},
        created_at=PAST,
    )


def test_a_due_card_is_delivered(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    report = daemon.deliver_due(cards, states, moment, notifier)
    assert len(report.delivered) == 1
    assert report.notified is True
    assert len(notifier.sent) == 1
    assert "hello" in notifier.sent[0][1]


def test_the_delivered_card_records_the_reminder_time(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    daemon.deliver_due(cards, states, moment, FakeNotifier())
    assert states["hello"].last_reminded_at == models.iso(moment)


def test_a_card_is_notified_again_after_ten_minutes(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    daemon.deliver_due(cards, states, moment, notifier)
    second = daemon.deliver_due(cards, states, moment + timedelta(minutes=10), notifier)
    assert len(notifier.sent) == 2
    assert len(second.delivered) == 1


def test_a_failing_notification_records_the_reminder_time(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    failing = FakeNotifier(notify.NotifyResult(False, 1, "Could not connect"))
    daemon.deliver_due(cards, states, moment, failing)
    assert states["hello"].last_reminded_at == models.iso(moment)


def test_a_failed_notification_is_not_retried_inside_the_slot(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    failing = FakeNotifier(notify.NotifyResult(False, 1, "Could not connect"))
    daemon.deliver_due(cards, states, moment, failing)
    daemon.deliver_due(cards, states, moment + timedelta(minutes=5), failing)
    assert len(failing.sent) == 1


def test_disabled_notifications_record_the_reminder_time(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    report = daemon.deliver_due(cards, states, moment, notifier, notify_enabled=False)
    assert report.delivered == ()
    assert notifier.sent == []
    assert states["hello"].last_reminded_at == models.iso(moment)


def test_three_slots_three_notifications(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    for offset in (0, 10, 20):
        report = daemon.deliver_due(cards, states, moment + timedelta(minutes=offset), notifier)
        assert len(report.delivered) == 1
    assert len(notifier.sent) == 3


def test_an_overdue_card_is_delivered_immediately(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due="2020-01-01T08:00:00+00:00")}
    notifier = FakeNotifier()
    report = daemon.deliver_due(cards, states, moment, notifier)
    assert len(report.delivered) == 1
    assert len(notifier.sent) == 1


def test_a_card_is_not_notified_twice(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    daemon.deliver_due(cards, states, moment, notifier)
    second = daemon.deliver_due(cards, states, moment, notifier)
    assert len(notifier.sent) == 1
    assert second.delivered == ()


def test_nothing_is_due_when_the_deck_is_empty(moment):
    report = daemon.deliver_due({}, {}, moment, FakeNotifier())
    assert report.delivered == ()
    assert report.notified is False


def test_a_failing_notification_is_reported(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    failing = FakeNotifier(notify.NotifyResult(False, 1, "Could not connect"))
    report = daemon.deliver_due(cards, states, moment, failing)
    assert report.notified is False
    assert "Could not connect" in report.message
    assert states["hello"].last_reminded_at is not None


def test_the_lock_excludes_a_second_scheduler(home):
    handle = daemon.acquire_lock()
    assert handle is not None
    assert daemon.acquire_lock() is None
    handle.close()
    second = daemon.acquire_lock()
    assert second is not None
    second.close()


def test_the_pid_file_is_written_and_removed(home):
    daemon.write_pid()
    assert daemon.read_pid() == os.getpid()
    daemon.remove_pid()
    assert daemon.read_pid() is None


def test_read_pid_ignores_a_broken_pid_file(home):
    paths_pid = daemon.paths.pid_path()
    paths_pid.write_text("not a number", encoding="utf-8")
    assert daemon.read_pid() is None


def test_read_pid_rejects_a_process_group_and_every_process(home):
    pid_file = paths.pid_path()
    for raw in ("0", "-1"):
        pid_file.write_text(f"{raw}\n", encoding="utf-8")
        assert daemon.read_pid() is None


def test_signalling_without_a_scheduler_does_nothing(home):
    assert daemon.signal_scheduler() is False


def test_signalling_a_running_scheduler_sends_a_wake_up(home):
    received = []
    previous = signal.signal(signal.SIGHUP, lambda signum, frame: received.append(signum))
    lock = daemon.acquire_lock()
    try:
        daemon.write_pid()
        assert daemon.signal_scheduler() is True
    finally:
        signal.signal(signal.SIGHUP, previous)
        lock.close()
    assert received == [signal.SIGHUP]


def test_a_stale_pid_file_without_the_lock_is_not_signalled(home):
    received = []
    previous = signal.signal(signal.SIGHUP, lambda signum, frame: received.append(signum))
    try:
        daemon.write_pid()
        assert daemon.scheduler_is_running() is False
        assert daemon.signal_scheduler() is False
    finally:
        signal.signal(signal.SIGHUP, previous)
    assert received == []


def test_the_failure_log_reports_the_first_and_every_tenth_failure():
    failures = daemon.FailureLog(every=10)
    assert failures.should_log("boom") is True
    assert failures.should_log("boom") is False
    for _ in range(7):
        failures.should_log("boom")
    assert failures.should_log("boom") is True


def test_the_failure_log_reports_the_recovery():
    failures = daemon.FailureLog(every=10)
    assert failures.recovered() is False
    failures.should_log("boom")
    assert failures.recovered() is True
    assert failures.recovered() is False
    assert failures.should_log("boom") is True


def test_the_loop_stops_after_the_configured_number_of_iterations(home):
    assert daemon.run(max_iterations=2, idle_timeout=0.0) == 0


def test_a_grade_saved_while_sending_survives_the_marks(home, moment, monkeypatch):
    due = models.iso(models.now_utc() - timedelta(minutes=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    graded = {}

    def grade_while_sending(title, body):
        states = models.load_states(paths.state_path())
        graded["state"] = srs.apply_grade(states["hello"], "easy", moment)
        models.save_states(paths.state_path(), {"hello": graded["state"]})
        return notify.NotifyResult(True, 0, "")

    monkeypatch.setattr(daemon.notify, "send", grade_while_sending)
    assert daemon.run(max_iterations=1, idle_timeout=0.0) == 0
    saved = models.load_states(paths.state_path())["hello"]
    assert saved.reps == graded["state"].reps
    assert saved.interval_days == graded["state"].interval_days
    assert saved.ease == graded["state"].ease
    assert saved.last_reminded_at is not None


def test_a_cli_grade_saved_while_sending_survives_the_marks(home, monkeypatch):
    due = models.iso(models.now_utc() - timedelta(minutes=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    graded = {}

    def grade_while_sending(title, body):
        assert cli.main(["next", "good"]) == 0
        graded["state"] = models.load_states(paths.state_path())["hello"]
        return notify.NotifyResult(True, 0, "")

    monkeypatch.setattr(daemon.notify, "send", grade_while_sending)
    assert daemon.run(max_iterations=1, idle_timeout=0.0) == 0
    saved = models.load_states(paths.state_path())["hello"]
    assert saved.reps == graded["state"].reps == 1
    assert saved.interval_days == graded["state"].interval_days
    assert saved.ease == graded["state"].ease
    assert saved.last_reminded_at is not None


def test_due_reminders_are_marked_when_notifications_are_disabled(home, monkeypatch, capsys):
    due = models.iso(models.now_utc() - timedelta(minutes=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    config.save_config(config.Config(notify_enabled=False))
    sent = []
    monkeypatch.setattr(daemon.notify, "send", lambda title, body: sent.append(title))
    assert daemon.run(max_iterations=1, idle_timeout=0.0) == 0
    assert sent == []
    assert models.load_states(paths.state_path())["hello"].last_reminded_at is not None
    captured = capsys.readouterr()
    assert "notifications are disabled" in captured.err
    assert "notification problem" not in captured.err


def test_the_loop_ignores_reminder_slots_when_notifications_are_disabled(home, monkeypatch):
    fixed = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(models, "now_utc", lambda: fixed)
    due = models.iso(fixed - timedelta(hours=1))
    reminded = models.iso(fixed - timedelta(minutes=4))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(
        paths.state_path(),
        {"hello": models.CardState(card_id="hello", due=due, last_reminded_at=reminded)},
    )
    config.save_config(config.Config(notify_enabled=False))
    timeouts = []

    def fake_select(read, write, error, timeout):
        timeouts.append(timeout)
        return ([], [], [])

    monkeypatch.setattr(daemon.select, "select", fake_select)
    assert daemon.run(max_iterations=1) == 0
    assert timeouts == [3600.0]


def test_the_loop_sleeps_until_the_next_wakeup(home, monkeypatch):
    fixed = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(models, "now_utc", lambda: fixed)
    due = models.iso(fixed + timedelta(hours=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    timeouts = []

    def fake_select(read, write, error, timeout):
        timeouts.append(timeout)
        return ([], [], [])

    monkeypatch.setattr(daemon.select, "select", fake_select)
    assert daemon.run(max_iterations=1) == 0
    assert timeouts == [3600.0]


def test_the_loop_sleeps_until_the_next_reminder(home, monkeypatch):
    fixed = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(models, "now_utc", lambda: fixed)
    due = models.iso(fixed - timedelta(hours=1))
    reminded = models.iso(fixed - timedelta(minutes=4))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(
        paths.state_path(),
        {"hello": models.CardState(card_id="hello", due=due, last_reminded_at=reminded)},
    )
    timeouts = []

    def fake_select(read, write, error, timeout):
        timeouts.append(timeout)
        return ([], [], [])

    monkeypatch.setattr(daemon.select, "select", fake_select)
    assert daemon.run(max_iterations=1) == 0
    assert timeouts == [360.0]


def test_a_notification_problem_and_the_recovery_are_logged(home, monkeypatch, capsys):
    due = models.iso(models.now_utc() - timedelta(minutes=1))
    models.save_deck(paths.deck_path(), {"hello": make_card()})
    models.save_states(paths.state_path(), {"hello": models.CardState(card_id="hello", due=due)})
    calls = []

    def flaky(title, body):
        calls.append(title)
        if len(calls) == 1:
            models.save_deck(
                paths.deck_path(), {"hello": make_card(), "world": make_card("world")}
            )
            models.save_states(
                paths.state_path(),
                {
                    "hello": models.CardState(card_id="hello", due=due),
                    "world": models.CardState(card_id="world", due=due),
                },
            )
            return notify.NotifyResult(False, 1, "Could not connect")
        return notify.NotifyResult(True, 0, "")

    monkeypatch.setattr(daemon.notify, "send", flaky)
    assert daemon.run(max_iterations=2, idle_timeout=0.0) == 0
    assert len(calls) == 2
    captured = capsys.readouterr()
    assert "notification problem: Could not connect" in captured.err
    assert "notifications are being delivered again" in captured.err


def test_a_broken_deck_does_not_kill_the_scheduler(home, capsys):
    paths.deck_path().write_text('{"version": 1, "cards": {', encoding="utf-8")
    assert daemon.run(max_iterations=2, idle_timeout=0.0) == 0
    captured = capsys.readouterr()
    assert "error: " in captured.err
    assert "is not valid JSON" in captured.err
    assert daemon.read_pid() is None
    lock = daemon.acquire_lock()
    assert lock is not None
    lock.close()


def test_a_second_scheduler_reports_the_error(home, capsys):
    lock = daemon.acquire_lock()
    try:
        assert daemon.run(max_iterations=1, idle_timeout=0.0) == 1
    finally:
        lock.close()
    assert "error: another scheduler is already running" in capsys.readouterr().err


def test_the_scheduler_stops_on_a_terminate_signal(home):
    source_root = str(Path(linguapulse.__file__).resolve().parents[1])
    environment = {**os.environ, "PYTHONPATH": source_root}
    process = subprocess.Popen(
        [sys.executable, "-m", "linguapulse", "daemon"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and daemon.read_pid() is None:
            time.sleep(0.1)
        assert daemon.read_pid() == process.pid
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=10) == 0
        assert daemon.read_pid() is None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
