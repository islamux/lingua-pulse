"""The background scheduler that wakes up when a card becomes due."""

from __future__ import annotations

import errno
import fcntl
import io
import os
import select
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import models, notify, paths, scheduler

RESCAN_SECONDS = 3600.0


@dataclass(frozen=True)
class DeliveryReport:
    """The outcome of one delivery round."""

    delivered: tuple[scheduler.Occurrence, ...]
    skipped: tuple[scheduler.Occurrence, ...]
    notified: bool
    message: str


class FailureLog:
    """Report a failure once and then only every tenth repetition."""

    def __init__(self, every: int = 10) -> None:
        self.every = max(1, every)
        self.counts: dict[str, int] = {}
        self.current = ""

    def should_log(self, key: str) -> bool:
        """Return True when the failure should be written to the log."""
        self.current = key
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        return count == 1 or count % self.every == 0

    def recovered(self) -> bool:
        """Forget the failure streak and return True when there was one."""
        if not self.current:
            return False
        self.current = ""
        self.counts.clear()
        return True


def acquire_lock(path: Path | None = None) -> io.TextIOWrapper | None:
    """Take the exclusive scheduler lock, or return None when it is taken."""
    target = path or paths.lock_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = open(target, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return None
        raise
    return handle


def write_pid(path: Path | None = None) -> None:
    """Write the process id of the scheduler to the pid file."""
    target = path or paths.pid_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{os.getpid()}\n", encoding="utf-8")


def read_pid(path: Path | None = None) -> int | None:
    """Read the process id of the scheduler, or None when there is none."""
    target = path or paths.pid_path()
    try:
        raw = target.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def remove_pid(path: Path | None = None) -> None:
    """Remove the pid file of the scheduler."""
    target = path or paths.pid_path()
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def scheduler_is_running(path: Path | None = None) -> bool:
    """Return True when a scheduler process is alive."""
    pid = read_pid(path)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_scheduler(path: Path | None = None) -> bool:
    """Ask a running scheduler to recompute its next wake up."""
    pid = read_pid(path)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGHUP)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _notification_for(group: Sequence[scheduler.Occurrence]) -> tuple[str, str]:
    """Build the title and the body of one notification."""
    lines: list[str] = []
    for occurrence in group:
        card = occurrence.card
        translations = card.translations
        answer = ""
        if translations:
            language = sorted(translations)[0]
            answer = f"  {language}: {translations[language]}"
        lines.append(f"{card.term}{answer}")
    if len(group) == 1:
        title = "lingua-pulse: a card is due"
    else:
        title = f"lingua-pulse: {len(group)} cards are due"
    return title, "\n".join(lines)


def _mark_handled(
    states: Mapping[str, models.CardState],
    occurrences: Sequence[scheduler.Occurrence],
) -> None:
    """Remember that these occurrences were acted on."""
    for occurrence in occurrences:
        state = occurrence.state
        if state is None:
            continue
        state.handled_due = occurrence.due.isoformat()


def deliver_due(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
    notifier: Callable[[str, str], notify.NotifyResult] | None = None,
) -> DeliveryReport:
    """Deliver the reminder that is due and remember that it was handled.

    The message of the report is only set when something went wrong, so that
    the caller can log it without writing a line for every empty round.
    """
    send = notifier or notify.send
    pending = scheduler.pending_occurrences(cards, states, moment)
    if not pending:
        return DeliveryReport((), (), False, "")
    reminder = scheduler.plan_reminder(pending, moment)
    if reminder is None:
        return DeliveryReport((), (), False, "")
    if not reminder.group:
        _mark_handled(states, reminder.skipped)
        return DeliveryReport((), reminder.skipped, False, "")
    title, body = _notification_for(reminder.group)
    result = send(title, body)
    _mark_handled(states, reminder.handled)
    if result.ok:
        return DeliveryReport(reminder.group, reminder.skipped, True, "")
    return DeliveryReport(
        reminder.group,
        reminder.skipped,
        False,
        result.message or "the notification failed",
    )


def run(max_iterations: int | None = None, idle_timeout: float | None = None) -> int:
    """Run the scheduler until it is stopped.

    The scheduler sleeps until the exact moment the next card is due. At most
    once per hour it rescans the files, that is the safety net for a deck
    that was edited by hand. The optional idle timeout caps that sleep, it is
    only used by the tests.
    """
    paths.ensure_dirs()
    lock = acquire_lock()
    if lock is None:
        print("another scheduler is already running", file=sys.stderr)
        return 1
    write_pid()
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    failures = FailureLog()
    stop_signals: list[int] = []
    wake_signals: list[int] = []

    def handle_stop(signum: int, frame: object) -> None:
        stop_signals.append(signum)
        try:
            os.write(write_fd, b"x")
        except OSError:
            pass

    def handle_wake(signum: int, frame: object) -> None:
        wake_signals.append(signum)
        try:
            os.write(write_fd, b"x")
        except OSError:
            pass

    previous = {
        signal.SIGTERM: signal.signal(signal.SIGTERM, handle_stop),
        signal.SIGINT: signal.signal(signal.SIGINT, handle_stop),
        signal.SIGHUP: signal.signal(signal.SIGHUP, handle_wake),
    }
    iterations = 0
    try:
        while not stop_signals:
            cards = models.load_deck(paths.deck_path())
            states = models.load_states(paths.state_path())
            moment = models.now_utc()
            report = deliver_due(cards, states, moment)
            if report.delivered or report.skipped:
                models.save_states(paths.state_path(), states)
            if report.delivered:
                print(f"delivered {len(report.delivered)} reminder(s)", flush=True)
            elif report.skipped:
                print(f"skipped {len(report.skipped)} stale reminder(s)", flush=True)
            if report.message and not report.notified:
                if failures.should_log(report.message):
                    print(f"notification problem: {report.message}", file=sys.stderr, flush=True)
            elif report.notified and failures.recovered():
                print("notifications are being delivered again", file=sys.stderr, flush=True)
            next_at = scheduler.next_wakeup(cards, states, models.now_utc())
            timeout = RESCAN_SECONDS
            if next_at is not None:
                timeout = max(0.0, (next_at - models.now_utc()).total_seconds())
            if idle_timeout is not None:
                timeout = idle_timeout
            select.select([read_fd], [], [], timeout)
            try:
                os.read(read_fd, 4096)
            except (BlockingIOError, OSError):
                pass
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        remove_pid()
        os.close(read_fd)
        os.close(write_fd)
        lock.close()
    return 0
