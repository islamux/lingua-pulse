import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import linguapulse
from linguapulse import daemon, models, notify

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


def test_the_delivered_occurrence_is_marked_as_handled(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    daemon.deliver_due(cards, states, moment, FakeNotifier())
    assert states["hello"].handled_due is not None


def test_a_card_is_not_notified_twice(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due=DUE)}
    notifier = FakeNotifier()
    daemon.deliver_due(cards, states, moment, notifier)
    second = daemon.deliver_due(cards, states, moment, notifier)
    assert len(notifier.sent) == 1
    assert second.delivered == ()


def test_a_stale_backlog_is_skipped(moment):
    cards = {"hello": make_card()}
    states = {"hello": models.CardState(card_id="hello", due="2020-01-01T08:00:00+00:00")}
    notifier = FakeNotifier()
    report = daemon.deliver_due(cards, states, moment, notifier)
    assert report.delivered == ()
    assert notifier.sent == []
    assert states["hello"].handled_due is not None


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
    assert states["hello"].handled_due is not None


def test_the_lock_excludes_a_second_scheduler(home):
    handle = daemon.acquire_lock()
    assert handle is not None
    assert daemon.acquire_lock() is None
    handle.close()
    assert daemon.acquire_lock() is not None


def test_the_pid_file_is_written_and_removed(home):
    daemon.write_pid()
    assert daemon.read_pid() == os.getpid()
    daemon.remove_pid()
    assert daemon.read_pid() is None


def test_read_pid_ignores_a_broken_pid_file(home):
    paths_pid = daemon.paths.pid_path()
    paths_pid.write_text("not a number", encoding="utf-8")
    assert daemon.read_pid() is None


def test_signalling_without_a_scheduler_does_nothing(home):
    assert daemon.signal_scheduler() is False


def test_signalling_a_running_scheduler_sends_a_wake_up(home):
    received = []
    previous = signal.signal(signal.SIGHUP, lambda signum, frame: received.append(signum))
    try:
        daemon.write_pid()
        assert daemon.signal_scheduler() is True
    finally:
        signal.signal(signal.SIGHUP, previous)
    assert received == [signal.SIGHUP]


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
