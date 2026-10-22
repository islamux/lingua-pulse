"""Desktop notification delivery through notify-send."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Mapping

NOTIFY_SEND = "notify-send"
BUSCTL = "busctl"
NOTIFICATIONS_BUS_NAME = "org.freedesktop.Notifications"
DBUS_SESSION_BUS_ADDRESS = "DBUS_SESSION_BUS_ADDRESS"


@dataclass(frozen=True)
class NotifyResult:
    """The outcome of one delivery attempt."""

    ok: bool
    code: int
    message: str


def _environment(env: Mapping[str, str] | None) -> dict[str, str]:
    return dict(os.environ if env is None else env)


def notify_send_path(env: Mapping[str, str] | None = None) -> str | None:
    """Return the absolute path of notify-send, or None when it is missing."""
    environment = _environment(env)
    return shutil.which(NOTIFY_SEND, path=environment.get("PATH"))


def session_bus_address(env: Mapping[str, str] | None = None) -> str | None:
    """Return the session bus address, or None when no bus can be reached."""
    environment = _environment(env)
    address = environment.get(DBUS_SESSION_BUS_ADDRESS)
    if address:
        return address
    runtime = environment.get("XDG_RUNTIME_DIR")
    if runtime:
        return f"unix:path={runtime}/bus"
    return None


def child_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a child process environment that carries a usable bus address."""
    environment = _environment(env)
    address = session_bus_address(environment)
    if address:
        environment[DBUS_SESSION_BUS_ADDRESS] = address
    return environment


def notification_daemon(env: Mapping[str, str] | None = None) -> str | None:
    """Return the name of the running notification daemon, or None."""
    environment = _environment(env)
    if session_bus_address(environment) is None:
        return None
    busctl = shutil.which(BUSCTL, path=environment.get("PATH"))
    if not busctl:
        return None
    try:
        completed = subprocess.run(
            [busctl, "--user", "--no-pager", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            env=child_environment(environment),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        columns = line.split()
        if columns and columns[0] == NOTIFICATIONS_BUS_NAME:
            return columns[2] if len(columns) > 2 else "unknown"
    return None


def send(
    title: str,
    body: str,
    *,
    env: Mapping[str, str] | None = None,
    urgency: str = "normal",
    timeout: float = 10.0,
) -> NotifyResult:
    """Deliver one notification. The caller decides whether to try again."""
    environment = _environment(env)
    binary = notify_send_path(environment)
    if binary is None:
        return NotifyResult(
            False,
            127,
            "notify-send is not installed; install the notify-send or libnotify-bin package",
        )
    if not session_bus_address(environment):
        return NotifyResult(
            False,
            1,
            "no session bus address; set DBUS_SESSION_BUS_ADDRESS or XDG_RUNTIME_DIR",
        )
    try:
        completed = subprocess.run(
            [binary, "--app-name=linguapulse", f"--urgency={urgency}", "--", title, body],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=child_environment(environment),
        )
    except subprocess.TimeoutExpired:
        return NotifyResult(False, 124, "notify-send timed out")
    except OSError as exc:
        return NotifyResult(False, 1, f"could not run notify-send: {exc}")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return NotifyResult(
            False,
            completed.returncode,
            detail or f"notify-send exited with status {completed.returncode}",
        )
    return NotifyResult(True, 0, "")
