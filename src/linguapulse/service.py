"""Installation of the systemd user unit and of the herbstluftwm autostart."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

UNIT_NAME = "linguapulse.service"
AUTOSTART_BEGIN = "# >>> lingua-pulse >>>"
AUTOSTART_END = "# <<< lingua-pulse <<<"
ENV_AUTOSTART = "LINGUAPULSE_AUTOSTART"

UNIT_TEMPLATE = """[Unit]
Description=lingua-pulse vocabulary scheduler
After=graphical-session.target

[Service]
Type=simple
ExecStart={executable} daemon
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
PassEnvironment=DBUS_SESSION_BUS_ADDRESS DISPLAY XAUTHORITY
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""

AUTOSTART_BLOCK = f"""{AUTOSTART_BEGIN}
# Start the lingua-pulse scheduler when the session starts.
systemctl --user start {UNIT_NAME}
{AUTOSTART_END}
"""


class MalformedBlock(ValueError):
    """Raised when only one of the two autostart markers is present."""


def unit_dir() -> Path:
    """Return the directory that holds the systemd user units."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "systemd" / "user"


def unit_path() -> Path:
    """Return the path of the systemd user unit."""
    return unit_dir() / UNIT_NAME


def autostart_path() -> Path:
    """Return the path of the herbstluftwm autostart file."""
    override = os.environ.get(ENV_AUTOSTART)
    if override:
        return Path(override)
    return Path.home() / ".config" / "herbstluftwm" / "autostart"


def default_executable() -> str:
    """Return the command that starts lingua-pulse."""
    found = shutil.which("linguapulse")
    if found:
        return found
    import sys

    return f"{sys.executable} -m linguapulse"


def render_unit(executable: str) -> str:
    """Return the content of the systemd user unit."""
    return UNIT_TEMPLATE.format(executable=executable)


def install_unit(executable: str) -> Path:
    """Write the systemd user unit."""
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_unit(executable), encoding="utf-8")
    return path


def remove_unit() -> bool:
    """Remove the systemd user unit."""
    path = unit_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def autostart_block() -> str:
    """Return the marked block that starts the scheduler."""
    return AUTOSTART_BLOCK


def check_autostart() -> None:
    """Raise MalformedBlock when only one of the two markers is present.

    A file with no marker, or with both markers, is left to the caller. A file
    with one marker but not the other is a hand edit or an interrupted write,
    and neither installing nor removing can tell where the block begins and
    ends, so the file is never touched.
    """
    path = autostart_path()
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if (AUTOSTART_BEGIN in content) != (AUTOSTART_END in content):
        raise MalformedBlock(
            f"{path}: the marked block is malformed, only one of its markers is present, "
            "the file was left untouched",
        )


def install_autostart() -> bool:
    """Add the marked block to the herbstluftwm autostart file.

    MalformedBlock is raised, and the file left untouched, when only one of the
    two markers is present.
    """
    check_autostart()
    path = autostart_path()
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    if AUTOSTART_BEGIN in original and AUTOSTART_END in original:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.stem + ".linguapulse.bak"))
    if original and not original.endswith("\n"):
        original += "\n"
    if original:
        original += "\n"
    path.write_text(original + autostart_block(), encoding="utf-8")
    return True


def remove_autostart() -> bool:
    """Remove the marked block from the herbstluftwm autostart file.

    MalformedBlock is raised, and the file left untouched, when only one of the
    two markers is present.
    """
    path = autostart_path()
    if not path.exists():
        return False
    check_autostart()
    original = path.read_text(encoding="utf-8")
    if AUTOSTART_BEGIN not in original:
        return False
    kept: list[str] = []
    inside = False
    for line in original.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == AUTOSTART_BEGIN:
            inside = True
            continue
        if stripped == AUTOSTART_END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    path.write_text("".join(kept), encoding="utf-8")
    return True


def systemctl(*args: str) -> subprocess.CompletedProcess:
    """Run a systemctl user command."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def enable() -> bool:
    """Enable the user unit for the next login."""
    return systemctl("enable", UNIT_NAME).returncode == 0


def disable() -> bool:
    """Disable the user unit."""
    return systemctl("disable", UNIT_NAME).returncode == 0


def install(executable: str) -> list[str]:
    """Install the unit and the autostart, and report every step.

    MalformedBlock is raised, and nothing is written, when only one of the two
    autostart markers is present.
    """
    check_autostart()
    steps: list[str] = []
    unit = install_unit(executable)
    steps.append(f"wrote the user unit {unit}")
    if install_autostart():
        steps.append("added the herbstluftwm autostart block")
    else:
        steps.append("the herbstluftwm autostart block was already there")
    systemctl("daemon-reload")
    if enable():
        steps.append(f"enabled {UNIT_NAME} for the next login")
    else:
        steps.append(f"could not enable the unit, run: systemctl --user enable {UNIT_NAME}")
    return steps


def uninstall() -> list[str]:
    """Remove the unit and the autostart, and report every step.

    MalformedBlock is raised, and nothing is removed, when only one of the two
    autostart markers is present.
    """
    check_autostart()
    steps: list[str] = []
    if disable():
        steps.append(f"disabled {UNIT_NAME}")
    if remove_unit():
        steps.append(f"removed the user unit {unit_path()}")
    else:
        steps.append("there was no user unit to remove")
    if remove_autostart():
        steps.append("removed the herbstluftwm autostart block")
    else:
        steps.append("there was no herbstluftwm autostart block to remove")
    systemctl("daemon-reload")
    return steps
