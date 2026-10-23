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

from . import config, models, notify, paths, scheduler, store

RESCAN_SECONDS = 3600.0


@dataclass(frozen=True)
class DeliveryReport:
    """The outcome of one delivery round."""

    delivered: tuple[scheduler.Occurrence, ...]
    notified: bool
    message: str
    reminded: tuple[tuple[str, str], ...] = ()


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
        pid = int(raw)
    except ValueError:
        return None
    return pid if pid > 1 else None


def remove_pid(path: Path | None = None) -> None:
    """Remove the pid file of the scheduler."""
    target = path or paths.pid_path()
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def _lock_is_free(path: Path | None = None) -> bool:
    """Return True when no scheduler holds the lock, releasing it again."""
    target = None if path is None else path.parent / "daemon.lock"
    handle = acquire_lock(target)
    if handle is None:
        return False
    handle.close()
    return True


def _pid_is_alive(pid: int) -> bool:
    """Return True when a process with this id still exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def scheduler_is_running(path: Path | None = None) -> bool:
    """Return True when a scheduler holds the lock and its process is alive."""
    if _lock_is_free(path):
        return False
    pid = read_pid(path)
    return pid is not None and _pid_is_alive(pid)


def signal_scheduler(path: Path | None = None) -> bool:
    """Ask a running scheduler to recompute its next wake up."""
    if _lock_is_free(path):
        return False
    pid = read_pid(path)
    if pid is None or not _pid_is_alive(pid):
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


def _mark_reminded(
    states: Mapping[str, models.CardState],
    occurrences: Sequence[scheduler.Occurrence],
    moment: datetime,
) -> tuple[tuple[str, str], ...]:
    """Record the reminder time on these cards and return their marks."""
    at = models.iso(moment)
    marks: list[tuple[str, str]] = []
    for occurrence in occurrences:
        state = occurrence.state
        if state is None:
            continue
        marks.append((occurrence.card.id, at))
        state.last_reminded_at = at
    return tuple(marks)


def _save_marks(marks: Sequence[tuple[str, str]]) -> dict[str, models.CardState]:
    """Apply the reminder marks to the current state file and save it.

    The states are read again right before the write, because a grade may
    have been recorded while the notification was being sent. Only the marks
    are applied, so the grade keeps its own due, interval and ease.
    """
    with store.state_lock():
        states = models.load_states(paths.state_path())
        for card_id, at in marks:
            state = states.setdefault(
                card_id, models.CardState(card_id=card_id, due=at, last_reminded_at=at)
            )
            state.last_reminded_at = at
        models.save_states(paths.state_path(), states)
    return states


def deliver_due(
    cards: Mapping[str, models.Card],
    states: Mapping[str, models.CardState],
    moment: datetime,
    notifier: Callable[[str, str], notify.NotifyResult] | None = None,
    notify_enabled: bool = True,
) -> DeliveryReport:
    """Deliver the reminder that is due and record when it was sent.

    The message of the report is only set when something went wrong, so that
    the caller can log it without writing a line for every empty round. The
    reminder marks are returned for the caller to persist, because the states
    it read may be out of date by the time the notification was sent. When
    notifications are disabled the due occurrences are marked without sending
    anything, and no reminder wakeup is scheduled.
    """
    send = notifier or notify.send
    pending = scheduler.pending_occurrences(cards, states, moment)
    group = scheduler.plan_reminder(pending)
    if not group:
        return DeliveryReport((), False, "")
    if not notify_enabled:
        marks = _mark_reminded(states, group, moment)
        return DeliveryReport((), False, "", marks)
    title, body = _notification_for(group)
    result = send(title, body)
    marks = _mark_reminded(states, group, moment)
    if result.ok:
        return DeliveryReport(group, True, "", marks)
    return DeliveryReport(
        group,
        False,
        result.message or "the notification failed",
        marks,
    )


def run(max_iterations: int | None = None, idle_timeout: float | None = None) -> int:
    """Run the scheduler until it is stopped.

    The scheduler sleeps until the exact moment the next card is due. When
    nothing is scheduled it rescans the files once an hour, that is the
    safety net for a deck that was edited by hand. The optional idle timeout
    caps that sleep, it is only used by the tests.
    """
    paths.ensure_dirs()
    lock = acquire_lock()
    if lock is None:
        print("error: another scheduler is already running", file=sys.stderr)
        return 1
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
        write_pid()
        disabled_notice = False
        while not stop_signals:
            timeout = RESCAN_SECONDS
            try:
                settings = config.load_config()
                cards = models.load_deck(paths.deck_path())
                states = models.load_states(paths.state_path())
                moment = models.now_utc()
                report = deliver_due(
                    cards,
                    states,
                    moment,
                    notify_enabled=settings.notify_enabled,
                )
                if report.reminded:
                    states = _save_marks(report.reminded)
                if not settings.notify_enabled:
                    if report.reminded and not disabled_notice:
                        print(
                            "notifications are disabled, advancing the reminder clock without sending",
                            file=sys.stderr,
                            flush=True,
                        )
                        disabled_notice = True
                else:
                    disabled_notice = False
                    if report.delivered:
                        print(f"delivered {len(report.delivered)} reminder(s)", flush=True)
                    if report.message and not report.notified:
                        if failures.should_log(report.message):
                            print(
                                f"notification problem: {report.message}",
                                file=sys.stderr,
                                flush=True,
                            )
                    elif report.notified and failures.recovered():
                        print(
                            "notifications are being delivered again",
                            file=sys.stderr,
                            flush=True,
                        )
                next_at = scheduler.next_wakeup(
                    cards, states, models.now_utc(), notify_enabled=settings.notify_enabled
                )
                if next_at is not None:
                    timeout = max(0.0, (next_at - models.now_utc()).total_seconds())
            except (ValueError, TypeError, OSError) as error:
                if failures.should_log(f"round failed: {error}"):
                    print(f"error: {error}", file=sys.stderr, flush=True)
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
