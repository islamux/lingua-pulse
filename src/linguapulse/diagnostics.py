"""Checks that tell the user whether the installation works."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import config, daemon, models, notify, paths, scheduler, store

NOTIFICATION_HELP = (
    "run 'notify-send --app-name=linguapulse test hello' to test the notification itself",
    "run 'busctl --user --no-pager list | grep org.freedesktop.Notifications' to find the daemon",
    "in a systemd user service, make sure DBUS_SESSION_BUS_ADDRESS reaches the scheduler",
)


@dataclass(frozen=True)
class Check:
    """The result of one diagnostic check."""

    name: str
    ok: bool
    detail: str


def _counted(count: int, singular: str) -> str:
    """Return a count with a correctly inflected noun."""
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {singular}s"


def _probe_writable(directory: Path) -> None:
    """Write and remove a probe file to prove that the directory is writable."""
    descriptor, name = tempfile.mkstemp(
        dir=directory, prefix=".linguapulse-probe-", suffix=".tmp"
    )
    try:
        os.write(descriptor, b"probe\n")
    finally:
        os.close(descriptor)
        Path(name).unlink(missing_ok=True)


def check_paths() -> Check:
    """Check that the data directories exist and are writable."""
    try:
        paths.ensure_dirs()
    except OSError as exc:
        return Check("paths", False, f"the data directory is not writable: {exc}")
    directories = (paths.data_dir(), paths.config_dir(), paths.state_dir())
    for directory in directories:
        try:
            _probe_writable(directory)
        except OSError as exc:
            return Check("paths", False, f"{directory} is not writable: {exc}")
    return Check(
        "paths",
        True,
        f"data {directories[0]}, config {directories[1]}, state {directories[2]}",
    )


def _config_summary(settings: config.Config) -> str:
    """Describe the configuration that is in effect."""
    notifications = "enabled" if settings.notify_enabled else "disabled"
    return (
        f"source {settings.source_lang}, target {settings.target_lang}, "
        f"notifications {notifications}"
    )


def _rejected_config_fields(raw: dict[str, object], settings: config.Config) -> list[str]:
    """Return the fields of the file that the loader replaced with a default."""
    rejected: list[str] = []
    for field_name, attribute in (
        ("source_lang", settings.source_lang),
        ("target_lang", settings.target_lang),
    ):
        if field_name not in raw:
            continue
        value = raw[field_name]
        if not isinstance(value, str) or value.strip() != attribute:
            rejected.append(f"{field_name} {value!r}")
    if "notify_enabled" in raw:
        value = raw["notify_enabled"]
        if not isinstance(value, bool) or value != settings.notify_enabled:
            rejected.append(f"notify_enabled {value!r}")
    return rejected


def check_config() -> Check:
    """Check which configuration is in effect and whether the file was accepted."""
    defaults = _config_summary(config.Config())
    try:
        raw = store.read_json(paths.config_path(), None)
    except (OSError, ValueError) as exc:
        return Check(
            "config",
            False,
            f"the configuration file cannot be read: {exc}; the defaults are in effect: {defaults}",
        )
    if raw is None:
        return Check("config", True, f"the defaults are in effect: {defaults}")
    if not isinstance(raw, dict):
        return Check(
            "config",
            False,
            f"the configuration file is not a JSON object; the defaults are in effect: {defaults}",
        )
    settings = config.Config.from_dict(raw)
    rejected = _rejected_config_fields(raw, settings)
    if rejected:
        return Check(
            "config",
            False,
            f"{', '.join(rejected)} rejected; in effect: {_config_summary(settings)}",
        )
    return Check("config", True, f"in effect: {_config_summary(settings)}")


def check_deck() -> Check:
    """Check that the deck file can be read and has no problems."""
    path = paths.deck_path()
    try:
        raw = store.read_json(path, None)
    except (OSError, ValueError) as exc:
        return Check("deck", False, f"the deck file cannot be read: {exc}")
    if raw is None:
        return Check("deck", True, "0 cards, no deck file yet")
    problems = models.validate_deck_raw(raw)
    if problems:
        return Check("deck", False, f"{len(problems)} problem(s): {problems[0]}")
    count = len(raw.get("cards", {})) if isinstance(raw, dict) else 0
    return Check("deck", True, f"{count} cards, no problems")


def check_state() -> Check:
    """Check that the state file can be read and holds a schedule."""
    path = paths.state_path()
    try:
        states = models.load_states(path)
    except (OSError, TypeError, ValueError) as exc:
        return Check("state", False, f"the state file cannot be read: {exc}")
    if not path.exists():
        return Check("state", True, "0 states, no state file yet")
    return Check("state", True, f"{_counted(len(states), 'state')}, no problems")


def check_notify_send() -> Check:
    """Check that notify-send is installed."""
    binary = notify.notify_send_path()
    if binary is None:
        return Check("notify-send", False, "notify-send was not found in PATH")
    return Check("notify-send", True, binary)


def check_busctl() -> Check:
    """Check that busctl is installed, so that the daemon can be identified."""
    binary = shutil.which(notify.BUSCTL, path=os.environ.get("PATH") or "")
    if binary is None:
        return Check("busctl", False, "busctl was not found in PATH")
    return Check("busctl", True, binary)


def check_session_bus() -> Check:
    """Check that a session bus address can be resolved."""
    address = notify.session_bus_address()
    if address is None:
        return Check(
            "session bus",
            False,
            "no DBUS_SESSION_BUS_ADDRESS and no XDG_RUNTIME_DIR",
        )
    return Check("session bus", True, address)


def check_notification_daemon() -> Check:
    """Check that a notification daemon owns the notifications bus name."""
    daemon_name = notify.notification_daemon()
    if daemon_name is None or daemon_name == "-":
        return Check(
            "notification daemon",
            False,
            "no daemon owns org.freedesktop.Notifications",
        )
    return Check("notification daemon", True, daemon_name)


def check_scheduler() -> Check:
    """Check that the scheduler is running."""
    pid = daemon.read_pid()
    if pid is None:
        return Check("scheduler", False, "the scheduler is not running")
    if not daemon.scheduler_is_running():
        return Check("scheduler", False, f"the scheduler is not running (process {pid} is gone)")
    return Check("scheduler", True, f"running with process {pid}")


def check_schedule() -> Check:
    """Check when the scheduler will wake up next."""
    try:
        cards = models.load_deck(paths.deck_path())
        states = models.load_states(paths.state_path())
        settings = config.load_config()
    except (OSError, TypeError, ValueError) as exc:
        return Check("schedule", False, f"the deck or state file cannot be read: {exc}")
    moment = models.now_utc()
    pending = scheduler.pending_occurrences(cards, states, moment)
    if pending:
        return Check("schedule", True, f"{_counted(len(pending), 'card')} due now")
    upcoming = scheduler.next_wakeup(
        cards, states, moment, notify_enabled=settings.notify_enabled
    )
    if upcoming is None:
        return Check("schedule", True, "nothing is scheduled")
    return Check("schedule", True, f"next wakeup at {upcoming.isoformat()}")


def run_checks() -> list[Check]:
    """Run every diagnostic check."""
    return [
        check_paths(),
        check_config(),
        check_deck(),
        check_state(),
        check_notify_send(),
        check_busctl(),
        check_session_bus(),
        check_notification_daemon(),
        check_scheduler(),
        check_schedule(),
    ]
